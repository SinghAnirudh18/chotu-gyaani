import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Ctx, get_db, require
from app.core.permissions import Perm
from app.schemas.common import envelope
from app.services import integration_service

router = APIRouter(prefix="/integrations", tags=["integrations"])


class SheetImportIn(BaseModel):
    spreadsheet_id: str = Field(min_length=5, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")
    range: str = Field(default="Sheet1!A:E", max_length=100)
    dry_run: bool = True


@router.get("")
async def list_integrations(ctx: Ctx = Depends(require(Perm.INTEGRATIONS_MANAGE))) -> dict:
    return envelope(await integration_service.list_integrations(ctx))


@router.post("/google-sheets/connect")
async def connect_google_sheets(ctx: Ctx = Depends(require(Perm.INTEGRATIONS_MANAGE))) -> dict:
    return envelope({"authorize_url": await integration_service.authorize_url(ctx)})


@router.get("/google-sheets/callback")
async def google_sheets_callback(code: str = Query(..., max_length=2048), state: str = Query(..., max_length=4096),
                                 db: AsyncSession = Depends(get_db)) -> dict:
    integ = await integration_service.oauth_callback(db, code, state)
    return envelope({"id": integ.id, "provider": integ.provider, "status": integ.status})


@router.post("/google-sheets/import")
async def import_from_google_sheets(data: SheetImportIn,
                                   ctx: Ctx = Depends(require(Perm.INTEGRATIONS_MANAGE))) -> dict:
    ctx.require(Perm.CUSTOMERS_IMPORT)
    return envelope(await integration_service.import_from_sheet(ctx, data.spreadsheet_id, data.range, data.dry_run))


@router.delete("/{integration_id}")
async def disconnect(integration_id: uuid.UUID, ctx: Ctx = Depends(require(Perm.INTEGRATIONS_MANAGE))) -> dict:
    await integration_service.disconnect(ctx, integration_id)
    return envelope({"disconnected": True})
