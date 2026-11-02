import csv
import io
import uuid
from datetime import UTC, date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import Ctx
from app.core.exceptions import Conflict, NotFound, ValidationFailed
from app.db.models import Customer, Invoice, Payment, PaymentCommitment, Reminder
from app.repositories import ledger as repo
from app.schemas.ledger import (
    CommitmentCreate,
    CommitmentPatch,
    CustomerCreate,
    CustomerPatch,
    InvoiceCreate,
    InvoiceOut,
    InvoicePatch,
    ReminderCreate,
    ReminderPatch,
)
from app.services.audit import audit
from app.utils.dates import today_in, utcnow
from app.utils.phone import normalize_phone
from app.utils.text import normalize_name


def today(ctx: Ctx) -> date:
    return today_in(ctx.business.timezone)


# ---------- customers ----------
async def get_customer(ctx: Ctx, customer_id: uuid.UUID, *, include_archived: bool = True) -> Customer:
    c = (await ctx.db.execute(select(Customer).where(
        Customer.id == customer_id, Customer.business_id == ctx.business_id))).scalar_one_or_none()
    if c is None or (not include_archived and c.archived_at is not None):
        raise NotFound("Customer not found", code="customer_not_found")
    return c


async def create_customer(ctx: Ctx, data: CustomerCreate, *, commit: bool = True) -> Customer:
    c = Customer(business_id=ctx.business_id, name=data.name.strip(), name_normalized=normalize_name(data.name),
                 phone_e164=normalize_phone(data.phone), email=data.email, external_ref=data.external_ref,
                 notes=data.notes)
    ctx.db.add(c)
    await ctx.db.flush()
    audit(ctx.db, ctx.business_id, ctx.user_id, "customer.created", entity_type="customer", entity_id=c.id)
    if commit:
        await ctx.db.commit()
        await ctx.db.refresh(c)
    return c


async def list_customers(ctx: Ctx, *, q: str | None, phone: str | None, include_archived: bool,
                         offset: int, limit: int) -> tuple[list[Customer], int]:
    if q:
        cands = await repo.search_customers(ctx.db, ctx.business_id, q, limit=offset + limit,
                                            include_archived=include_archived)
        found = [c.customer for c in cands]
        return found[offset:offset + limit], len(found)
    stmt = select(Customer).where(Customer.business_id == ctx.business_id)
    if not include_archived:
        stmt = stmt.where(Customer.archived_at.is_(None))
    if phone:
        stmt = stmt.where(Customer.phone_e164 == normalize_phone(phone))
    total = (await ctx.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await ctx.db.execute(stmt.order_by(Customer.name).offset(offset).limit(limit))).scalars().all()
    return list(rows), total


async def update_customer(ctx: Ctx, customer_id: uuid.UUID, data: CustomerPatch) -> Customer:
    c = await get_customer(ctx, customer_id, include_archived=False)
    fields = data.model_dump(exclude_unset=True)
    if "name" in fields and data.name:
        c.name = data.name.strip()
        c.name_normalized = normalize_name(data.name)
    if "phone" in fields:
        c.phone_e164 = normalize_phone(data.phone)
    for k in ("email", "external_ref", "notes"):
        if k in fields:
            setattr(c, k, fields[k])
    audit(ctx.db, ctx.business_id, ctx.user_id, "customer.updated", entity_type="customer", entity_id=c.id,
          metadata={"fields": ",".join(sorted(fields))})
    await ctx.db.commit()
    await ctx.db.refresh(c)
    return c


async def archive_customer(ctx: Ctx, customer_id: uuid.UUID) -> Customer:
    c = await get_customer(ctx, customer_id, include_archived=False)
    c.archived_at = utcnow()
    audit(ctx.db, ctx.business_id, ctx.user_id, "customer.archived", entity_type="customer", entity_id=c.id)
    await ctx.db.commit()
    await ctx.db.refresh(c)
    return c


