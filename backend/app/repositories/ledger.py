"""Complex queries only: balances, fuzzy customer search, dashboard aggregates."""
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import Select, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Customer, Invoice, Payment, PaymentCommitment, PendingAction, Reminder
from app.schemas.ledger import InvoiceOut
from app.utils.text import normalize_name

TRGM_THRESHOLD = 0.3
AMBIGUITY_MARGIN = 0.15


def paid_subquery(business_id: uuid.UUID):  # type: ignore[no-untyped-def]
    return (
        select(Payment.invoice_id, func.coalesce(func.sum(Payment.amount_paise), 0).label("paid"))
        .where(Payment.business_id == business_id)
        .group_by(Payment.invoice_id)
        .subquery()
    )


def invoice_select(business_id: uuid.UUID) -> tuple[Select, Any, Any]:
    paid_sq = paid_subquery(business_id)
    paid = func.coalesce(paid_sq.c.paid, 0)
    balance = case((Invoice.status == "open", func.greatest(Invoice.total_paise - paid, 0)), else_=0)
    stmt = (
        select(Invoice, paid.label("paid"), balance.label("balance"))
        .outerjoin(paid_sq, paid_sq.c.invoice_id == Invoice.id)
        .where(Invoice.business_id == business_id)
    )
    return stmt, paid, balance


def to_invoice_out(inv: Invoice, paid: int, today: date) -> InvoiceOut:
    balance = max(inv.total_paise - int(paid), 0) if inv.status == "open" else 0
    out = InvoiceOut.model_validate(inv)
    out.paid_paise = int(paid)
    out.balance_paise = balance
    out.is_overdue = inv.status == "open" and balance > 0 and inv.due_on < today
    return out


async def get_invoice_with_balance(db: AsyncSession, business_id: uuid.UUID, invoice_id: uuid.UUID,
                                   today: date) -> InvoiceOut | None:
    stmt, _, _ = invoice_select(business_id)
    row = (await db.execute(stmt.where(Invoice.id == invoice_id))).first()
    return to_invoice_out(row[0], row[1], today) if row else None


async def list_invoices(
    db: AsyncSession, business_id: uuid.UUID, today: date, *, customer_id: uuid.UUID | None = None,
    status: str | None = None, overdue: bool | None = None, number: str | None = None,
    offset: int = 0, limit: int = 20,
) -> tuple[list[InvoiceOut], int]:
    stmt, _, balance = invoice_select(business_id)
    conds = []
    if customer_id:
        conds.append(Invoice.customer_id == customer_id)
    if status:
        conds.append(Invoice.status == status)
    if number:
        conds.append(func.lower(Invoice.number) == number.lower())
    overdue_cond = and_(Invoice.status == "open", Invoice.due_on < today, balance > 0)
    if overdue is True:
        conds.append(overdue_cond)
    elif overdue is False:
        conds.append(~overdue_cond)
    if conds:
        stmt = stmt.where(*conds)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(
        stmt.order_by(Invoice.due_on.asc(), Invoice.number.asc()).offset(offset).limit(limit))).all()
    return [to_invoice_out(r[0], r[1], today) for r in rows], total


async def customer_balance(db: AsyncSession, business_id: uuid.UUID, customer_id: uuid.UUID,
                           today: date) -> dict:
    invoices, _ = await list_invoices(db, business_id, today, customer_id=customer_id, status="open",
                                      limit=1000)
    open_with_balance = [i for i in invoices if i.balance_paise > 0]
    return {
        "customer_id": str(customer_id),
        "outstanding_paise": sum(i.balance_paise for i in open_with_balance),
        "overdue_paise": sum(i.balance_paise for i in open_with_balance if i.is_overdue),
        "open_invoices": open_with_balance,
    }


# ---------- customers ----------
@dataclass
class Candidate:
    customer: Customer
    score: float


