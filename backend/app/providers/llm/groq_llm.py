"""Groq LLM adapter (default model openai/gpt-oss-120b).

Uses strict json_schema structured outputs, then validates again with the same
Pydantic schemas the rest of the pipeline uses. Retries once on invalid output."""
import json
from typing import Any

from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.exceptions import ProviderUnavailable
from app.providers import groq_http
from app.providers.llm.base import IntentContext
from app.providers.llm.prompts import (
    AGENT_SYSTEM,
    INTENT_SYSTEM,
    agent_user_message,
    intent_user_message,
    reply_system,
)
from app.schemas.assistant import AgentConfig, Intent

# Groq strict mode needs closed objects with every property required; constraint
# keywords are dropped here because Pydantic re-validates the result anyway.
_DROP = {"title", "default", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength",
         "maxLength", "minItems", "maxItems", "pattern", "format"}


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(n) for n in node]
        if not isinstance(node, dict):
            return node
        out = {k: walk(v) for k, v in node.items() if k not in _DROP}
        if out.get("type") == "object" or "properties" in out:
            props = out.get("properties", {})
            required = set(node.get("required", []))
            for name, prop in props.items():
                if name not in required and not _nullable(prop):
                    props[name] = {"anyOf": [prop, {"type": "null"}]}
            out["type"] = "object"
            out["required"] = list(props)
            out["additionalProperties"] = False
        return out

    return walk(model.model_json_schema())


def _nullable(prop: dict) -> bool:
    return prop.get("type") == "null" or any(p.get("type") == "null" for p in prop.get("anyOf", []))


def _strip_nulls(value: Any) -> Any:
    """Strict mode returns explicit nulls for every optional field; let Pydantic defaults apply."""
    if isinstance(value, dict):
        return {k: _strip_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_strip_nulls(v) for v in value]
    return value


class GroqLLM:
    name = "groq"

    def __init__(self) -> None:
        groq_http.require_key()
        s = get_settings()
        self.model = s.groq_llm_model
        self.reasoning_effort = s.groq_reasoning_effort
        self.timeout = s.llm_timeout_seconds

    def _body(self, system: str, user: str, max_tokens: int) -> dict[str, Any]:
        return {"model": self.model, "messages": [{"role": "system", "content": system},
                                                  {"role": "user", "content": user}],
                "max_completion_tokens": max_tokens, "temperature": 0, "reasoning_effort": self.reasoning_effort,
                "include_reasoning": False}

    async def _structured(self, system: str, user: str, model: type[BaseModel], max_tokens: int) -> Any:
        body = self._body(system, user, max_tokens)
        body["response_format"] = {"type": "json_schema", "json_schema": {
            "name": model.__name__.lower(), "strict": True, "schema": strict_schema(model)}}
        last_error = ""
        for _attempt in range(2):
            resp = await groq_http.post("/chat/completions", json=body, timeout=self.timeout, kind="llm")
            try:
                content = resp.json()["choices"][0]["message"]["content"] or ""
                return model.model_validate(_strip_nulls(json.loads(content)))
            except (KeyError, IndexError, ValueError, ValidationError) as e:
                last_error = type(e).__name__
        raise ProviderUnavailable("LLM returned invalid output", details={"provider": "groq", "error": last_error})

    async def extract_intent(self, text: str, ctx: IntentContext) -> Intent:
        return await self._structured(INTENT_SYSTEM, intent_user_message(text, ctx), Intent, 2048)

    async def generate_agent_config(self, description: str, language: str | None,
                                    allowed_tools: list[str]) -> AgentConfig:
        return await self._structured(AGENT_SYSTEM, agent_user_message(description, language, allowed_tools),
                                      AgentConfig, 4096)

    async def compose_reply(self, text: str, language: str, agent_instructions: str | None) -> str:
        body = self._body(reply_system(language, agent_instructions), f"<data>\n{text}\n</data>", 1024)
        resp = await groq_http.post("/chat/completions", json=body, timeout=self.timeout, kind="llm")
        try:
            return (resp.json()["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, ValueError):
            return ""
