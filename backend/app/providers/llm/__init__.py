from app.core.config import get_settings
from app.providers.llm.base import IntentContext, LLMProvider
from app.providers.llm.mock import MockLLM

_override: LLMProvider | None = None


def get_llm() -> LLMProvider:
    if _override is not None:
        return _override
    provider = get_settings().llm_provider
    if provider == "groq":
        from app.providers.llm.groq_llm import GroqLLM

        return GroqLLM()
    if provider == "anthropic":
        from app.providers.llm.anthropic_llm import AnthropicLLM

        return AnthropicLLM()
    return MockLLM()


def set_llm_override(provider: LLMProvider | None) -> None:
    global _override
    _override = provider


__all__ = ["IntentContext", "LLMProvider", "MockLLM", "get_llm", "set_llm_override"]
