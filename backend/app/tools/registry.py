"""Tool registry. The LLM can only select from this allowlist; inputs are
validated by Pydantic; write tools never mutate directly - they produce a
pending action, and execution re-validates everything inside the transaction."""
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, ClassVar, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound, ValidationFailed
from app.core.permissions import Perm, Role
from app.db.models import Business, Customer, Invoice, Payment, PaymentCommitment, Reminder
from app.repositories import ledger as repo
from app.utils.i18n import t
from app.utils.money import format_inr


@dataclass
class ToolContext:
    db: AsyncSession
    business: Business
    user_id: uuid.UUID
    role: str
    language: str
    today: date
    now: datetime

    @property
    def business_id(self) -> uuid.UUID:
        return self.business.id


@dataclass
class ToolResult:
    data: Any
    text: str


class Tool:
    name: ClassVar[str]
    description: ClassVar[str]
    input_schema: ClassVar[type[BaseModel]]
    kind: ClassVar[Literal["read", "write"]]
    min_role: ClassVar[Role] = Role.MEMBER
    requires_confirmation: ClassVar[bool] = False
    audit_event: ClassVar[str]
    propose_perm: ClassVar[Perm]
    confirm_perm: ClassVar[Perm | None] = None

    async def run(self, ctx: ToolContext, inp: BaseModel) -> ToolResult:  # read tools
        raise NotImplementedError

    async def preview(self, ctx: ToolContext, inp: BaseModel) -> dict:  # write tools
        raise NotImplementedError

    async def execute(self, ctx: ToolContext, inp: BaseModel, action_id: uuid.UUID) -> dict:  # write tools
        raise NotImplementedError


# ---------- helpers ----------
async def _customer(ctx: ToolContext, cid: uuid.UUID) -> Customer:
    c = (await ctx.db.execute(select(Customer).where(Customer.id == cid, Customer.business_id == ctx.business_id,
                                                     Customer.archived_at.is_(None)))).scalar_one_or_none()
    if c is None:
        raise NotFound("Customer not found", code="customer_not_found")
    return c


async def _invoice(ctx: ToolContext, iid: uuid.UUID, *, lock: bool = False) -> Invoice:
    stmt = select(Invoice).where(Invoice.id == iid, Invoice.business_id == ctx.business_id)
    if lock:
        stmt = stmt.with_for_update()
    inv = (await ctx.db.execute(stmt)).scalar_one_or_none()
    if inv is None:
        raise NotFound("Invoice not found", code="invoice_not_found")
    return inv


def _local(ctx: ToolContext, dt: datetime) -> str:
    return dt.astimezone(ZoneInfo(ctx.business.timezone)).strftime("%d %b %Y, %I:%M %p")


# ---------- read tools ----------
class SearchCustomersIn(BaseModel):
    query: str = Field(min_length=1, max_length=160)


class SearchCustomers(Tool):
    name = "search_customers"
    description = "Find customers by name (fuzzy, transliteration-aware) or phone."
    input_schema = SearchCustomersIn
    kind = "read"
    audit_event = "tool.search_customers"
    propose_perm = Perm.CUSTOMERS_READ

    async def run(self, ctx: ToolContext, inp: SearchCustomersIn) -> ToolResult:  # type: ignore[override]
        cands = await repo.search_customers(ctx.db, ctx.business_id, inp.query, limit=10)
        items = [{"id": str(c.customer.id), "name": c.customer.name, "phone": c.customer.phone_e164,
                  "score": round(c.score, 2)} for c in cands]
        if not items:
            return ToolResult(items, t("not_found_customer", ctx.language, query=inp.query))
        names = ", ".join(f"{i['name']}" + (f" ({i['phone']})" if i["phone"] else "") for i in items)
        return ToolResult(items, t("customers_found", ctx.language, count=len(items), names=names))


class CustomerRefIn(BaseModel):
    customer_id: uuid.UUID