async def import_customers_csv(ctx: Ctx, raw: bytes, dry_run: bool) -> dict:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise ValidationFailed("CSV must be UTF-8", code="invalid_csv") from e
    reader = csv.DictReader(io.StringIO(text))
    headers = [h.strip().lower() for h in (reader.fieldnames or [])]
    if "name" not in headers:
        raise ValidationFailed("CSV must have a 'name' column", code="invalid_csv",
                               details={"headers": headers})
    valid: list[dict] = []
    errors: list[dict] = []
    seen_phones: set[str] = set()
    for idx, row in enumerate(reader, start=2):
        if idx > 5001:
            errors.append({"row": idx, "error": "row limit (5000) exceeded"})
            break
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        try:
            data = CustomerCreate(name=row.get("name", ""), phone=row.get("phone") or None,
                                  email=row.get("email") or None, external_ref=row.get("external_ref") or None,
                                  notes=row.get("notes") or None)
            phone = normalize_phone(data.phone)
        except ValidationFailed as e:
            errors.append({"row": idx, "error": e.message})
            continue
        except ValueError as e:
            errors.append({"row": idx, "error": str(e).splitlines()[0]})
            continue
        if phone and phone in seen_phones:
            errors.append({"row": idx, "error": "duplicate phone in file"})
            continue
        if phone:
            seen_phones.add(phone)
            dup = (await ctx.db.execute(select(Customer.id).where(
                Customer.business_id == ctx.business_id, Customer.phone_e164 == phone,
                Customer.archived_at.is_(None)))).first()
            if dup:
                errors.append({"row": idx, "error": "customer with this phone already exists"})
                continue
        valid.append({"row": idx, "name": data.name, "phone_e164": phone, "email": data.email,
                      "external_ref": data.external_ref, "notes": data.notes})
    created = 0
    if not dry_run and valid:
        for v in valid:
            ctx.db.add(Customer(business_id=ctx.business_id, name=v["name"].strip(),
                                name_normalized=normalize_name(v["name"]), phone_e164=v["phone_e164"],
                                email=v["email"], external_ref=v["external_ref"], notes=v["notes"]))
            created += 1
        audit(ctx.db, ctx.business_id, ctx.user_id, "customer.imported", entity_type="customer",
              metadata={"created": created, "errors": len(errors)})
        await ctx.db.commit()
    return {"dry_run": dry_run, "valid_count": len(valid), "error_count": len(errors), "created": created,
            "preview": [{k: v for k, v in r.items() if k != "notes"} for r in valid[:50]], "errors": errors}


# ---------- invoices ----------
async def get_invoice_row(ctx: Ctx, invoice_id: uuid.UUID, *, lock: bool = False) -> Invoice:
    stmt = select(Invoice).where(Invoice.id == invoice_id, Invoice.business_id == ctx.business_id)
    if lock:
        stmt = stmt.with_for_update()
    inv = (await ctx.db.execute(stmt)).scalar_one_or_none()
    if inv is None:
        raise NotFound("Invoice not found", code="invoice_not_found")
    return inv


async def get_invoice(ctx: Ctx, invoice_id: uuid.UUID) -> InvoiceOut:
    out = await repo.get_invoice_with_balance(ctx.db, ctx.business_id, invoice_id, today(ctx))
    if out is None:
        raise NotFound("Invoice not found", code="invoice_not_found")
    return out


async def create_invoice(ctx: Ctx, data: InvoiceCreate) -> InvoiceOut:
    await get_customer(ctx, data.customer_id, include_archived=False)
    if data.due_on < data.issued_on:
        raise ValidationFailed("due_on must be on or after issued_on", code="invalid_dates")
    inv = Invoice(business_id=ctx.business_id, customer_id=data.customer_id, number=data.number.strip(),
                  total_paise=data.total_paise, issued_on=data.issued_on, due_on=data.due_on,
                  description=data.description, status="open")
    ctx.db.add(inv)
    try:
        await ctx.db.flush()
    except IntegrityError as e:
        await ctx.db.rollback()
        raise Conflict("Invoice number already exists", code="invoice_number_taken") from e
    audit(ctx.db, ctx.business_id, ctx.user_id, "invoice.created", entity_type="invoice", entity_id=inv.id,
          metadata={"total_paise": inv.total_paise})
    await ctx.db.commit()
    return await get_invoice(ctx, inv.id)


async def update_invoice(ctx: Ctx, invoice_id: uuid.UUID, data: InvoicePatch) -> InvoiceOut:
    inv = await get_invoice_row(ctx, invoice_id, lock=True)
    fields = data.model_dump(exclude_unset=True)
    paid = (await ctx.db.execute(select(func.coalesce(func.sum(Payment.amount_paise), 0)).where(
        Payment.invoice_id == inv.id))).scalar_one()
    if inv.status == "void":
        raise Conflict("Void invoices cannot be changed", code="invoice_void")
    if "total_paise" in fields and data.total_paise is not None:
        if data.total_paise < paid:
            raise ValidationFailed("Total cannot be less than amount already paid", code="total_below_paid")
        inv.total_paise = data.total_paise
    for k in ("issued_on", "due_on", "description"):
        if k in fields and (fields[k] is not None or k == "description"):
            setattr(inv, k, fields[k])
    if inv.due_on < inv.issued_on:
        raise ValidationFailed("due_on must be on or after issued_on", code="invalid_dates")
    if data.status == "void":
        if paid > 0:
            raise Conflict("Invoices with payments cannot be voided", code="invoice_has_payments")
        inv.status = "void"
    elif inv.status != "void":
        inv.status = "paid" if paid >= inv.total_paise else "open"
    audit(ctx.db, ctx.business_id, ctx.user_id, "invoice.updated", entity_type="invoice", entity_id=inv.id,
          metadata={"fields": ",".join(sorted(fields))})
    await ctx.db.commit()
    return await get_invoice(ctx, inv.id)


