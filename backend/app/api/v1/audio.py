from typing import Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response

from app.api.deps import Ctx, require
from app.core.config import get_settings
from app.core.permissions import Perm
from app.providers.stt import get_stt
from app.providers.tts import get_tts
from app.schemas.assistant import SpeechIn
from app.schemas.common import envelope
from app.services import usage
from app.utils.audio import ALLOWED, validate_audio

router = APIRouter(prefix="/audio", tags=["audio"])


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...), language: Literal["en", "hi", "hi-Latn"] | None = Form(None),
                     ctx: Ctx = Depends(require(Perm.AUDIO_USE))) -> dict:
    audio = await file.read()
    meta = validate_audio(audio, file.content_type)
    await usage.consume(ctx.db, ctx.business_id, "audio_requests")
    tr = await get_stt().transcribe(audio, language)
    del audio  # raw audio is never persisted
    return envelope({"text": tr.text, "language": tr.language, "confidence": tr.confidence,
                     "provider": tr.provider, "mock": tr.provider == "mock", "audio": meta})


@router.post("/speech")
async def speech(data: SpeechIn, ctx: Ctx = Depends(require(Perm.AUDIO_USE))) -> Response:
    await usage.consume(ctx.db, ctx.business_id, "audio_requests")
    result = await get_tts().synthesize(data.text, data.language, data.voice)
    return Response(content=result.audio, media_type=result.mime_type,
                    headers={"X-TTS-Provider": result.provider, "X-Mock-Provider": str(result.provider == "mock").lower(),
                             "X-Audio-Duration": str(result.duration_seconds)})


@router.get("/providers")
async def providers(ctx: Ctx = Depends(require(Perm.AUDIO_USE))) -> dict:
    s = get_settings()
    return envelope({
        "stt": await get_stt().health(),
        "tts": await get_tts().health(),
        "limits": {"max_bytes": s.max_audio_bytes, "max_seconds": s.max_audio_seconds,
                   "accepted_mime_types": sorted({m for ms in ALLOWED.values() for m in ms})},
        "languages": ["en", "hi", "hi-Latn"],
    })