class GetCustomerBalance(Tool):
    name = "get_customer_balance"
    description = "Outstanding balance for one customer, computed from invoices and payments."
    input_schema = CustomerRefIn
    kind = "read"
    audit_event = "tool.get_customer_balance"
    propose_perm = Perm.INVOICES_READ

    async def run(self, ctx: ToolContext, inp: CustomerRefIn) -> ToolResult:  # type: ignore[override]
        c = await _customer(ctx, inp.customer_id)
        bal = await repo.customer_balance(ctx.db, ctx.business_id, c.id, ctx.today)
        data = {"customer": {"id": str(c.id), "name": c.name}, "outstanding_paise": bal["outstanding_paise"],
                "outstanding_display": format_inr(bal["outstanding_paise"]),
                "overdue_paise": bal["overdue_paise"],
                "open_invoices": [{"id": str(i.id), "number": i.number, "balance_paise": i.balance_paise,
                                   "due_on": i.due_on.isoformat(), "is_overdue": i.is_overdue}
                                  for i in bal["open_invoices"]]}
        if bal["outstanding_paise"] == 0:
            return ToolResult(data, t("balance_zero", ctx.language, customer=c.name))
        return ToolResult(data, t("balance", ctx.language, customer=c.name,
                                  amount=format_inr(bal["outstanding_paise"]), count=len(bal["open_invoices"])))


class InvoiceRefIn(BaseModel):
    invoice_number: str = Field(min_length=1, max_length=64)


class GetInvoiceDetails(Tool):
    name = "get_invoice_details"
    description = "Details and balance of one invoice by number."
    input_schema = InvoiceRefIn
    kind = "read"
    audit_event = "tool.get_invoice_details"
    propose_perm = Perm.INVOICES_READ

    async def run(self, ctx: ToolContext, inp: InvoiceRefIn) -> ToolResult:  # type: ignore[override]
        items, _ = await repo.list_invoices(ctx.db, ctx.business_id, ctx.today, number=inp.invoice_number, limit=1)
        if not items:
            raise NotFound("Invoice not found", code="invoice_not_found", details={"query": inp.invoice_number})
        inv = items[0]
        c = await ctx.db.get(Customer, inv.customer_id)
        data = inv.model_dump(mode="json") | {"customer_name": c.name if c else None}
        return ToolResult(data, t("invoice_details", ctx.language, number=inv.number,
                                  customer=c.name if c else "-", total=format_inr(inv.total_paise),
                                  paid=format_inr(inv.paid_paise), balance=format_inr(inv.balance_paise),
                                  due_on=inv.due_on.isoformat(), status=inv.status))


class ListOverdueIn(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)


class ListOverdueInvoices(Tool):
    name = "list_overdue_invoices"
    description = "Open invoices past their due date with a remaining balance."
    input_schema = ListOverdueIn
    kind = "read"
    audit_event = "tool.list_overdue_invoices"
    propose_perm = Perm.INVOICES_READ

    async def run(self, ctx: ToolContext, inp: ListOverdueIn) -> ToolResult:  # type: ignore[override]
        items, total = await repo.list_invoices(ctx.db, ctx.business_id, ctx.today, overdue=True, limit=inp.limit)
        all_items, _ = await repo.list_invoices(ctx.db, ctx.business_id, ctx.today, overdue=True, limit=10000)
        amount = sum(i.balance_paise for i in all_items)
        data = {"count": total, "total_overdue_paise": amount,
                "invoices": [{"id": str(i.id), "number": i.number, "customer_id": str(i.customer_id),
                              "balance_paise": i.balance_paise, "due_on": i.due_on.isoformat()} for i in items]}
        if total == 0:
            return ToolResult(data, t("overdue_none", ctx.language))
        return ToolResult(data, t("overdue_count", ctx.language, count=total, amount=format_inr(amount)))


