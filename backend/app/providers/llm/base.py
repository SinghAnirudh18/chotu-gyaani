from dataclasses import dataclass, field
from typing import Protocol

from app.schemas.assistant import AgentConfig, Intent


@dataclass
class IntentContext:
    language: str
    timezone: str
    today_iso: str
    allowed_intents: list[str]
    agent_instructions: str | None = None
    awaiting_slot: str | None = None
    recent_turns: list[dict] = field(default_factory=list)


class LLMProvider(Protocol):
    name: str

    async def extract_intent(self, text: str, ctx: IntentContext) -> Intent: ...

    async def generate_agent_config(self, description: str, language: str | None,
                                    allowed_tools: list[str]) -> AgentConfig: ...

    async def compose_reply(self, text: str, language: str, agent_instructions: str | None) -> str: ...
