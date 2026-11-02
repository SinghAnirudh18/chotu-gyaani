import uuid
from datetime import timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Ctx
from app.core.config import get_settings
from app.core.exceptions import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.permissions import Role
from app.core.security import hash_token, new_opaque_token
from app.db.models import (
    Agent,
    Business,
    BusinessMember,
    Conversation,
    Customer,
    Integration,
    Invitation,
    Invoice,
    Message,
    Payment,
    PaymentCommitment,
    Reminder,
    User,
)
from app.schemas.business import BusinessCreate, BusinessPatch
from app.services.audit import audit
from app.utils.dates import utcnow


async def create_business(db: AsyncSession, user: User, data: BusinessCreate) -> Business:
    b = Business(name=data.name.strip(), timezone=data.timezone, default_language=data.default_language)
    db.add(b)
    await db.flush()
    db.add(BusinessMember(business_id=b.id, user_id=user.id, role=Role.OWNER.value))
    audit(db, b.id, user.id, "business.created", entity_type="business", entity_id=b.id)
    await db.commit()
    await db.refresh(b)
    return b


async def update_business(ctx: Ctx, data: BusinessPatch) -> Business:
    b = ctx.business
    changed = data.model_dump(exclude_unset=True, exclude={"settings"})
    for k, v in changed.items():
        if v is not None:
            setattr(b, k, v)
    if data.settings is not None:
        b.settings = {**(b.settings or {}), **data.settings.model_dump(exclude_none=True)}
        changed["settings"] = b.settings
    audit(ctx.db, b.id, ctx.user_id, "business.updated", entity_type="business", entity_id=b.id,
          metadata={"fields": ",".join(sorted(changed))})
    await ctx.db.commit()
    await ctx.db.refresh(b)
    return b


async def delete_business(ctx: Ctx) -> None:
    """Deletion = archive + scrub personal data. Audit log is retained (append-only)."""
    db, bid = ctx.db, ctx.business_id
    await db.execute(update(Customer).where(Customer.business_id == bid).values(
        name="Deleted customer", name_normalized="deleted customer", phone_e164=None, email=None,
        notes=None, external_ref=None, archived_at=func.coalesce(Customer.archived_at, func.now())))
    conv_ids = select(Conversation.id).where(Conversation.business_id == bid)
    await db.execute(delete(Message).where(Message.conversation_id.in_(conv_ids)))
    await db.execute(delete(Integration).where(Integration.business_id == bid))
    await db.execute(update(Reminder).where(Reminder.business_id == bid, Reminder.status.in_(
        ["scheduled", "due"])).values(status="cancelled"))
    ctx.business.archived_at = utcnow()
    audit(db, bid, ctx.user_id, "business.deleted", entity_type="business", entity_id=bid)
    await db.commit()


async def export_business(ctx: Ctx) -> dict:
    db, bid = ctx.db, ctx.business_id

    async def rows(model, *cols):  # type: ignore[no-untyped-def]
        res = (await db.execute(select(model).where(model.business_id == bid))).scalars().all()
        return [{c: getattr(r, c) for c in cols} for r in res]

    data = {
        "business": {"id": ctx.business.id, "name": ctx.business.name, "timezone": ctx.business.timezone,
                     "default_language": ctx.business.default_language, "currency": ctx.business.currency},
        "customers": await rows(Customer, "id", "name", "phone_e164", "email", "external_ref", "notes",
                                "archived_at", "created_at"),
        "invoices": await rows(Invoice, "id", "customer_id", "number", "total_paise", "issued_on", "due_on",
                               "status", "description", "created_at"),
        "payments": await rows(Payment, "id", "invoice_id", "amount_paise", "paid_on", "method", "created_at"),
        "payment_commitments": await rows(PaymentCommitment, "id", "customer_id", "invoice_id",
                                          "promised_amount_paise", "promised_on", "status", "created_at"),
        "reminders": await rows(Reminder, "id", "customer_id", "invoice_id", "scheduled_at", "channel",
                                "status", "created_at"),
        "agents": await rows(Agent, "id", "name", "language", "instructions", "enabled_tools", "status"),
        "exported_at": utcnow(),
    }
    audit(db, bid, ctx.user_id, "business.exported", entity_type="business", entity_id=bid)
    await db.commit()
    return data