class ListCustomerReminders(Tool):
    name = "list_customer_reminders"
    description = "Upcoming reminders for one customer."
    input_schema = CustomerRefIn
    kind = "read"
    audit_event = "tool.list_customer_reminders"
    propose_perm = Perm.REMINDERS_READ

    async def run(self, ctx: ToolContext, inp: CustomerRefIn) -> ToolResult:  # type: ignore[override]
        c = await _customer(ctx, inp.customer_id)
        rows = (await ctx.db.execute(select(Reminder).where(
            Reminder.business_id == ctx.business_id, Reminder.customer_id == c.id,
            Reminder.status.in_(["scheduled", "due"])).order_by(Reminder.scheduled_at))).scalars().all()
        data = {"customer": {"id": str(c.id), "name": c.name},
                "reminders": [{"id": str(r.id), "scheduled_at": r.scheduled_at.isoformat(), "status": r.status,
                               "channel": r.channel} for r in rows]}
        details = (": " + "; ".join(_local(ctx, r.scheduled_at) for r in rows[:5])) if rows else ""
        return ToolResult(data, t("reminders_list", ctx.language, customer=c.name, count=len(rows),
                                  details=details))


class EmptyIn(BaseModel):
    pass


class GetDashboardSummary(Tool):
    name = "get_dashboard_summary"
    description = "Business-wide totals: outstanding, overdue, reminders, collections."
    input_schema = EmptyIn
    kind = "read"
    audit_event = "tool.get_dashboard_summary"
    propose_perm = Perm.DASHBOARD_READ

    async def run(self, ctx: ToolContext, inp: EmptyIn) -> ToolResult:  # type: ignore[override]
        summary = await repo.dashboard_summary(ctx.db, ctx.business_id, ctx.today, ctx.now,
                                               ctx.today.replace(day=1))
        return ToolResult(summary, t("dashboard", ctx.language,
                                     outstanding=format_inr(summary["total_outstanding_paise"]),
                                     overdue=summary["overdue_invoices_count"],
                                     reminders=summary["upcoming_reminders_count"],
                                     collected=format_inr(summary["collected_this_month_paise"])))


# ---------- write tools ----------
class ScheduleReminderIn(BaseModel):
    customer_id: uuid.UUID
    invoice_id: uuid.UUID | None = None
    scheduled_at: datetime
    channel: Literal["whatsapp", "sms", "call", "in_app"] = "whatsapp"


class ScheduleReminder(Tool):
    name = "schedule_reminder"
    description = "Schedule a payment reminder for a customer (requires confirmation)."
    input_schema = ScheduleReminderIn
    kind = "write"
    requires_confirmation = True
    audit_event = "reminder.created"
    propose_perm = Perm.REMINDERS_WRITE
    confirm_perm = Perm.REMINDERS_CONFIRM

    async def _validate(self, ctx: ToolContext, inp: ScheduleReminderIn) -> tuple[Customer, Invoice | None]:
        c = await _customer(ctx, inp.customer_id)
        inv = None
        if inp.invoice_id:
            inv = await _invoice(ctx, inp.invoice_id)
            if inv.customer_id != c.id:
                raise ValidationFailed("Invoice does not belong to this customer", code="invoice_customer_mismatch")
        if inp.scheduled_at <= ctx.now:
            raise ValidationFailed("That time is in the past", code="date_in_past")
        return c, inv

    async def preview(self, ctx: ToolContext, inp: ScheduleReminderIn) -> dict:  # type: ignore[override]
        c, inv = await self._validate(ctx, inp)
        when = _local(ctx, inp.scheduled_at)
        inv_txt = f" (invoice {inv.number})" if inv else ""
        return {"text": t("preview_schedule_reminder", ctx.language, customer=c.name, when=when,
                          channel=inp.channel, invoice=inv_txt),
                "fields": {"customer": c.name, "customer_id": str(c.id), "invoice": inv.number if inv else None,
                           "scheduled_at": inp.scheduled_at.isoformat(), "scheduled_at_local": when,
                           "timezone": ctx.business.timezone, "channel": inp.channel}}

    async def execute(self, ctx: ToolContext, inp: ScheduleReminderIn, action_id: uuid.UUID) -> dict:  # type: ignore[override]
        c, inv = await self._validate(ctx, inp)
        r = Reminder(business_id=ctx.business_id, customer_id=c.id, invoice_id=inv.id if inv else None,
                     scheduled_at=inp.scheduled_at, channel=inp.channel, status="scheduled",
                     creation_source="assistant", source_action_id=action_id)
        ctx.db.add(r)
        await ctx.db.flush()
        return {"entity_type": "reminder", "entity_id": str(r.id),
                "summary": f"Reminder for {c.name} at {_local(ctx, inp.scheduled_at)}"}


