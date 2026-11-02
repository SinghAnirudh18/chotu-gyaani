import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import Ctx, require
from app.core.exceptions import ValidationFailed
from app.core.permissions import Perm
from app.providers.stt import get_stt
from app.schemas.assistant import AgentConfig, AgentGenerateIn, AgentOut, AgentPatch, AgentTestIn
from app.schemas.common import Pagination, envelope
from app.services import agent_service, usage
from app.services.pipeline import process_user_message
from app.utils.audio import validate_audio

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/generate")
async def generate_agent(data: AgentGenerateIn, ctx: Ctx = Depends(require(Perm.AGENTS_WRITE))) -> dict:
    await usage.consume(ctx.db, ctx.business_id, "agent_generations")
    cfg, provider = await agent_service.generate(data.description, data.language)
    # Generation returns a draft config only; it is never saved or activated automatically.
    return envelope({"config": cfg, "provider": provider, "saved": False})


@router.post("/generate-from-audio")
async def generate_agent_from_audio(file: UploadFile = File(...),
                                    language: Literal["en", "hi", "hi-Latn"] | None = Form(None),
                                    ctx: Ctx = Depends(require(Perm.AGENTS_WRITE))) -> dict:
    ctx.require(Perm.AUDIO_USE)
    audio = await file.read()
    validate_audio(audio, file.content_type)
    await usage.consume(ctx.db, ctx.business_id, "audio_requests")
    await usage.consume(ctx.db, ctx.business_id, "agent_generations")
    transcript = await get_stt().transcribe(audio, language)
    del audio
    if len(transcript.text.strip()) < 3:
        raise ValidationFailed("Could not understand the audio", code="empty_transcript")
    cfg, provider = await agent_service.generate(transcript.text, language or transcript.language)
    return envelope({"config": cfg, "provider": provider, "saved": False,
                     "transcript": {"text": transcript.text, "language": transcript.language,
                                    "provider": transcript.provider, "mock": transcript.provider == "mock"}})


@router.post("", status_code=201)
async def create_agent(data: AgentConfig, ctx: Ctx = Depends(require(Perm.AGENTS_WRITE))) -> dict:
    return envelope(AgentOut.model_validate(await agent_service.create(ctx, data)))


@router.get("")
async def list_agents(status: Literal["draft", "active", "archived"] | None = None, page: Pagination = Depends(),
                      ctx: Ctx = Depends(require(Perm.AGENTS_READ))) -> dict:
    items, total = await agent_service.list_agents(ctx, status, page.offset, page.page_size)
    return envelope([AgentOut.model_validate(a) for a in items], **page.meta(total))


@router.get("/{agent_id}")
async def get_agent(agent_id: uuid.UUID, ctx: Ctx = Depends(require(Perm.AGENTS_READ))) -> dict:
    return envelope(AgentOut.model_validate(await agent_service.get_agent(ctx, agent_id)))


@router.patch("/{agent_id}")
async def patch_agent(agent_id: uuid.UUID, data: AgentPatch, ctx: Ctx = Depends(require(Perm.AGENTS_WRITE))) -> dict:
    return envelope(AgentOut.model_validate(await agent_service.patch(ctx, agent_id, data)))


@router.post("/{agent_id}/test")
async def test_agent(agent_id: uuid.UUID, data: AgentTestIn, ctx: Ctx = Depends(require(Perm.AGENTS_READ))) -> dict:
    """Dry run: forces dry_run, persists nothing (no conversation, messages or actions)."""
    agent = await agent_service.get_agent(ctx, agent_id)
    await usage.consume(ctx.db, ctx.business_id, "assistant_messages")
    result = await process_user_message(ctx, None, data.message, data.language, dry_run=True, agent=agent)
    o = result["outcome"]
    await ctx.db.rollback()
    return envelope({"dry_run": True, "reply": o.reply, "language": o.language, "intent": o.intent, "tool": o.tool,
                     "result": o.data, "preview": o.preview, "clarification": o.clarification,
                     "providers": {"llm": result["llm_provider"]}})


@router.post("/{agent_id}/activate")
async def activate_agent(agent_id: uuid.UUID, ctx: Ctx = Depends(require(Perm.AGENTS_WRITE))) -> dict:
    return envelope(AgentOut.model_validate(await agent_service.set_status(ctx, agent_id, "active")))


@router.post("/{agent_id}/deactivate")
async def deactivate_agent(agent_id: uuid.UUID, ctx: Ctx = Depends(require(Perm.AGENTS_WRITE))) -> dict:
    return envelope(AgentOut.model_validate(await agent_service.set_status(ctx, agent_id, "draft")))


@router.delete("/{agent_id}")
async def delete_agent(agent_id: uuid.UUID, ctx: Ctx = Depends(require(Perm.AGENTS_WRITE))) -> dict:
    return envelope(AgentOut.model_validate(await agent_service.set_status(ctx, agent_id, "archived")))
