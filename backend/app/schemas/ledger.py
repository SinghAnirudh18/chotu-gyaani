import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, computed_field

from app.schemas.common import ORMModel
from app.utils.money import format_inr

Channel = Literal["whatsapp", "sms", "call", "in_app"]


# ---------- customers ----------
class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    external_ref: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)


class CustomerPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    external_ref: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)


class CustomerOut(ORMModel):
    id: uuid.UUID
    name: str
    phone_e164: str | None
    email: str | None
    external_ref: str | None
    notes: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ---------- invoices ----------
class InvoiceCreate(BaseModel):
    customer_id: uuid.UUID
    number: str = Field(min_length=1, max_length=64)
    total_paise: int = Field(gt=0, le=10**13)
    issued_on: date
    due_on: date
    description: str | None = Field(default=None, max_length=4000)


class InvoicePatch(BaseModel):
    total_paise: int | None = Field(default=None, gt=0, le=10**13)
    issued_on: date | None = None
    due_on: date | None = None
    description: str | None = Field(default=None, max_length=4000)
    status: Literal["open", "void"] | None = None


class InvoiceOut(ORMModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    number: str
    total_paise: int
    paid_paise: int = 0
    balance_paise: int = 0
    issued_on: date
    due_on: date
    status: str
    is_overdue: bool = False
    description: str | None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_display(self) -> str | None:
        return format_inr(self.total_paise)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def balance_display(self) -> str | None:
        return format_inr(self.balance_paise)


class PaymentOut(ORMModel):
    id: uuid.UUID
    invoice_id: uuid.UUID
    amount_paise: int
    paid_on: date
    method: str
    source_action_id: uuid.UUID | None
    created_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def amount_display(self) -> str | None:
        return format_inr(self.amount_paise)


class PaymentProposeIn(BaseModel):
    amount_paise: int = Field(gt=0, le=10**13)
    paid_on: date | None = None
    method: Literal["cash", "upi", "bank_transfer", "cheque", "card", "other"] = "cash"


# ---------- reminders ----------
class ReminderCreate(BaseModel):
    customer_id: uuid.UUID
    invoice_id: uuid.UUID | None = None
    scheduled_at: datetime
    channel: Channel = "whatsapp"
    message: str | None = Field(default=None, max_length=1000)


class ReminderPatch(BaseModel):
    scheduled_at: datetime | None = None
    channel: Channel | None = None
    message: str | None = Field(default=None, max_length=1000)


class ReminderOut(ORMModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    invoice_id: uuid.UUID | None
    scheduled_at: datetime
    channel: str
    status: str
    message: str | None
    creation_source: str
    delivery_attempts: int
    last_error: str | None
    completed_at: datetime | None
    source_action_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


# ---------- commitments ----------
class CommitmentCreate(BaseModel):
    customer_id: uuid.UUID
    invoice_id: uuid.UUID | None = None
    promised_amount_paise: int | None = Field(default=None, gt=0, le=10**13)
    promised_on: date
    notes: str | None = Field(default=None, max_length=2000)


class CommitmentPatch(BaseModel):
    promised_amount_paise: int | None = Field(default=None, gt=0, le=10**13)
    promised_on: date | None = None
    status: Literal["open", "kept", "broken", "cancelled"] | None = None
    notes: str | None = Field(default=None, max_length=2000)


class CommitmentOut(ORMModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    invoice_id: uuid.UUID | None
    promised_amount_paise: int | None
    promised_on: date
    status: str
    notes: str | None
    source_action_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