class CommitmentIn(BaseModel):
    customer_id: uuid.UUID
    invoice_id: uuid.UUID | None = None
    promised_amount_paise: int | None = Field(default=None, gt=0, le=10**13)
    promised_on: date


class RecordPaymentCommitment(Tool):
    name = "record_payment_commitment"
    description = "Record a customer's promise to pay on a date. Never changes payments or invoices."
    input_schema = CommitmentIn
    kind = "write"
    requires_confirmation = True
    audit_event = "commitment.created"
    propose_perm = Perm.COMMITMENTS_WRITE
    confirm_perm = Perm.COMMITMENTS_CONFIRM

    async def _validate(self, ctx: ToolContext, inp: CommitmentIn) -> tuple[Customer, Invoice | None]:
        c = await _customer(ctx, inp.customer_id)
        inv = None
        if inp.invoice_id:
            inv = await _invoice(ctx, inp.invoice_id)
            if inv.customer_id != c.id:
                raise ValidationFailed("Invoice does not belong to this customer", code="invoice_customer_mismatch")
        if inp.promised_on < ctx.today:
            raise ValidationFailed("That date is in the past", code="date_in_past")
        return c, inv

    async def preview(self, ctx: ToolContext, inp: CommitmentIn) -> dict:  # type: ignore[override]
        c, inv = await self._validate(ctx, inp)
        amount = format_inr(inp.promised_amount_paise) if inp.promised_amount_paise else "-"
        return {"text": t("preview_record_payment_commitment", ctx.language, customer=c.name, amount=amount,
                          when=inp.promised_on.strftime("%d %b %Y")),
                "fields": {"customer": c.name, "customer_id": str(c.id), "invoice": inv.number if inv else None,
                           "promised_amount_paise": inp.promised_amount_paise, "promised_amount_display": amount,
                           "promised_on": inp.promised_on.isoformat()}}

    async def execute(self, ctx: ToolContext, inp: CommitmentIn, action_id: uuid.UUID) -> dict:  # type: ignore[override]
        c, inv = await self._validate(ctx, inp)
        pc = PaymentCommitment(business_id=ctx.business_id, customer_id=c.id, invoice_id=inv.id if inv else None,
                               promised_amount_paise=inp.promised_amount_paise, promised_on=inp.promised_on,
                               status="open", source_action_id=action_id)
        ctx.db.add(pc)
        await ctx.db.flush()
        return {"entity_type": "payment_commitment", "entity_id": str(pc.id),
                "summary": f"Commitment from {c.name} for {inp.promised_on.isoformat()}"}


class RecordPaymentIn(BaseModel):
    invoice_id: uuid.UUID
    amount_paise: int = Field(gt=0, le=10**13)
    paid_on: date
    method: Literal["cash", "upi", "bank_transfer", "cheque", "card", "other"] = "cash"


