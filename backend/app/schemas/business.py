import uuid
from datetime import datetime
from zoneinfo import available_timezones

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel

_TZS = available_timezones()


def _check_tz(v: str | None) -> str | None:
    if v is not None and v not in _TZS:
        raise ValueError("Unknown timezone")
    return v


def _check_lang(v: str | None) -> str | None:
    if v is not None and v not in ("en", "hi", "hi-Latn"):
        raise ValueError("Language must be one of en, hi, hi-Latn")
    return v


class BusinessCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    timezone: str = "Asia/Kolkata"
    default_language: str = "hi-Latn"

    _tz = field_validator("timezone")(_check_tz)
    _lang = field_validator("default_language")(_check_lang)


class BusinessSettings(BaseModel):
    members_can_confirm_reminders: bool | None = None


class BusinessPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    timezone: str | None = None
    default_language: str | None = None
    settings: BusinessSettings | None = None

    _tz = field_validator("timezone")(_check_tz)
    _lang = field_validator("default_language")(_check_lang)


class BusinessOut(ORMModel):
    id: uuid.UUID
    name: str
    timezone: str
    default_language: str
    currency: str
    settings: dict
    created_at: datetime
    updated_at: datetime


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    name: str
    role: str
    joined_at: datetime


class InviteIn(BaseModel):
    email: EmailStr
    role: str = "member"

    @field_validator("role")
    @classmethod
    def _role(cls, v: str) -> str:
        if v not in ("admin", "member"):
            raise ValueError("Role must be admin or member")
        return v


class AcceptInviteIn(BaseModel):
    token: str = Field(min_length=10, max_length=256)


class RoleChangeIn(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def _role(cls, v: str) -> str:
        if v not in ("owner", "admin", "member"):
            raise ValueError("Role must be owner, admin or member")
        return v
