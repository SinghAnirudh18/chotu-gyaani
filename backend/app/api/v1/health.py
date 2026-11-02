from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.providers.llm import get_llm
from app.providers.stt import get_stt
from app.providers.tts import get_tts
from app.schemas.common import envelope

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return envelope({"status": "ok"})


@router.get("/ready")
async def ready() -> JSONResponse:
    checks: dict[str, object] = {}
    ok = True
    try:
        async with get_sessionmaker()() as db:
            await db.execute(text("SELECT 1"))
            ext = (await db.execute(text("SELECT extname FROM pg_extension WHERE extname IN ('pg_trgm','citext')"))
                   ).scalars().all()
        checks["database"] = "ok"
        checks["extensions"] = sorted(ext)
        if {"pg_trgm", "citext"} - set(ext):
            ok = False
    except Exception:
        checks["database"] = "unavailable"
        ok = False
    s = get_settings()
    try:
        llm_name = get_llm().name
    except Exception:
        llm_name = f"{s.llm_provider} (not configured)"
    checks["providers"] = {
        "llm": llm_name,
        "stt": await get_stt().health(),
        "tts": await get_tts().health(),
        "delivery": "stub",
    }
    body = envelope({"status": "ready" if ok else "not_ready", "checks": checks})
    return JSONResponse(body, status_code=200 if ok else 503)