class RecordPayment(Tool):
    name = "record_payment"
    description = "Record a payment received against an invoice (owner/admin confirmation always)."
    input_schema = RecordPaymentIn
    kind = "write"
    min_role = Role.MEMBER
    requires_confirmation = True
    audit_event = "payment.recorded"
    propose_perm = Perm.PAYMENTS_PROPOSE
    confirm_perm = Perm.PAYMENTS_CONFIRM

    async def _validate(self, ctx: ToolContext, inp: RecordPaymentIn, *, lock: bool) -> tuple[Invoice, Customer, int]:
        inv = await _invoice(ctx, inp.invoice_id, lock=lock)
        if inv.status != "open":
            raise ValidationFailed(f"Invoice is {inv.status}", code="invoice_not_open")
        paid = (await ctx.db.execute(select(func.coalesce(func.sum(Payment.amount_paise), 0)).where(
            Payment.invoice_id == inv.id))).scalar_one()
        balance = inv.total_paise - int(paid)
        if inp.amount_paise > balance:
            raise ValidationFailed("Amount exceeds the invoice balance", code="amount_exceeds_balance",
                                   details={"balance_paise": balance})
        if inp.paid_on > ctx.today:
            raise ValidationFailed("Payment date cannot be in the future", code="date_in_future")
        c = await ctx.db.get(Customer, inv.customer_id)
        assert c is not None
        return inv, c, int(paid)

    async def preview(self, ctx: ToolContext, inp: RecordPaymentIn) -> dict:  # type: ignore[override]
        inv, c, _ = await self._validate(ctx, inp, lock=False)
        return {"text": t("preview_record_payment", ctx.language, customer=c.name,
                          amount=format_inr(inp.amount_paise), invoice=inv.number,
                          when=inp.paid_on.strftime("%d %b %Y")),
                "fields": {"customer": c.name, "customer_id": str(c.id), "invoice": inv.number,
                           "invoice_id": str(inv.id), "amount_paise": inp.amount_paise,
                           "amount_display": format_inr(inp.amount_paise), "paid_on": inp.paid_on.isoformat(),
                           "method": inp.method}}

    async def execute(self, ctx: ToolContext, inp: RecordPaymentIn, action_id: uuid.UUID) -> dict:  # type: ignore[override]
        inv, c, paid = await self._validate(ctx, inp, lock=True)
        p = Payment(business_id=ctx.business_id, invoice_id=inv.id, amount_paise=inp.amount_paise,
                    paid_on=inp.paid_on, method=inp.method, source_action_id=action_id)
        ctx.db.add(p)
        if paid + inp.amount_paise >= inv.total_paise:
            inv.status = "paid"
        await ctx.db.flush()
        return {"entity_type": "payment", "entity_id": str(p.id),
                "summary": f"Payment of {format_inr(inp.amount_paise)} on {inv.number}"}


REGISTRY: dict[str, Tool] = {tool.name: tool for tool in (
    SearchCustomers(), GetCustomerBalance(), GetInvoiceDetails(), ListOverdueInvoices(),
    ListCustomerReminders(), GetDashboardSummary(), ScheduleReminder(), RecordPaymentCommitment(),
    RecordPayment(),
)}
ALLOWLIST: frozenset[str] = frozenset(REGISTRY)
WRITE_TOOLS: frozenset[str] = frozenset(n for n, tl in REGISTRY.items() if tl.kind == "write")


def get_tool(name: str) -> Tool:
    tool = REGISTRY.get(name)
    if tool is None:
        raise ValidationFailed("Unknown tool", code="unknown_tool", details={"tool": name})
    return tool


def tools_for_role(role: str, business_settings: dict | None = None) -> set[str]:
    from app.core.permissions import has_perm

    return {n for n, tl in REGISTRY.items() if has_perm(role, tl.propose_perm, business_settings)}


def effective_tools(role: str, agent_tools: list[str] | None, business_settings: dict | None = None) -> set[str]:
    """agent enabled_tools ∩ role permissions ∩ global allowlist."""
    allowed = set(ALLOWLIST) & tools_for_role(role, business_settings)
    if agent_tools is not None:
        allowed &= set(agent_tools)
    return allowed
