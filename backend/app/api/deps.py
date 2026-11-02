import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequest, Forbidden, NotFound, Unauthorized
from app.core.permissions import Perm, has_perm
from app.core.security import decode_access_token
from app.db.models import Business, BusinessMember, User
from app.db.session import get_sessionmaker

bearer = HTTPBearer(auto_error=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise Unauthorized()
    claims = decode_access_token(creds.credentials)
    try:
        user_id = uuid.UUID(claims["sub"])
    except (ValueError, KeyError) as e:
        raise Unauthorized("Invalid token", code="invalid_token") from e
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise Unauthorized("Invalid token", code="invalid_token")
    return user


@dataclass
class Ctx:
    db: AsyncSession
    user: User
    business: Business
    role: str

    @property
    def business_id(self) -> uuid.UUID:
        return self.business.id

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id

    def can(self, perm: Perm) -> bool:
        return has_perm(self.role, perm, self.business.settings)

    def require(self, perm: Perm) -> None:
        if not self.can(perm):
            raise Forbidden(details={"permission": perm.value})


async def get_ctx(
    request: Request,
    x_business_id: str | None = Header(default=None, alias="X-Business-ID"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Ctx:
    if not x_business_id:
        raise BadRequest("X-Business-ID header is required", code="business_header_required")
    try:
        business_id = uuid.UUID(x_business_id)
    except ValueError as e:
        raise NotFound("Business not found", code="business_not_found") from e
    row = (await db.execute(
        select(Business, BusinessMember.role)
        .join(BusinessMember, BusinessMember.business_id == Business.id)
        .where(Business.id == business_id, BusinessMember.user_id == user.id, Business.archived_at.is_(None))
    )).first()
    if row is None:
        # 404, not 403: do not reveal other tenants' existence.
        raise NotFound("Business not found", code="business_not_found")
    business, role = row
    request.state.business_id = str(business.id)
    return Ctx(db=db, user=user, business=business, role=role)


def require(perm: Perm) -> Callable[..., Coroutine[Any, Any, Ctx]]:
    async def _dep(ctx: Ctx = Depends(get_ctx)) -> Ctx:
        ctx.require(perm)
        return ctx

    return _dep