async def search_customers(db: AsyncSession, business_id: uuid.UUID, query: str, limit: int = 10,
                           include_archived: bool = False) -> list[Candidate]:
    q = normalize_name(query)
    if not q:
        return []
    score = func.greatest(func.similarity(Customer.name_normalized, q),
                          func.word_similarity(q, Customer.name_normalized))
    stmt = select(Customer, score.label("score")).where(
        Customer.business_id == business_id,
        or_(score >= TRGM_THRESHOLD, Customer.name_normalized.contains(q)),
    )
    if not include_archived:
        stmt = stmt.where(Customer.archived_at.is_(None))
    rows = (await db.execute(stmt.order_by(score.desc(), Customer.name.asc()).limit(limit))).all()
    return [Candidate(r[0], float(r[1])) for r in rows]


async def resolve_customer(db: AsyncSession, business_id: uuid.UUID, *, name: str | None = None,
                           phone_e164: str | None = None) -> tuple[Customer | None, list[Customer]]:
    """Return (match, candidates). Exactly one of: a match, >1 candidates (ambiguous), or nothing."""
    if phone_e164:
        rows = (await db.execute(select(Customer).where(
            Customer.business_id == business_id, Customer.phone_e164 == phone_e164,
            Customer.archived_at.is_(None)))).scalars().all()
        if len(rows) == 1:
            return rows[0], []
        if len(rows) > 1:
            return None, list(rows)
    if not name:
        return None, []
    q = normalize_name(name)
    exact = (await db.execute(select(Customer).where(
        Customer.business_id == business_id, Customer.name_normalized == q,
        Customer.archived_at.is_(None)))).scalars().all()
    if len(exact) == 1:
        return exact[0], []
    if len(exact) > 1:
        return None, list(exact)
    cands = await search_customers(db, business_id, name, limit=6)
    if not cands:
        return None, []
    if len(cands) == 1 or cands[0].score - cands[1].score >= AMBIGUITY_MARGIN:
        return cands[0].customer, []
    top = cands[0].score
    return None, [c.customer for c in cands if top - c.score < AMBIGUITY_MARGIN]


# ---------- dashboard ----------
async def dashboard_summary(db: AsyncSession, business_id: uuid.UUID, today: date, now: datetime,
                            month_start: date) -> dict:
    stmt, _, balance = invoice_select(business_id)
    sq = stmt.subquery()
    agg = (await db.execute(select(
        func.coalesce(func.sum(sq.c.balance), 0),
        func.count().filter(and_(sq.c.status == "open", sq.c.balance > 0)),
        func.count().filter(and_(sq.c.status == "open", sq.c.balance > 0, sq.c.due_on < today)),
        func.coalesce(func.sum(sq.c.balance).filter(sq.c.due_on < today), 0),
    ))).one()
    customers_count = (await db.execute(select(func.count()).select_from(Customer).where(
        Customer.business_id == business_id, Customer.archived_at.is_(None)))).scalar_one()
    upcoming = (await db.execute(select(func.count()).select_from(Reminder).where(
        Reminder.business_id == business_id, Reminder.status == "scheduled",
        Reminder.scheduled_at > now))).scalar_one()
    due = (await db.execute(select(func.count()).select_from(Reminder).where(
        Reminder.business_id == business_id, Reminder.status == "due"))).scalar_one()
    collected = (await db.execute(select(func.coalesce(func.sum(Payment.amount_paise), 0)).where(
        Payment.business_id == business_id, Payment.paid_on >= month_start))).scalar_one()
    pending = (await db.execute(select(func.count()).select_from(PendingAction).where(
        PendingAction.business_id == business_id, PendingAction.status == "pending_confirmation",
        PendingAction.expires_at > now))).scalar_one()
    commitments = (await db.execute(select(func.count()).select_from(PaymentCommitment).where(
        PaymentCommitment.business_id == business_id, PaymentCommitment.status == "open"))).scalar_one()
    return {
        "total_outstanding_paise": int(agg[0]),
        "open_invoices_count": int(agg[1]),
        "overdue_invoices_count": int(agg[2]),
        "overdue_amount_paise": int(agg[3]),
        "customers_count": int(customers_count),
        "upcoming_reminders_count": int(upcoming),
        "due_reminders_count": int(due),
        "collected_this_month_paise": int(collected),
        "pending_actions_count": int(pending),
        "open_commitments_count": int(commitments),
    }
