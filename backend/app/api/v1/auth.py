from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
from app.core.rate_limit import rate_limiter
from app.db.models import User
from app.schemas.auth import (
    ForgotPasswordIn,
    LoginIn,
    LogoutIn,
    MembershipOut,
    RefreshIn,
    RegisterIn,
    ResetPasswordIn,
    UserOut,
    UserPatch,
)
from app.schemas.common import envelope
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _me_payload(db: AsyncSession, user: User) -> dict:
    return {"user": UserOut.model_validate(user),
            "memberships": [MembershipOut(**m) for m in await auth_service.memberships(db, user.id)]}


@router.post("/register", status_code=201)
async def register(data: RegisterIn, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    await rate_limiter.hit(f"register:{_client_ip(request)}", get_settings().auth_rate_limit_per_minute)
    user, tokens = await auth_service.register(db, data)
    return envelope({"user": UserOut.model_validate(user), "tokens": tokens})


@router.post("/login")
async def login(data: LoginIn, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    limit = get_settings().auth_rate_limit_per_minute
    await rate_limiter.hit(f"login:{_client_ip(request)}", limit)
    await rate_limiter.hit(f"login-email:{data.email.lower()}", limit)
    user, tokens = await auth_service.login(db, data.email, data.password)
    return envelope({"user": UserOut.model_validate(user), "tokens": tokens})


@router.get("/me")
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    return envelope(await _me_payload(db, user))


@router.patch("/me")
async def patch_me(data: UserPatch, user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)) -> dict:
    user = await db.merge(user)
    user = await auth_service.update_me(db, user, data)
    return envelope(await _me_payload(db, user))


@router.post("/refresh")
async def refresh(data: RefreshIn, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    await rate_limiter.hit(f"refresh:{_client_ip(request)}", get_settings().auth_rate_limit_per_minute * 6)
    return envelope({"tokens": await auth_service.refresh(db, data.refresh_token)})


@router.post("/logout")
async def logout(data: LogoutIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    await auth_service.logout(db, user.id, data.refresh_token, data.all_sessions)
    return envelope({"logged_out": True})


@router.post("/forgot-password", status_code=202)
async def forgot_password(data: ForgotPasswordIn, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    await rate_limiter.hit(f"forgot:{_client_ip(request)}", get_settings().auth_rate_limit_per_minute)
    token = await auth_service.forgot_password(db, data.email)
    body: dict = {"message": "If the account exists, a reset link has been sent."}
    if get_settings().app_env != "prod" and token:
        body["debug_reset_token"] = token  # no email provider yet; never returned in prod
    return envelope(body)


@router.post("/reset-password")
async def reset_password(data: ResetPasswordIn, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    await rate_limiter.hit(f"reset:{_client_ip(request)}", get_settings().auth_rate_limit_per_minute)
    await auth_service.reset_password(db, data.token, data.new_password)
    return envelope({"password_reset": True})
