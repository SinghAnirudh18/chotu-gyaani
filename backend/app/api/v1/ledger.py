import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.api.deps import Ctx, require
from app.core.exceptions import ValidationFailed
from app.core.permissions import Perm
from app.repositories import ledger as repo
from app.schemas.assistant import ActionOut
from app.schemas.common import Pagination, envelope
from app.schemas.ledger import (
    CommitmentCreate,
    CommitmentOut,
    CommitmentPatch,
    CustomerCreate,
    CustomerOut,
    CustomerPatch,
    InvoiceCreate,
    InvoicePatch,
    PaymentOut,
    PaymentProposeIn,
    ReminderCreate,
    ReminderOut,
    ReminderPatch,
)
from app.services import action_service, ledger_service
from app.tools.registry import get_tool
from app.utils.money import format_inr

router = APIRouter(tags=["ledger"])


# ---------------- customers ----------------
@router.post("/customers", status_code=201)
async def create_customer(data: CustomerCreate, ctx: Ctx = Depends(require(Perm.CUSTOMERS_WRITE))) -> dict:
    return envelope(CustomerOut.model_validate(await ledger_service.create_customer(ctx, data)))


@router.get("/customers")
async def list_customers(q: str | None = Query(None, max_length=160), phone: str | None = Query(None, max_length=32),
                         include_archived: bool = False, page: Pagination = Depends(),
                         ctx: Ctx = Depends(require(Perm.CUSTOMERS_READ))) -> dict:
    items, total = await ledger_service.list_customers(ctx, q=q, phone=phone, include_archived=include_archived,
                                                       offset=page.offset, limit=page.page_size)
    return envelope([CustomerOut.model_validate(c) for c in items], **page.meta(total))


@router.post("/customers/import")
async def import_customers(file: UploadFile = File(...), dry_run: bool = True,
                           ctx: Ctx = Depends(require(Perm.CUSTOMERS_IMPORT))) -> dict:
    raw = await file.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValidationFailed("CSV file is too large (max 2 MB)", code="file_too_large")
    return envelope(await ledger_service.import_customers_csv(ctx, raw, dry_run))


@router.get("/customers/{customer_id}")
async def get_customer(customer_id: uuid.UUID, ctx: Ctx = Depends(require(Perm.CUSTOMERS_READ))) -> dict:
    c = await ledger_service.get_customer(ctx, customer_id)
    bal = await repo.customer_balance(ctx.db, ctx.business_id, c.id, ledger_service.today(ctx))
    data = CustomerOut.model_validate(c).model_dump(mode="json")
    data["balance"] = {"outstanding_paise": bal["outstanding_paise"],
                       "outstanding_display": format_inr(bal["outstanding_paise"]),
                       "overdue_paise": bal["overdue_paise"], "open_invoices_count": len(bal["open_invoices"])}
    return envelope(data)


@router.patch("/customers/{customer_id}")
async def patch_customer(customer_id: uuid.UUID, data: CustomerPatch,
                         ctx: Ctx = Depends(require(Perm.CUSTOMERS_WRITE))) -> dict:
    return envelope(CustomerOut.model_validate(await ledger_service.update_customer(ctx, customer_id, data)))


@router.delete("/customers/{customer_id}")
async def delete_customer(customer_id: uuid.UUID, ctx: Ctx = Depends(require(Perm.CUSTOMERS_DELETE))) -> dict:
    return envelope(CustomerOut.model_validate(await ledger_service.archive_customer(ctx, customer_id)))


# ---------------- invoices & payments ----------------
@router.post("/invoices", status_code=201)
async def create_invoice(data: InvoiceCreate, ctx: Ctx = Depends(require(Perm.INVOICES_WRITE))) -> dict:
    return envelope(await ledger_service.create_invoice(ctx, data))


@router.get("/invoices")
async def list_invoices(customer_id: uuid.UUID | None = None, status: Literal["open", "paid", "void"] | None = None,
                        overdue: bool | None = None, number: str | None = Query(None, max_length=64),
                        page: Pagination = Depends(), ctx: Ctx = Depends(require(Perm.INVOICES_READ))) -> dict:
    items, total = await repo.list_invoices(ctx.db, ctx.business_id, ledger_service.today(ctx),
                                            customer_id=customer_id, status=status, overdue=overdue, number=number,
                                            offset=page.offset, limit=page.page_size)
    return envelope(items, **page.meta(total))


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: uuid.UUID, ctx: Ctx = Depends(require(Perm.INVOICES_READ))) -> dict:
    return envelope(await ledger_service.get_invoice(ctx, invoice_id))


@router.patch("/invoices/{invoice_id}")
async def patch_invoice(invoice_id: uuid.UUID, data: InvoicePatch,
                        ctx: Ctx = Depends(require(Perm.INVOICES_WRITE))) -> dict:
    return envelope(await ledger_service.update_invoice(ctx, invoice_id, data))


@router.get("/invoices/{invoice_id}/payments")
async def list_invoice_payments(invoice_id: uuid.UUID, page: Pagination = Depends(),
                                ctx: Ctx = Depends(require(Perm.PAYMENTS_READ))) -> dict:
    await ledger_service.get_invoice_row(ctx, invoice_id)
    items, total = await ledger_service.list_payments(ctx, invoice_id=invoice_id, offset=page.offset,
                                                      limit=page.page_size)
    return envelope([PaymentOut.model_validate(p) for p in items], **page.meta(total))


