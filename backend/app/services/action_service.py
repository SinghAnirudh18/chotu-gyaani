"""Pending action state machine.

pending_confirmation -> processing -> completed | failed
pending_confirmation -> cancelled | expired

Transitions are enforced with conditional UPDATEs; the effect rows carry a
unique source_action_id so a double execution fails at the database."""
import logging
import uuid
from datetime import timedelta

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Ctx
from app.core.config import get_settings
from app.core.exceptions import AppError, Conflict, Forbidden, Gone, NotFound, ValidationFailed
from app.core.logging import log_event
from app.core.permissions import Perm
from app.db.models import Conversation, Message, PendingAction
from app.services.audit import audit
from app.tools.registry import Tool, ToolContext, get_tool
from app.utils.dates import today_in, utcnow
from app.utils.i18n import t

logger = logging.getLogger(__name__)


def tool_ctx(ctx: Ctx, language: str) -> ToolContext:
    now = utcnow()
    return ToolContext(db=ctx.db, business=ctx.business, user_id=ctx.user_id, role=ctx.role, language=language,
                       today=today_in(ctx.business.timezone, now), now=now)


async def propose(tctx: ToolContext, tool: Tool, inp: BaseModel, conversation_id: uuid.UUID | None,
                  *, commit: bool = True) -> PendingAction:
    preview = await tool.preview(tctx, inp)
    action = PendingAction(
        business_id=tctx.business_id, conversation_id=conversation_id, user_id=tctx.user_id, type=tool.name,
        payload=inp.model_dump(mode="json"), preview=preview, status="pending_confirmation",
        expires_at=utcnow() + timedelta(minutes=get_settings().action_ttl_minutes),
    )
    tctx.db.add(action)
    await tctx.db.flush()
    audit(tctx.db, tctx.business_id, tctx.user_id, "action.proposed", entity_type="pending_action",
          entity_id=action.id, metadata={"type": tool.name})
    if commit:
        await tctx.db.commit()
        await tctx.db.refresh(action)
    return action


async def get_action(ctx: Ctx, action_id: uuid.UUID) -> PendingAction:
    a = (await ctx.db.execute(select(PendingAction).where(
        PendingAction.id == action_id, PendingAction.business_id == ctx.business_id)
        .execution_options(populate_existing=True))).scalar_one_or_none()
    if a is None:
        raise NotFound("Action not found", code="action_not_found")
    return a


