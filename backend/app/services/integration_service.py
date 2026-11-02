"""Google Sheets integration (P2). Works only with GOOGLE_CLIENT_ID/SECRET configured;
otherwise every entry point returns 503 provider_not_configured."""
import base64
import csv
import hashlib
import io
import json
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, urlencode

import httpx
import jwt
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Ctx
from app.core.config import get_settings
from app.core.exceptions import NotFound, ProviderNotConfigured, ProviderUnavailable, ValidationFailed
from app.db.models import Integration
from app.services import ledger_service
from app.services.audit import audit

PROVIDER = "google_sheets"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SHEETS_URL = "https://sheets.googleapis.com/v4/spreadsheets/{sid}/values/{rng}"
SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"


def _fernet() -> Fernet:
    key = hashlib.sha256(("integrations:" + get_settings().jwt_secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _require_configured() -> None:
    s = get_settings()
    if not (s.google_client_id and s.google_client_secret):
        raise ProviderNotConfigured("Google integration is not configured", details={"provider": PROVIDER})


def _http() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(10.0), transport=httpx.AsyncHTTPTransport(retries=2))


async def list_integrations(ctx: Ctx) -> list[dict]:
    rows = (await ctx.db.execute(select(Integration).where(Integration.business_id == ctx.business_id))
            ).scalars().all()
    s = get_settings()
    configured = bool(s.google_client_id and s.google_client_secret)
    out = [{"id": r.id, "provider": r.provider, "status": r.status, "config": r.config,
            "created_at": r.created_at} for r in rows]
    if not any(r["provider"] == PROVIDER for r in out):
        out.append({"id": None, "provider": PROVIDER, "status": "available" if configured else "not_configured",
                    "config": {}, "created_at": None})
    return out


async def authorize_url(ctx: Ctx) -> str:
    _require_configured()
    s = get_settings()
    state = jwt.encode({"b": str(ctx.business_id), "u": str(ctx.user_id), "aud": "google-oauth",
                        "exp": datetime.now(UTC) + timedelta(minutes=10)}, s.jwt_secret, algorithm="HS256")
    params = {"client_id": s.google_client_id, "redirect_uri": s.google_redirect_uri, "response_type": "code",
              "scope": SCOPE, "access_type": "offline", "prompt": "consent", "state": state}
    return f"{AUTH_URL}?{urlencode(params)}"


async def oauth_callback(db: AsyncSession, code: str, state: str) -> Integration:
    _require_configured()
    s = get_settings()
    try:
        claims = jwt.decode(state, s.jwt_secret, algorithms=["HS256"], audience="google-oauth")
    except jwt.PyJWTError as e:
        raise ValidationFailed("Invalid OAuth state", code="invalid_oauth_state") from e
    bid, uid = uuid.UUID(claims["b"]), uuid.UUID(claims["u"])
    try:
        async with _http() as client:
            resp = await client.post(TOKEN_URL, data={
                "code": code, "client_id": s.google_client_id, "client_secret": s.google_client_secret,
                "redirect_uri": s.google_redirect_uri, "grant_type": "authorization_code"})
    except httpx.HTTPError as e:
        raise ProviderUnavailable("Google is unreachable", details={"provider": PROVIDER}) from e
    if resp.status_code != 200:
        raise ProviderUnavailable("Google token exchange failed", details={"provider": PROVIDER,
                                                                          "status": resp.status_code})
    tokens = resp.json()
    secret = _fernet().encrypt(json.dumps(tokens).encode()).decode()
    integ = (await db.execute(select(Integration).where(Integration.business_id == bid,
                                                        Integration.provider == PROVIDER))).scalar_one_or_none()
    if integ is None:
        integ = Integration(business_id=bid, provider=PROVIDER)
        db.add(integ)
    integ.status, integ.secret_encrypted, integ.connected_by = "connected", secret, uid
    integ.config = {"scope": SCOPE}
    await db.flush()
    audit(db, bid, uid, "integration.connected", entity_type="integration", entity_id=integ.id,
          metadata={"provider": PROVIDER})
    await db.commit()
    return integ


async def _access_token(ctx: Ctx, integ: Integration) -> str:
    try:
        tokens = json.loads(_fernet().decrypt((integ.secret_encrypted or "").encode()))
    except (InvalidToken, ValueError) as e:
        raise ValidationFailed("Integration credentials are invalid; reconnect", code="integration_invalid") from e
    refresh = tokens.get("refresh_token")
    if not refresh:
        return tokens["access_token"]
    s = get_settings()
    async with _http() as client:
        resp = await client.post(TOKEN_URL, data={"client_id": s.google_client_id,
                                                  "client_secret": s.google_client_secret,
                                                  "refresh_token": refresh, "grant_type": "refresh_token"})
    if resp.status_code != 200:
        raise ProviderUnavailable("Google token refresh failed", details={"provider": PROVIDER})
    return resp.json()["access_token"]


async def import_from_sheet(ctx: Ctx, spreadsheet_id: str, range_: str, dry_run: bool) -> dict:
    _require_configured()
    integ = (await ctx.db.execute(select(Integration).where(Integration.business_id == ctx.business_id,
                                                            Integration.provider == PROVIDER))).scalar_one_or_none()
    if integ is None or integ.status != "connected":
        raise NotFound("Google Sheets is not connected", code="integration_not_connected")
    token = await _access_token(ctx, integ)
    url = SHEETS_URL.format(sid=quote(spreadsheet_id, safe=""), rng=quote(range_, safe=""))
    try:
        async with _http() as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    except httpx.HTTPError as e:
        raise ProviderUnavailable("Google is unreachable", details={"provider": PROVIDER}) from e
    if resp.status_code != 200:
        raise ProviderUnavailable("Could not read the spreadsheet", details={"status": resp.status_code})
    values = resp.json().get("values", [])
    buf = io.StringIO()
    csv.writer(buf).writerows(values)
    return await ledger_service.import_customers_csv(ctx, buf.getvalue().encode(), dry_run)


async def disconnect(ctx: Ctx, integration_id: uuid.UUID) -> None:
    integ = (await ctx.db.execute(select(Integration).where(Integration.id == integration_id,
                                                            Integration.business_id == ctx.business_id))
             ).scalar_one_or_none()
    if integ is None:
        raise NotFound("Integration not found")
    await ctx.db.delete(integ)
    audit(ctx.db, ctx.business_id, ctx.user_id, "integration.disconnected", entity_type="integration",
          entity_id=integration_id, metadata={"provider": integ.provider})
    await ctx.db.commit()