@router.post("/invoices/{invoice_id}/payments", status_code=202)
async def propose_payment(invoice_id: uuid.UUID, data: PaymentProposeIn,
                          ctx: Ctx = Depends(require(Perm.PAYMENTS_PROPOSE))) -> dict:
    """Payments are recorded only via a confirmed pending action."""
    await ledger_service.get_invoice_row(ctx, invoice_id)
    tool = get_tool("record_payment")
    tctx = action_service.tool_ctx(ctx, ctx.business.default_language)
    inp = tool.input_schema.model_validate({"invoice_id": invoice_id, "amount_paise": data.amount_paise,
                                            "paid_on": data.paid_on or tctx.today, "method": data.method})
    action = await action_service.propose(tctx, tool, inp, None)
    return envelope(ActionOut.model_validate(action))


@router.get("/payments")
async def list_payments(invoice_id: uuid.UUID | None = None, customer_id: uuid.UUID | None = None,
                        page: Pagination = Depends(), ctx: Ctx = Depends(require(Perm.PAYMENTS_READ))) -> dict:
    items, total = await ledger_service.list_payments(ctx, invoice_id=invoice_id, customer_id=customer_id,
                                                      offset=page.offset, limit=page.page_size)
    return envelope([PaymentOut.model_validate(p) for p in items], **page.meta(total))


# ---------------- reminders ----------------
ReminderStatus = Literal["scheduled", "due", "delivered", "failed", "cancelled", "completed"]


@router.post("/reminders", status_code=201)
async def create_reminder(data: ReminderCreate, ctx: Ctx = Depends(require(Perm.REMINDERS_WRITE))) -> dict:
    return envelope(ReminderOut.model_validate(await ledger_service.create_reminder(ctx, data)))


@router.get("/reminders")
async def list_reminders(status: ReminderStatus | None = None, customer_id: uuid.UUID | None = None,
                         invoice_id: uuid.UUID | None = None, upcoming: bool | None = None,
                         page: Pagination = Depends(), ctx: Ctx = Depends(require(Perm.REMINDERS_READ))) -> dict:
    items, total = await ledger_service.list_reminders(ctx, status=status, customer_id=customer_id,
                                                       invoice_id=invoice_id, upcoming=upcoming,
                                                       offset=page.offset, limit=page.page_size)
    return envelope([ReminderOut.model_validate(r) for r in items], **page.meta(total))


@router.get("/reminders/{reminder_id}")
async def get_reminder(reminder_id: uuid.UUID, ctx: Ctx = Depends(require(Perm.REMINDERS_READ))) -> dict:
    return envelope(ReminderOut.model_validate(await ledger_service.get_reminder(ctx, reminder_id)))


@router.patch("/reminders/{reminder_id}")
async def patch_reminder(reminder_id: uuid.UUID, data: ReminderPatch,
                         ctx: Ctx = Depends(require(Perm.REMINDERS_WRITE))) -> dict:
    return envelope(ReminderOut.model_validate(await ledger_service.update_reminder(ctx, reminder_id, data)))


@router.post("/reminders/{reminder_id}/cancel")
async def cancel_reminder(reminder_id: uuid.UUID, ctx: Ctx = Depends(require(Perm.REMINDERS_WRITE))) -> dict:
    return envelope(ReminderOut.model_validate(await ledger_service.cancel_reminder(ctx, reminder_id)))


@router.post("/reminders/{reminder_id}/complete")
async def complete_reminder(reminder_id: uuid.UUID, ctx: Ctx = Depends(require(Perm.REMINDERS_WRITE))) -> dict:
    return envelope(ReminderOut.model_validate(await ledger_service.complete_reminder(ctx, reminder_id)))


# ---------------- payment commitments ----------------
@router.post("/payment-commitments", status_code=201)
async def create_commitment(data: CommitmentCreate, ctx: Ctx = Depends(require(Perm.COMMITMENTS_WRITE))) -> dict:
    return envelope(CommitmentOut.model_validate(await ledger_service.create_commitment(ctx, data)))


@router.get("/payment-commitments")
async def list_commitments(status: Literal["open", "kept", "broken", "cancelled"] | None = None,
                           customer_id: uuid.UUID | None = None, page: Pagination = Depends(),
                           ctx: Ctx = Depends(require(Perm.COMMITMENTS_READ))) -> dict:
    items, total = await ledger_service.list_commitments(ctx, status=status, customer_id=customer_id,
                                                         offset=page.offset, limit=page.page_size)
    return envelope([CommitmentOut.model_validate(c) for c in items], **page.meta(total))


@router.get("/payment-commitments/{commitment_id}")
async def get_commitment(commitment_id: uuid.UUID, ctx: Ctx = Depends(require(Perm.COMMITMENTS_READ))) -> dict:
    return envelope(CommitmentOut.model_validate(await ledger_service.get_commitment(ctx, commitment_id)))


@router.patch("/payment-commitments/{commitment_id}")
async def patch_commitment(commitment_id: uuid.UUID, data: CommitmentPatch,
                           ctx: Ctx = Depends(require(Perm.COMMITMENTS_WRITE))) -> dict:
    return envelope(CommitmentOut.model_validate(await ledger_service.update_commitment(ctx, commitment_id, data)))


@router.delete("/payment-commitments/{commitment_id}")
async def delete_commitment(commitment_id: uuid.UUID, ctx: Ctx = Depends(require(Perm.COMMITMENTS_WRITE))) -> dict:
    return envelope(CommitmentOut.model_validate(await ledger_service.cancel_commitment(ctx, commitment_id)))
