import base64
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import func, select

from app.api.deps import Ctx, require
from app.core.exceptions import NotFound, ValidationFailed
from app.core.permissions import Perm
from app.db.models import ActionLog, Agent, Conversation, Message
from app.providers.stt import get_stt
from app.providers.tts import get_tts
from app.repositories import ledger as repo
from app.schemas.assistant import ActionOut, ConversationCreate, ConversationOut, MessageIn, MessageOut
from app.schemas.common import Pagination, envelope
from app.schemas.ledger import ReminderOut
from app.services import action_service, ledger_service, usage
from app.services.pipeline import process_user_message
from app.utils.audio import validate_audio
from app.utils.dates import utcnow
from app.utils.i18n import normalize_lang

router = APIRouter(tags=["assistant"])


# ---------------- conversations ----------------
async def _get_conversation(ctx: Ctx, conversation_id: uuid.UUID, *, for_write: bool = False) -> Conversation:
    conv = (await ctx.db.execute(select(Conversation).where(
        Conversation.id == conversation_id, Conversation.business_id == ctx.business_id))).scalar_one_or_none()
    if conv is None:
        raise NotFound("Conversation not found", code="conversation_not_found")
    if conv.user_id != ctx.user_id and (for_write or not ctx.can(Perm.CONVERSATIONS_READ_ALL)):
        raise NotFound("Conversation not found", code="conversation_not_found")
    return conv


def _message_payload(conv: Conversation, result: dict) -> dict:
    o = result["outcome"]
    return {
        "conversation_id": conv.id,
        "user_message": MessageOut.model_validate(result["user_message"]) if result["user_message"] else None,
        "assistant_message": MessageOut.model_validate(result["assistant_message"])
        if result["assistant_message"] else None,
        "reply": o.reply,
        "language": o.language,
        "intent": o.intent,
        "tool": o.tool,
        "result": o.data,
        "action": ActionOut.model_validate(o.action) if o.action is not None else None,
        "clarification": o.clarification,
        "providers": {"llm": result["llm_provider"]},
    }


@router.post("/conversations", status_code=201)
async def create_conversation(data: ConversationCreate, ctx: Ctx = Depends(require(Perm.CONVERSATIONS_USE))) -> dict:
    if data.agent_id:
        agent = (await ctx.db.execute(select(Agent).where(Agent.id == data.agent_id,
                                                          Agent.business_id == ctx.business_id))).scalar_one_or_none()
        if agent is None:
            raise NotFound("Agent not found", code="agent_not_found")
        if agent.status != "active":
            raise ValidationFailed("Agent is not active", code="agent_not_active")
    conv = Conversation(business_id=ctx.business_id, user_id=ctx.user_id, agent_id=data.agent_id, title=data.title,
                        language=data.language or ctx.business.default_language, state={}, is_test=False)
    ctx.db.add(conv)
    await ctx.db.commit()
    await ctx.db.refresh(conv)
    return envelope(ConversationOut.model_validate(conv))


@router.get("/conversations")
async def list_conversations(page: Pagination = Depends(), ctx: Ctx = Depends(require(Perm.CONVERSATIONS_USE))) -> dict:
    stmt = select(Conversation).where(Conversation.business_id == ctx.business_id, Conversation.is_test.is_(False))
    if not ctx.can(Perm.CONVERSATIONS_READ_ALL):
        stmt = stmt.where(Conversation.user_id == ctx.user_id)
    total = (await ctx.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    items = (await ctx.db.execute(stmt.order_by(Conversation.updated_at.desc()).offset(page.offset)
                                  .limit(page.page_size))).scalars().all()
    return envelope([ConversationOut.model_validate(c) for c in items], **page.meta(total))


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: uuid.UUID, ctx: Ctx = Depends(require(Perm.CONVERSATIONS_USE))) -> dict:
    conv = await _get_conversation(ctx, conversation_id)
    data = ConversationOut.model_validate(conv).model_dump(mode="json")
    data["awaiting"] = (conv.state or {}).get("awaiting", {}).get("slot") if conv.state else None
    return envelope(data)


