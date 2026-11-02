import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=120)
    preferred_language: str | None = Field(default=None, max_length=16)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=10, max_length=256)


class LogoutIn(BaseModel):
    refresh_token: str | None = Field(default=None, max_length=256)
    all_sessions: bool = False


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=10, max_length=256)
    new_password: str = Field(min_length=1, max_length=128)


class UserPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    preferred_language: str | None = Field(default=None, max_length=16)
    current_password: str | None = Field(default=None, max_length=128)
    new_password: str | None = Field(default=None, max_length=128)


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    name: str
    preferred_language: str | None
    is_active: bool
    created_at: datetime


class MembershipOut(BaseModel):
    business_id: uuid.UUID
    business_name: str
    role: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str
