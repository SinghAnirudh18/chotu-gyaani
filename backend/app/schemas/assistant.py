import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel

IntentType = Literal[
    "search_customers", "get_customer_balance", "get_invoice_details", "list_overdue_invoices",
    "list_customer_reminders", "get_dashboard_summary", "schedule_reminder",
    "record_payment_commitment", "record_payment", "create_customer", "clarify", "smalltalk", "unsupported",
]


class DateSpec(BaseModel):
    relative: str | None = Field(default=None, max_length=32)
    date: str | None = Field(default=None, max_length=10)
    time: str | None = Field(default=None, max_length=5)


class IntentEntities(BaseModel):
    customer_name: str | None = Field(default=None, max_length=160)
    customer_phone: str | None = Field(default=None, max_length=32)
    invoice_number: str | None = Field(default=None, max_length=64)
    amount_phrase: str | None = Field(default=None, max_length=80)
    date: DateSpec | None = None
    channel: Literal["whatsapp", "sms", "call", "in_app"] | None = None
    query: str | None = Field(default=None, max_length=160)


class Intent(BaseModel):
    type: IntentType
    entities: IntentEntities = Field(default_factory=IntentEntities)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    missing_fields: list[str] = Field(default_factory=list)


class ConversationCreate(BaseModel):
    agent_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=160)
    language: Literal["en", "hi", "hi-Latn"] | None = None


class ConversationOut(ORMModel):
    id: uuid.UUID
    agent_id: uuid.UUID | None
    user_id: uuid.UUID
    title: str | None
    language: str | None
    is_test: bool
    created_at: datetime
    updated_at: datetime


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    language: Literal["en", "hi", "hi-Latn"] | None = None


class MessageOut(ORMModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    intent: dict | None
    tool_metadata: dict | None
    language: str | None
    created_at: datetime


class ActionOut(ORMModel):
    id: uuid.UUID
    conversation_id: uuid.UUID | None
    user_id: uuid.UUID
    type: str
    payload: dict
    preview: dict
    status: str
    expires_at: datetime
    confirmed_by: uuid.UUID | None
    result: dict | None
    error: str | None
    created_at: datetime
    updated_at: datetime


# ---------- agents ----------
class KnowledgeSource(BaseModel):
    type: Literal["note", "url", "faq"]
    value: str = Field(min_length=1, max_length=2000)


class AgentConfig(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    language: Literal["en", "hi", "hi-Latn"] = "hi-Latn"
    instructions: str = Field(default="", max_length=4000)
    enabled_tools: list[str] = Field(default_factory=list, max_length=20)
    knowledge_sources: list[KnowledgeSource] = Field(default_factory=list, max_length=10)


class AgentGenerateIn(BaseModel):
    description: str = Field(min_length=3, max_length=2000)
    language: Literal["en", "hi", "hi-Latn"] | None = None


class AgentPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    language: Literal["en", "hi", "hi-Latn"] | None = None
    instructions: str | None = Field(default=None, max_length=4000)
    enabled_tools: list[str] | None = Field(default=None, max_length=20)
    knowledge_sources: list[KnowledgeSource] | None = Field(default=None, max_length=10)


class AgentOut(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None
    language: str
    instructions: str
    enabled_tools: list[str]
    knowledge_sources: list[Any]
    status: str
    config_version: int
    created_at: datetime
    updated_at: datetime


class AgentTestIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    language: Literal["en", "hi", "hi-Latn"] | None = None


class SpeechIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    language: Literal["en", "hi", "hi-Latn"] = "hi-Latn"
    voice: str | None = Field(default=None, max_length=64)