# ---------- members ----------
async def list_members(ctx: Ctx) -> list[dict]:
    rows = (await ctx.db.execute(
        select(BusinessMember, User).join(User, User.id == BusinessMember.user_id)
        .where(BusinessMember.business_id == ctx.business_id).order_by(BusinessMember.created_at)
    )).all()
    return [{"user_id": u.id, "email": u.email, "name": u.name, "role": m.role, "joined_at": m.created_at}
            for m, u in rows]


async def invite(ctx: Ctx, email: str, role: str) -> tuple[Invitation, str]:
    if role == Role.ADMIN and ctx.role != Role.OWNER:
        raise Forbidden("Only owners can invite admins")
    existing = (await ctx.db.execute(
        select(BusinessMember).join(User, User.id == BusinessMember.user_id)
        .where(BusinessMember.business_id == ctx.business_id, User.email == email.lower()))).scalar_one_or_none()
    if existing:
        raise Conflict("User is already a member", code="already_member")
    token = new_opaque_token()
    inv = Invitation(business_id=ctx.business_id, email=email.lower(), role=role, token_hash=hash_token(token),
                     invited_by=ctx.user_id,
                     expires_at=utcnow() + timedelta(days=get_settings().invitation_ttl_days))
    ctx.db.add(inv)
    await ctx.db.flush()
    audit(ctx.db, ctx.business_id, ctx.user_id, "member.invited", entity_type="invitation", entity_id=inv.id,
          metadata={"role": role})
    await ctx.db.commit()
    await ctx.db.refresh(inv)
    return inv, token


async def accept_invitation(db: AsyncSession, user: User, token: str) -> BusinessMember:
    inv = (await db.execute(select(Invitation).where(Invitation.token_hash == hash_token(token))
                            .with_for_update())).scalar_one_or_none()
    if inv is None or inv.accepted_at or inv.revoked_at or inv.expires_at <= utcnow():
        raise NotFound("Invitation not found or expired", code="invitation_invalid")
    if inv.email.lower() != user.email.lower():
        raise NotFound("Invitation not found or expired", code="invitation_invalid")
    existing = (await db.execute(select(BusinessMember).where(
        BusinessMember.business_id == inv.business_id, BusinessMember.user_id == user.id))).scalar_one_or_none()
    if existing:
        raise Conflict("Already a member", code="already_member")
    m = BusinessMember(business_id=inv.business_id, user_id=user.id, role=inv.role)
    db.add(m)
    inv.accepted_at = utcnow()
    audit(db, inv.business_id, user.id, "member.joined", entity_type="user", entity_id=user.id,
          metadata={"role": inv.role})
    await db.commit()
    return m


async def _get_member(ctx: Ctx, user_id: uuid.UUID) -> BusinessMember:
    m = (await ctx.db.execute(select(BusinessMember).where(
        BusinessMember.business_id == ctx.business_id, BusinessMember.user_id == user_id)
        .with_for_update())).scalar_one_or_none()
    if m is None:
        raise NotFound("Member not found")
    return m


async def _owner_count(ctx: Ctx) -> int:
    return (await ctx.db.execute(select(func.count()).select_from(BusinessMember).where(
        BusinessMember.business_id == ctx.business_id, BusinessMember.role == Role.OWNER.value))).scalar_one()


async def change_role(ctx: Ctx, user_id: uuid.UUID, role: str) -> BusinessMember:
    m = await _get_member(ctx, user_id)
    if ctx.role != Role.OWNER and (role in (Role.OWNER, Role.ADMIN) or m.role in (Role.OWNER, Role.ADMIN)):
        raise Forbidden("Only owners can change owner or admin roles")
    if m.role == Role.OWNER and role != Role.OWNER and await _owner_count(ctx) <= 1:
        raise ValidationFailed("A business must keep at least one owner", code="last_owner")
    old = m.role
    m.role = role
    audit(ctx.db, ctx.business_id, ctx.user_id, "member.role_changed", entity_type="user", entity_id=user_id,
          metadata={"from": old, "to": role})
    await ctx.db.commit()
    return m


async def remove_member(ctx: Ctx, user_id: uuid.UUID) -> None:
    m = await _get_member(ctx, user_id)
    if ctx.role != Role.OWNER and m.role in (Role.OWNER, Role.ADMIN):
        raise Forbidden("Only owners can remove owners or admins")
    if m.role == Role.OWNER and await _owner_count(ctx) <= 1:
        raise ValidationFailed("A business must keep at least one owner", code="last_owner")
    await ctx.db.delete(m)
    audit(ctx.db, ctx.business_id, ctx.user_id, "member.removed", entity_type="user", entity_id=user_id)
    await ctx.db.commit()
