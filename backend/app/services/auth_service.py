import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import Conflict, Unauthorized, ValidationFailed
from app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_opaque_token,
    validate_password_policy,
    verify_password,
)
from app.db.models import Business, BusinessMember, PasswordReset, RefreshToken, User
from app.schemas.auth import RegisterIn, UserPatch
from app.utils.dates import utcnow

# Dummy hash so login timing does not reveal whether the email exists.
_DUMMY_HASH = hash_password("dummy-password-1")


async def _issue_tokens(db: AsyncSession, user_id: uuid.UUID, family_id: uuid.UUID | None = None) -> dict:
    s = get_settings()
    access, ttl = create_access_token(user_id)
    refresh = new_opaque_token()
    rt = RefreshToken(user_id=user_id, token_hash=hash_token(refresh), family_id=family_id or uuid.uuid4(),
                      expires_at=utcnow() + timedelta(days=s.refresh_token_ttl_days))
    db.add(rt)
    await db.flush()
    return {"access_token": access, "token_type": "bearer", "expires_in": ttl, "refresh_token": refresh,
            "_refresh_id": rt.id}


def _public(tokens: dict) -> dict:
    return {k: v for k, v in tokens.items() if not k.startswith("_")}


async def register(db: AsyncSession, data: RegisterIn) -> tuple[User, dict]:
    validate_password_policy(data.password)
    user = User(email=data.email.lower(), password_hash=hash_password(data.password), name=data.name.strip(),
                preferred_language=data.preferred_language)
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        raise Conflict("An account with this email already exists", code="email_taken") from e
    tokens = await _issue_tokens(db, user.id)
    await db.commit()
    return user, _public(tokens)


async def login(db: AsyncSession, email: str, password: str) -> tuple[User, dict]:
    user = (await db.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()
    if user is None:
        verify_password(password, _DUMMY_HASH)
        raise Unauthorized("Invalid email or password", code="invalid_credentials")
    if not verify_password(password, user.password_hash) or not user.is_active:
        raise Unauthorized("Invalid email or password", code="invalid_credentials")
    tokens = await _issue_tokens(db, user.id)
    await db.commit()
    return user, _public(tokens)


async def refresh(db: AsyncSession, token: str) -> dict:
    now = utcnow()
    rt = (await db.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_token(token))
                           .with_for_update())).scalar_one_or_none()
    if rt is None:
        raise Unauthorized("Invalid refresh token", code="invalid_refresh_token")
    if rt.revoked_at is not None:
        # Reuse of a rotated token: revoke the whole family.
        await db.execute(update(RefreshToken).where(RefreshToken.family_id == rt.family_id,
                                                    RefreshToken.revoked_at.is_(None)).values(revoked_at=now))
        await db.commit()
        raise Unauthorized("Refresh token reuse detected", code="refresh_token_reused")
    if rt.expires_at <= now:
        raise Unauthorized("Refresh token expired", code="refresh_token_expired")
    user = await db.get(User, rt.user_id)
    if user is None or not user.is_active:
        raise Unauthorized("Invalid refresh token", code="invalid_refresh_token")
    tokens = await _issue_tokens(db, rt.user_id, rt.family_id)
    rt.revoked_at = now
    rt.replaced_by = tokens["_refresh_id"]
    await db.commit()
    return _public(tokens)


async def logout(db: AsyncSession, user_id: uuid.UUID, token: str | None, all_sessions: bool) -> None:
    now = utcnow()
    stmt = update(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
    if not all_sessions:
        if not token:
            raise ValidationFailed("refresh_token is required unless all_sessions is true")
        stmt = stmt.where(RefreshToken.token_hash == hash_token(token))
    await db.execute(stmt.values(revoked_at=now))
    await db.commit()


async def memberships(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    rows = (await db.execute(
        select(Business.id, Business.name, BusinessMember.role)
        .join(BusinessMember, BusinessMember.business_id == Business.id)
        .where(BusinessMember.user_id == user_id, Business.archived_at.is_(None))
        .order_by(Business.created_at)
    )).all()
    return [{"business_id": r[0], "business_name": r[1], "role": r[2]} for r in rows]


async def update_me(db: AsyncSession, user: User, data: UserPatch) -> User:
    if data.name is not None:
        user.name = data.name.strip()
    if data.preferred_language is not None:
        user.preferred_language = data.preferred_language
    if data.new_password is not None:
        if not data.current_password or not verify_password(data.current_password, user.password_hash):
            raise Unauthorized("Current password is incorrect", code="invalid_credentials")
        validate_password_policy(data.new_password)
        user.password_hash = hash_password(data.new_password)
        await db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id,
                                                    RefreshToken.revoked_at.is_(None)).values(revoked_at=utcnow()))
    await db.commit()
    await db.refresh(user)
    return user


async def forgot_password(db: AsyncSession, email: str) -> str | None:
    """Creates a reset token. Returns it only so dev/test can complete the flow (no email provider)."""
    user = (await db.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    token = new_opaque_token()
    db.add(PasswordReset(user_id=user.id, token_hash=hash_token(token),
                         expires_at=utcnow() + timedelta(minutes=get_settings().password_reset_ttl_minutes)))
    await db.commit()
    return token


async def reset_password(db: AsyncSession, token: str, new_password: str) -> None:
    now = utcnow()
    pr = (await db.execute(select(PasswordReset).where(PasswordReset.token_hash == hash_token(token))
                           .with_for_update())).scalar_one_or_none()
    if pr is None or pr.used_at is not None or pr.expires_at <= now:
        raise ValidationFailed("Invalid or expired reset token", code="invalid_reset_token")
    validate_password_policy(new_password)
    user = await db.get(User, pr.user_id)
    assert user is not None
    user.password_hash = hash_password(new_password)
    pr.used_at = now
    await db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id,
                                                RefreshToken.revoked_at.is_(None)).values(revoked_at=now))
    await db.commit()
