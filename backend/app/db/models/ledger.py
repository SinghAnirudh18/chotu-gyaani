import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


def _bid() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"),
                         index=True, nullable=False)


class Customer(IdMixin, TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (
        Index("ix_customers_name_trgm", "name_normalized", postgresql_using="gin",
              postgresql_ops={"name_normalized": "gin_trgm_ops"}),
        Index("ix_customers_business_phone", "business_id", "phone_e164"),
    )
    business_id: Mapped[uuid.UUID] = _bid()
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(160), nullable=False)
    phone_e164: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(254))
    external_ref: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Invoice(IdMixin, TimestampMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("business_id", "number"),
        CheckConstraint("total_paise > 0", name="total_positive"),
        CheckConstraint("status IN ('open','paid','void')", name="status_valid"),
    )
    business_id: Mapped[uuid.UUID] = _bid()
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), index=True, nullable=False)
    number: Mapped[str] = mapped_column(String(64), nullable=False)
    total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    issued_on: Mapped[date] = mapped_column(Date, nullable=False)
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="open")
    description: Mapped[str | None] = mapped_column(Text)


class Payment(IdMixin, TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (CheckConstraint("amount_paise > 0", name="amount_positive"),)
    business_id: Mapped[uuid.UUID] = _bid()
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="RESTRICT"), index=True, nullable=False)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False, server_default="cash")
    source_action_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), unique=True)


class PaymentCommitment(IdMixin, TimestampMixin, Base):
    __tablename__ = "payment_commitments"
    __table_args__ = (
        CheckConstraint("promised_amount_paise IS NULL OR promised_amount_paise > 0", name="amount_positive"),
        CheckConstraint("status IN ('open','kept','broken','cancelled')", name="status_valid"),
    )
    business_id: Mapped[uuid.UUID] = _bid()
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), index=True, nullable=False)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), index=True)
    promised_amount_paise: Mapped[int | None] = mapped_column(BigInteger)
    promised_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="open")
    notes: Mapped[str | None] = mapped_column(Text)
    source_action_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), unique=True)


class Reminder(IdMixin, TimestampMixin, Base):
    __tablename__ = "reminders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('scheduled','due','delivered','failed','cancelled','completed')", name="status_valid"),
        CheckConstraint("channel IN ('whatsapp','sms','call','in_app')", name="channel_valid"),
        Index("ix_reminders_due_poll", "status", "next_attempt_at"),
    )
    business_id: Mapped[uuid.UUID] = _bid()
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), index=True, nullable=False)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False, server_default="whatsapp")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="scheduled")
    message: Mapped[str | None] = mapped_column(Text)
    creation_source: Mapped[str] = mapped_column(String(16), nullable=False, server_default="api")
    delivery_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(255))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_action_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), unique=True)