async def list_actions(ctx: Ctx, *, status: str | None, type_: str | None, conversation_id: uuid.UUID | None,
                       offset: int, limit: int) -> tuple[list[PendingAction], int]:
    await expire_due(ctx.db, business_id=ctx.business_id)
    stmt = select(PendingAction).where(PendingAction.business_id == ctx.business_id)
    if not ctx.can(Perm.CONVERSATIONS_READ_ALL):
        stmt = stmt.where(PendingAction.user_id == ctx.user_id)
    if status:
        stmt = stmt.where(PendingAction.status == status)
    if type_:
        stmt = stmt.where(PendingAction.type == type_)
    if conversation_id:
        stmt = stmt.where(PendingAction.conversation_id == conversation_id)
    total = (await ctx.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    items = (await ctx.db.execute(stmt.order_by(PendingAction.created_at.desc()).offset(offset).limit(limit)
                                  )).scalars().all()
    return list(items), total


async def _conversation_language(db: AsyncSession, action: PendingAction, fallback: str) -> str:
    if action.conversation_id:
        conv = await db.get(Conversation, action.conversation_id)
        if conv and conv.language:
            return conv.language
    return fallback


async def _handled_error(ctx: Ctx, action_id: uuid.UUID) -> AppError:
    # The conditional UPDATE matched nothing, so there is nothing to roll back.
    a = await get_action(ctx, action_id)
    if a.status == "pending_confirmation" and a.expires_at <= utcnow():
        await expire_due(ctx.db, business_id=ctx.business_id)
        return Gone("This action has expired", code="action_expired")
    if a.status == "expired":
        return Gone("This action has expired", code="action_expired")
    return Conflict("This action was already handled", code="action_already_handled",
                    details={"status": a.status})


async def confirm(ctx: Ctx, action_id: uuid.UUID) -> PendingAction:
    action = await get_action(ctx, action_id)
    tool = get_tool(action.type)
    if tool.confirm_perm is not None and not ctx.can(tool.confirm_perm):
        raise Forbidden(details={"permission": tool.confirm_perm.value})

    claimed = (await ctx.db.execute(
        update(PendingAction)
        .where(PendingAction.id == action_id, PendingAction.business_id == ctx.business_id,
               PendingAction.status == "pending_confirmation", PendingAction.expires_at > func.now())
        .values(status="processing", confirmed_by=ctx.user_id, updated_at=func.now())
        .returning(PendingAction.id)
    )).scalar_one_or_none()
    if claimed is None:
        raise await _handled_error(ctx, action_id)

    action = await get_action(ctx, action_id)
    lang = await _conversation_language(ctx.db, action, ctx.business.default_language)
    tctx = tool_ctx(ctx, lang)
    try:
        inp = tool.input_schema.model_validate(action.payload)
        async with ctx.db.begin_nested():
            result = await tool.execute(tctx, inp, action.id)
    except (AppError, ValidationError, IntegrityError) as e:
        code = e.code if isinstance(e, AppError) else ("duplicate_effect" if isinstance(e, IntegrityError)
                                                        else "invalid_payload")
        message = e.message if isinstance(e, AppError) else "Action could not be executed"
        await ctx.db.execute(update(PendingAction).where(PendingAction.id == action.id).values(
            status="failed", error=code, updated_at=func.now()))
        audit(ctx.db, ctx.business_id, ctx.user_id, "action.failed", entity_type="pending_action",
              entity_id=action.id, outcome="failure", metadata={"type": tool.name, "error": code})
        await ctx.db.commit()
        log_event(logger, "action_failed", action_type=tool.name, error=code)
        raise ValidationFailed(message, code="action_failed", details={"reason": code,
                                                                        "action_id": str(action.id)}) from e

    await ctx.db.execute(update(PendingAction).where(PendingAction.id == action.id).values(
        status="completed", result=result, updated_at=func.now()))
    audit(ctx.db, ctx.business_id, ctx.user_id, tool.audit_event, entity_type=result.get("entity_type"),
          entity_id=uuid.UUID(result["entity_id"]) if result.get("entity_id") else None,
          metadata={"action_id": str(action.id), "source": "assistant"})
    audit(ctx.db, ctx.business_id, ctx.user_id, "action.confirmed", entity_type="pending_action",
          entity_id=action.id, metadata={"type": tool.name})
    if action.conversation_id:
        ctx.db.add(Message(conversation_id=action.conversation_id, role="assistant", language=lang,
                           content=t("confirmed", lang, summary=result.get("summary", "")),
                           tool_metadata={"action_id": str(action.id), "status": "completed"}))
    await ctx.db.commit()
    return await get_action(ctx, action_id)


async def cancel(ctx: Ctx, action_id: uuid.UUID) -> PendingAction:
    action = await get_action(ctx, action_id)
    if action.user_id != ctx.user_id and not ctx.can(Perm.CONVERSATIONS_READ_ALL):
        raise Forbidden()
    done = (await ctx.db.execute(
        update(PendingAction)
        .where(PendingAction.id == action_id, PendingAction.business_id == ctx.business_id,
               PendingAction.status == "pending_confirmation", PendingAction.expires_at > func.now())
        .values(status="cancelled", updated_at=func.now()).returning(PendingAction.id)
    )).scalar_one_or_none()
    if done is None:
        raise await _handled_error(ctx, action_id)
    audit(ctx.db, ctx.business_id, ctx.user_id, "action.cancelled", entity_type="pending_action",
          entity_id=action_id, metadata={"type": action.type})
    if action.conversation_id:
        lang = await _conversation_language(ctx.db, action, ctx.business.default_language)
        ctx.db.add(Message(conversation_id=action.conversation_id, role="assistant", language=lang,
                           content=t("cancelled", lang),
                           tool_metadata={"action_id": str(action_id), "status": "cancelled"}))
    await ctx.db.commit()
    return await get_action(ctx, action_id)


async def expire_due(db: AsyncSession, *, business_id: uuid.UUID | None = None) -> int:
    stmt = (update(PendingAction)
            .where(PendingAction.status == "pending_confirmation", PendingAction.expires_at <= func.now())
            .values(status="expired", updated_at=func.now())
            .returning(PendingAction.id, PendingAction.business_id, PendingAction.type))
    if business_id is not None:
        stmt = stmt.where(PendingAction.business_id == business_id)
    rows = (await db.execute(stmt)).all()
    for aid, bid, typ in rows:
        audit(db, bid, None, "action.expired", entity_type="pending_action", entity_id=aid,
              metadata={"type": typ})
    await db.commit()
    return len(rows)
