"""Claude adapter: structured output validated against the same Pydantic Intent schema.

Untrusted content (agent instructions, prior turns) is wrapped in <data> tags and
the system prompt states it is data, never instructions. The model only fills
the schema; tools, permissions and confirmation are enforced by the backend."""
import logging
import time

import anthropic
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.exceptions import ProviderNotConfigured, ProviderUnavailable
from app.core.logging import log_event
from app.providers.llm.base import IntentContext
from app.providers.llm.prompts import (
    AGENT_SYSTEM,
    INTENT_SYSTEM,
    agent_user_message,
    intent_user_message,
    reply_system,
)
from app.schemas.assistant import AgentConfig, Intent

logger = logging.getLogger(__name__)


class AnthropicLLM:
    name = "anthropic"

    def __init__(self) -> None:
        s = get_settings()
        if not s.anthropic_api_key:
            raise ProviderNotConfigured("ANTHROPIC_API_KEY is not set", details={"provider": "anthropic"})
        self.model = s.anthropic_model
        self.client = anthropic.AsyncAnthropic(api_key=s.anthropic_api_key, timeout=s.llm_timeout_seconds,
                                               max_retries=2)

    async def _parse(self, system: str, user: str, schema: type, max_tokens: int = 2048):  # type: ignore[no-untyped-def]
        started = time.perf_counter()
        last_error: Exception | None = None
        for _attempt in range(2):  # retry once on malformed output, then fail safely
            try:
                resp = await self.client.messages.parse(
                    model=self.model, max_tokens=max_tokens, system=system,
                    messages=[{"role": "user", "content": user}], output_format=schema,
                )
            except anthropic.RateLimitError as e:
                raise ProviderUnavailable("LLM rate limited", details={"provider": "anthropic"}) from e
            except anthropic.APIStatusError as e:
                raise ProviderUnavailable("LLM error", details={"provider": "anthropic",
                                                                "status": e.status_code}) from e
            except anthropic.APIConnectionError as e:
                raise ProviderUnavailable("LLM unreachable", details={"provider": "anthropic"}) from e
            except ValidationError as e:
                last_error = e
                continue
            finally:
                log_event(logger, "llm_call", provider="anthropic",
                          latency_ms=round((time.perf_counter() - started) * 1000))
            if resp.stop_reason == "refusal":
                return None
            if resp.parsed_output is not None:
                return resp.parsed_output
        raise ProviderUnavailable("LLM returned invalid output", details={"provider": "anthropic",
                                                                        "error": type(last_error).__name__})

    async def extract_intent(self, text: str, ctx: IntentContext) -> Intent:
        result = await self._parse(INTENT_SYSTEM, intent_user_message(text, ctx), Intent, max_tokens=2048)
        if result is None:
            return Intent(type="unsupported", confidence=0.0)
        return result

    async def generate_agent_config(self, description: str, language: str | None,
                                    allowed_tools: list[str]) -> AgentConfig:
        result = await self._parse(AGENT_SYSTEM, agent_user_message(description, language, allowed_tools),
                                   AgentConfig, max_tokens=4096)
        if result is None:
            raise ProviderUnavailable("LLM declined to generate a configuration")
        return result

    async def compose_reply(self, text: str, language: str, agent_instructions: str | None) -> str:
        try:
            resp = await self.client.messages.create(
                model=self.model, max_tokens=1024, system=reply_system(language, agent_instructions),
                messages=[{"role": "user", "content": f"<data>\n{text}\n</data>"}],
            )
        except anthropic.APIError as e:
            raise ProviderUnavailable("LLM error", details={"provider": "anthropic"}) from e
        if resp.stop_reason == "refusal":
            return ""
        return "".join(b.text for b in resp.content if isinstance(b, anthropic.types.TextBlock)).strip()
