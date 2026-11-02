import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ActionLog

_UNSAFE_KEYS = {"password", "password_hash", "token", "access_token", "refresh_token", "secret", "content",
                "text", "transcript", "notes", "authorization", "api_key"}


def _safe(meta: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (meta or {}).items():
        if k.lower() in _UNSAFE_KEYS:
            continue
        if isinstance(v, dict):
            out[k] = _safe(v)
        elif isinstance(v, str | int | float | bool) or v is None:
            out[k] = v
        else:
            out[k] = str(v)
    return out


def audit(
    db: AsyncSession, business_id: uuid.UUID, actor_user_id: uuid.UUID | None, action_type: str, *,
    entity_type: str | None = None, entity_id: uuid.UUID | None = None, outcome: str = "success",
    metadata: dict[str, Any] | None = None,
) -> None:
    """Stage an append-only audit row in the caller's transaction."""
    db.add(ActionLog(
        business_id=business_id, actor_user_id=actor_user_id, action_type=action_type,
        entity_type=entity_type, entity_id=entity_id, outcome=outcome, metadata_=_safe(metadata),
    ))
