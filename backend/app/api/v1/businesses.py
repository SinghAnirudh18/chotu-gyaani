import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Ctx, get_current_user, get_db, require
from app.core.config import get_settings
from app.core.permissions import Perm
from app.db.models import User
from app.schemas.business import (
    AcceptInviteIn,
    BusinessCreate,
    BusinessOut,
    BusinessPatch,
    InviteIn,
    MemberOut,
    RoleChangeIn,
)
from app.schemas.common import envelope
from app.services import business_service

router = APIRouter(tags=["businesses"])


@router.post("/businesses", status_code=201)
async def create_business(data: BusinessCreate, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)) -> dict:
    b = await business_service.create_business(db, user, data)
    return envelope({"business": BusinessOut.model_validate(b), "role": "owner"})


@router.get("/businesses/me")
async def get_my_business(ctx: Ctx = Depends(require(Perm.BUSINESS_READ))) -> dict:
    return envelope({"business": BusinessOut.model_validate(ctx.business), "role": ctx.role})


@router.patch("/businesses/me")
async def patch_my_business(data: BusinessPatch, ctx: Ctx = Depends(require(Perm.BUSINESS_UPDATE))) -> dict:
    b = await business_service.update_business(ctx, data)
    return envelope({"business": BusinessOut.model_validate(b), "role": ctx.role})


@router.delete("/businesses/me")
async def delete_my_business(ctx: Ctx = Depends(require(Perm.BUSINESS_DELETE))) -> dict:
    await business_service.delete_business(ctx)
    return envelope({"deleted": True, "business_id": ctx.business_id})


@router.get("/export")
async def export_data(ctx: Ctx = Depends(require(Perm.DATA_EXPORT))) -> dict:
    return envelope(await business_service.export_business(ctx))


# ---------- members & invitations ----------
@router.get("/members")
async def list_members(ctx: Ctx = Depends(require(Perm.MEMBERS_READ))) -> dict:
    members = [MemberOut(**m) for m in await business_service.list_members(ctx)]
    return envelope(members, total=len(members))


@router.post("/members/invite", status_code=201)
async def invite_member(data: InviteIn, ctx: Ctx = Depends(require(Perm.MEMBERS_MANAGE))) -> dict:
    inv, token = await business_service.invite(ctx, data.email, data.role)
    body: dict = {"invitation": {"id": inv.id, "email": inv.email, "role": inv.role, "expires_at": inv.expires_at}}
    if get_settings().app_env != "prod":
        body["debug_invite_token"] = token  # no email provider yet; never returned in prod
    return envelope(body)


@router.post("/invitations/accept")
async def accept_invitation(data: AcceptInviteIn, user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)) -> dict:
    m = await business_service.accept_invitation(db, user, data.token)
    return envelope({"business_id": m.business_id, "role": m.role})


@router.patch("/members/{user_id}")
async def change_member_role(user_id: uuid.UUID, data: RoleChangeIn,
                             ctx: Ctx = Depends(require(Perm.MEMBERS_MANAGE))) -> dict:
    m = await business_service.change_role(ctx, user_id, data.role)
    return envelope({"user_id": m.user_id, "role": m.role})


@router.delete("/members/{user_id}")
async def remove_member(user_id: uuid.UUID, ctx: Ctx = Depends(require(Perm.MEMBERS_MANAGE))) -> dict:
    await business_service.remove_member(ctx, user_id)
    return envelope({"removed": True, "user_id": user_id})