@router.post("/conversations/{conversation_id}/messages")
async def post_message(conversation_id: uuid.UUID, data: MessageIn,
                       ctx: Ctx = Depends(require(Perm.CONVERSATIONS_USE))) -> dict:
    conv = await _get_conversation(ctx, conversation_id, for_write=True)
    await usage.consume(ctx.db, ctx.business_id, "assistant_messages")
    result = await process_user_message(ctx, conv, data.content, data.language, source="text")
    return envelope(_message_payload(conv, result))


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: uuid.UUID, page: Pagination = Depends(),
                        ctx: Ctx = Depends(require(Perm.CONVERSATIONS_USE))) -> dict:
    conv = await _get_conversation(ctx, conversation_id)
    stmt = select(Message).where(Message.conversation_id == conv.id)
    total = (await ctx.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    items = (await ctx.db.execute(stmt.order_by(Message.created_at.asc(), Message.id).offset(page.offset)
                                  .limit(page.page_size))).scalars().all()
    return envelope([MessageOut.model_validate(m) for m in items], **page.meta(total))


@router.post("/conversations/{conversation_id}/messages/audio")
async def post_audio_message(conversation_id: uuid.UUID, file: UploadFile = File(...),
                             language: Literal["en", "hi", "hi-Latn"] | None = Form(None),
                             include_speech: bool = Form(False),
                             ctx: Ctx = Depends(require(Perm.AUDIO_USE))) -> dict:
    ctx.require(Perm.CONVERSATIONS_USE)
    conv = await _get_conversation(ctx, conversation_id, for_write=True)
    audio = await file.read()
    meta = validate_audio(audio, file.content_type)
    await usage.consume(ctx.db, ctx.business_id, "audio_requests")
    await usage.consume(ctx.db, ctx.business_id, "assistant_messages")
    stt = get_stt()
    transcript = await stt.transcribe(audio, language)
    del audio  # raw audio is never persisted
    result = await process_user_message(ctx, conv, transcript.text, language or transcript.language, source="audio")
    payload = _message_payload(conv, result)
    payload["transcript"] = {"text": transcript.text, "language": transcript.language,
                             "confidence": transcript.confidence, "provider": transcript.provider,
                             "mock": transcript.provider == "mock", "audio": meta}
    payload["providers"]["stt"] = transcript.provider
    if include_speech:
        speech = await get_tts().synthesize(payload["reply"], normalize_lang(payload["language"]), None)
        payload["speech"] = {"mime_type": speech.mime_type, "provider": speech.provider,
                             "duration_seconds": speech.duration_seconds,
                             "audio_base64": base64.b64encode(speech.audio).decode()}
        payload["providers"]["tts"] = speech.provider
    return envelope(payload)


# ---------------- actions ----------------
ActionStatus = Literal["pending_confirmation", "processing", "completed", "failed", "cancelled", "expired"]


@router.get("/actions")
async def list_actions(status: ActionStatus | None = None, type: str | None = None,
                       conversation_id: uuid.UUID | None = None, page: Pagination = Depends(),
                       ctx: Ctx = Depends(require(Perm.ACTIONS_READ))) -> dict:
    items, total = await action_service.list_actions(ctx, status=status, type_=type, conversation_id=conversation_id,
                                                     offset=page.offset, limit=page.page_size)
    return envelope([ActionOut.model_validate(a) for a in items], **page.meta(total))


@router.get("/actions/{action_id}")
async def get_action(action_id: uuid.UUID, ctx: Ctx = Depends(require(Perm.ACTIONS_READ))) -> dict:
    a = await action_service.get_action(ctx, action_id)
    if a.status == "pending_confirmation" and a.expires_at <= utcnow():
        await action_service.expire_due(ctx.db, business_id=ctx.business_id)
        a = await action_service.get_action(ctx, action_id)
    return envelope(ActionOut.model_validate(a))


@router.post("/actions/{action_id}/confirm")
async def confirm_action(action_id: uuid.UUID, ctx: Ctx = Depends(require(Perm.ACTIONS_READ))) -> dict:
    return envelope(ActionOut.model_validate(await action_service.confirm(ctx, action_id)))


@router.post("/actions/{action_id}/cancel")
async def cancel_action(action_id: uuid.UUID, ctx: Ctx = Depends(require(Perm.ACTIONS_CANCEL))) -> dict:
    return envelope(ActionOut.model_validate(await action_service.cancel(ctx, action_id)))


# ---------------- dashboard ----------------
@router.get("/dashboard/summary")
async def dashboard_summary(ctx: Ctx = Depends(require(Perm.DASHBOARD_READ))) -> dict:
    today = ledger_service.today(ctx)
    data = await repo.dashboard_summary(ctx.db, ctx.business_id, today, utcnow(), today.replace(day=1))
    return envelope(data, currency=ctx.business.currency, as_of=today.isoformat())


@router.get("/dashboard/activity")
async def dashboard_activity(page: Pagination = Depends(), ctx: Ctx = Depends(require(Perm.DASHBOARD_READ))) -> dict:
    stmt = select(ActionLog).where(ActionLog.business_id == ctx.business_id,
                                   ActionLog.action_type.not_like("tool.%"))
    total = (await ctx.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await ctx.db.execute(stmt.order_by(ActionLog.created_at.desc()).offset(page.offset)
                                 .limit(page.page_size))).scalars().all()
    return envelope([_log_out(r) for r in rows], **page.meta(total))


@router.get("/dashboard/upcoming-reminders")
async def dashboard_upcoming(page: Pagination = Depends(), ctx: Ctx = Depends(require(Perm.DASHBOARD_READ))) -> dict:
    items, total = await ledger_service.list_reminders(ctx, status=None, customer_id=None, invoice_id=None,
                                                       upcoming=True, offset=page.offset, limit=page.page_size)
    names = await ledger_service.customers_by_ids(ctx, {r.customer_id for r in items})
    data = [ReminderOut.model_validate(r).model_dump(mode="json") | {
        "customer_name": names[r.customer_id].name if r.customer_id in names else None} for r in items]
    return envelope(data, **page.meta(total))


@router.get("/dashboard/overdue-invoices")
async def dashboard_overdue(page: Pagination = Depends(), ctx: Ctx = Depends(require(Perm.DASHBOARD_READ))) -> dict:
    items, total = await repo.list_invoices(ctx.db, ctx.business_id, ledger_service.today(ctx), overdue=True,
                                            offset=page.offset, limit=page.page_size)
    names = await ledger_service.customers_by_ids(ctx, {i.customer_id for i in items})
    data = [i.model_dump(mode="json") | {"customer_name": names[i.customer_id].name if i.customer_id in names
                                         else None} for i in items]
    return envelope(data, **page.meta(total))


# ---------------- audit & usage ----------------
def _log_out(r: ActionLog) -> dict:
    return {"id": r.id, "actor_user_id": r.actor_user_id, "action_type": r.action_type,
            "entity_type": r.entity_type, "entity_id": r.entity_id, "outcome": r.outcome,
            "metadata": r.metadata_, "created_at": r.created_at}


@router.get("/audit-logs")
async def audit_logs(action_type: str | None = None, entity_type: str | None = None,
                     entity_id: uuid.UUID | None = None, page: Pagination = Depends(),
                     ctx: Ctx = Depends(require(Perm.AUDIT_READ))) -> dict:
    stmt = select(ActionLog).where(ActionLog.business_id == ctx.business_id)
    if action_type:
        stmt = stmt.where(ActionLog.action_type == action_type)
    if entity_type:
        stmt = stmt.where(ActionLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(ActionLog.entity_id == entity_id)
    total = (await ctx.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await ctx.db.execute(stmt.order_by(ActionLog.created_at.desc(), ActionLog.id).offset(page.offset)
                                 .limit(page.page_size))).scalars().all()
    return envelope([_log_out(r) for r in rows], **page.meta(total))


@router.get("/usage")
async def get_usage(ctx: Ctx = Depends(require(Perm.USAGE_READ))) -> dict:
    return envelope(await usage.summary(ctx.db, ctx.business_id))
