"""Shared HTTP access to Groq's OpenAI-compatible API (LLM, STT, TTS).

Timeouts and bounded retries; provider errors are mapped to safe AppErrors.
Logs carry latency and status only, never prompts, transcripts or keys."""
import asyncio
import logging
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.exceptions import ProviderNotConfigured, ProviderUnavailable
from app.core.logging import log_event

logger = logging.getLogger(__name__)

# Tests inject an httpx.MockTransport here; production uses the default transport.
transport_override: httpx.AsyncBaseTransport | None = None


def require_key() -> str:
    key = get_settings().groq_api_key
    if not key:
        raise ProviderNotConfigured("GROQ_API_KEY is not set", details={"provider": "groq"})
    return key


async def post(path: str, *, json: dict | None = None, files: dict | None = None, data: dict | None = None,
               timeout: float = 30.0, kind: str = "llm") -> httpx.Response:
    s = get_settings()
    headers = {"Authorization": f"Bearer {require_key()}"}
    transport = transport_override or httpx.AsyncHTTPTransport(retries=2)  # retries connection errors
    started = time.perf_counter()
    last: httpx.Response | None = None
    async with httpx.AsyncClient(base_url=s.groq_base_url, timeout=httpx.Timeout(timeout, connect=5.0),
                                 transport=transport) as client:
        for attempt in range(2):
            try:
                resp = await client.post(path, headers=headers, json=json, files=files, data=data)
            except httpx.HTTPError as e:
                log_event(logger, "provider_call", provider="groq", kind=kind, outcome="network_error",
                          latency_ms=round((time.perf_counter() - started) * 1000))
                raise ProviderUnavailable("Groq is unreachable", details={"provider": "groq"}) from e
            last = resp
            if attempt == 0 and resp.status_code >= 500:
                await asyncio.sleep(0.5)
                continue
            # Free-tier token limits reset within seconds; wait once if the wait is short.
            wait = retry_after_seconds(resp)
            if attempt == 0 and resp.status_code == 429 and wait is not None \
                    and wait <= s.groq_max_rate_limit_wait_seconds:
                await asyncio.sleep(wait)
                continue
            break
    assert last is not None
    log_event(logger, "provider_call", provider="groq", kind=kind, status=last.status_code,
              latency_ms=round((time.perf_counter() - started) * 1000))
    if last.status_code < 400:
        return last
    code = _error_code(last)
    if last.status_code in (401, 403):
        raise ProviderNotConfigured("Groq rejected the API key", details={"provider": "groq"})
    if code == "model_terms_required":
        raise ProviderNotConfigured("Accept the model terms in the Groq console before using it",
                                    details={"provider": "groq", "reason": code})
    if last.status_code == 429:
        raise ProviderUnavailable("Groq rate limit reached", details={
            "provider": "groq", "retry_after": last.headers.get("retry-after")})
    raise ProviderUnavailable("Groq request failed", details={"provider": "groq", "status": last.status_code,
                                                              "reason": code})


def retry_after_seconds(resp: httpx.Response) -> float | None:
    try:
        return float(resp.headers["retry-after"])
    except (KeyError, ValueError):
        return None


def _error_code(resp: httpx.Response) -> str | None:
    try:
        body: Any = resp.json()
        return body.get("error", {}).get("code")
    except ValueError:
        return None