async def list_payments(ctx: Ctx, *, invoice_id: uuid.UUID | None = None, customer_id: uuid.UUID | None = None,
                        offset: int = 0, limit: int = 20) -> tuple[list[Payment], int]:
    stmt = select(Payment).where(Payment.business_id == ctx.business_id)
    if invoice_id:
        stmt = stmt.where(Payment.invoice_id == invoice_id)
    if customer_id:
        stmt = stmt.join(Invoice, Invoice.id == Payment.invoice_id).where(Invoice.customer_id == customer_id)
    total = (await ctx.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    items = (await ctx.db.execute(stmt.order_by(Payment.paid_on.desc(), Payment.created_at.desc())
                                  .offset(offset).limit(limit))).scalars().all()
    return list(items), total


# ---------- reminders ----------
async def get_reminder(ctx: Ctx, reminder_id: uuid.UUID, *, lock: bool = False) -> Reminder:
    stmt = select(Reminder).where(Reminder.id == reminder_id, Reminder.business_id == ctx.business_id)
    if lock:
        stmt = stmt.with_for_update()
    r = (await ctx.db.execute(stmt)).scalar_one_or_none()
    if r is None:
        raise NotFound("Reminder not found", code="reminder_not_found")
    return r


def _aware(dt):  # type: ignore[no-untyped-def]
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


async def create_reminder(ctx: Ctx, data: ReminderCreate) -> Reminder:
    await get_customer(ctx, data.customer_id, include_archived=False)
    if data.invoice_id:
        inv = await get_invoice_row(ctx, data.invoice_id)
        if inv.customer_id != data.customer_id:
            raise ValidationFailed("Invoice does not belong to this customer", code="invoice_customer_mismatch")
    when = _aware(data.scheduled_at)
    if when <= utcnow():
        raise ValidationFailed("scheduled_at must be in the future", code="date_in_past")
    r = Reminder(business_id=ctx.business_id, customer_id=data.customer_id, invoice_id=data.invoice_id,
                 scheduled_at=when, channel=data.channel, message=data.message, creation_source="api",
                 status="scheduled")
    ctx.db.add(r)
    await ctx.db.flush()
    audit(ctx.db, ctx.business_id, ctx.user_id, "reminder.created", entity_type="reminder", entity_id=r.id)
    await ctx.db.commit()
    await ctx.db.refresh(r)
    return r


async def list_reminders(ctx: Ctx, *, status: str | None, customer_id: uuid.UUID | None,
                         invoice_id: uuid.UUID | None, upcoming: bool | None,
                         offset: int, limit: int) -> tuple[list[Reminder], int]:
    stmt = select(Reminder).where(Reminder.business_id == ctx.business_id)
    if status:
        stmt = stmt.where(Reminder.status == status)
    if customer_id:
        stmt = stmt.where(Reminder.customer_id == customer_id)
    if invoice_id:
        stmt = stmt.where(Reminder.invoice_id == invoice_id)
    if upcoming:
        stmt = stmt.where(Reminder.status == "scheduled", Reminder.scheduled_at > utcnow())
    total = (await ctx.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    items = (await ctx.db.execute(stmt.order_by(Reminder.scheduled_at.asc()).offset(offset).limit(limit)
                                  )).scalars().all()
    return list(items), total


async def update_reminder(ctx: Ctx, reminder_id: uuid.UUID, data: ReminderPatch) -> Reminder:
    r = await get_reminder(ctx, reminder_id, lock=True)
    if r.status != "scheduled":
        raise Conflict("Only scheduled reminders can be changed", code="reminder_not_editable")
    fields = data.model_dump(exclude_unset=True)
    if data.scheduled_at is not None:
        when = _aware(data.scheduled_at)
        if when <= utcnow():
            raise ValidationFailed("scheduled_at must be in the future", code="date_in_past")
        r.scheduled_at = when
    if data.channel is not None:
        r.channel = data.channel
    if "message" in fields:
        r.message = data.message
    audit(ctx.db, ctx.business_id, ctx.user_id, "reminder.updated", entity_type="reminder", entity_id=r.id,
          metadata={"fields": ",".join(sorted(fields))})
    await ctx.db.commit()
    await ctx.db.refresh(r)
    return r


async def cancel_reminder(ctx: Ctx, reminder_id: uuid.UUID) -> Reminder:
    r = await get_reminder(ctx, reminder_id, lock=True)
    if r.status not in ("scheduled", "due"):
        raise Conflict(f"Reminder is already {r.status}", code="reminder_not_cancellable")
    r.status = "cancelled"
    audit(ctx.db, ctx.business_id, ctx.user_id, "reminder.cancelled", entity_type="reminder", entity_id=r.id)
    await ctx.db.commit()
    await ctx.db.refresh(r)
    return r


async def complete_reminder(ctx: Ctx, reminder_id: uuid.UUID) -> Reminder:
    r = await get_reminder(ctx, reminder_id, lock=True)
    if r.status not in ("scheduled", "due", "failed"):
        raise Conflict(f"Reminder is already {r.status}", code="reminder_not_completable")
    r.status = "completed"
    r.completed_at = utcnow()
    audit(ctx.db, ctx.business_id, ctx.user_id, "reminder.completed", entity_type="reminder", entity_id=r.id)
    await ctx.db.commit()
    await ctx.db.refresh(r)
    return r


# ---------- commitments (never touch payments or invoice status) ----------
async def get_commitment(ctx: Ctx, cid: uuid.UUID) -> PaymentCommitment:
    c = (await ctx.db.execute(select(PaymentCommitment).where(
        PaymentCommitment.id == cid, PaymentCommitment.business_id == ctx.business_id))).scalar_one_or_none()
    if c is None:
        raise NotFound("Payment commitment not found", code="commitment_not_found")
    return c


async def create_commitment(ctx: Ctx, data: CommitmentCreate) -> PaymentCommitment:
    await get_customer(ctx, data.customer_id, include_archived=False)
    if data.invoice_id:
        inv = await get_invoice_row(ctx, data.invoice_id)
        if inv.customer_id != data.customer_id:
            raise ValidationFailed("Invoice does not belong to this customer", code="invoice_customer_mismatch")
    if data.promised_on < today(ctx):
        raise ValidationFailed("promised_on cannot be in the past", code="date_in_past")
    c = PaymentCommitment(business_id=ctx.business_id, customer_id=data.customer_id, invoice_id=data.invoice_id,
                          promised_amount_paise=data.promised_amount_paise, promised_on=data.promised_on,
                          notes=data.notes, status="open")
    ctx.db.add(c)
    await ctx.db.flush()
    audit(ctx.db, ctx.business_id, ctx.user_id, "commitment.created", entity_type="payment_commitment",
          entity_id=c.id)
    await ctx.db.commit()
    await ctx.db.refresh(c)
    return c


async def list_commitments(ctx: Ctx, *, status: str | None, customer_id: uuid.UUID | None,
                           offset: int, limit: int) -> tuple[list[PaymentCommitment], int]:
    stmt = select(PaymentCommitment).where(PaymentCommitment.business_id == ctx.business_id)
    if status:
        stmt = stmt.where(PaymentCommitment.status == status)
    if customer_id:
        stmt = stmt.where(PaymentCommitment.customer_id == customer_id)
    total = (await ctx.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    items = (await ctx.db.execute(stmt.order_by(PaymentCommitment.promised_on.asc()).offset(offset)
                                  .limit(limit))).scalars().all()
    return list(items), total


async def update_commitment(ctx: Ctx, cid: uuid.UUID, data: CommitmentPatch) -> PaymentCommitment:
    c = await get_commitment(ctx, cid)
    fields = data.model_dump(exclude_unset=True)
    if c.status == "cancelled":
        raise Conflict("Cancelled commitments cannot be changed", code="commitment_cancelled")
    for k in ("promised_amount_paise", "promised_on", "status", "notes"):
        if k in fields:
            setattr(c, k, fields[k])
    audit(ctx.db, ctx.business_id, ctx.user_id, "commitment.updated", entity_type="payment_commitment",
          entity_id=c.id, metadata={"fields": ",".join(sorted(fields))})
    await ctx.db.commit()
    await ctx.db.refresh(c)
    return c


async def cancel_commitment(ctx: Ctx, cid: uuid.UUID) -> PaymentCommitment:
    c = await get_commitment(ctx, cid)
    c.status = "cancelled"
    audit(ctx.db, ctx.business_id, ctx.user_id, "commitment.cancelled", entity_type="payment_commitment",
          entity_id=c.id)
    await ctx.db.commit()
    await ctx.db.refresh(c)
    return c


async def customers_by_ids(ctx: Ctx, ids: set[uuid.UUID]) -> dict[uuid.UUID, Customer]:
    if not ids:
        return {}
    rows = (await ctx.db.execute(select(Customer).where(Customer.business_id == ctx.business_id,
                                                        Customer.id.in_(ids)))).scalars().all()
    return {c.id: c for c in rows}


