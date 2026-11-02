"""Idempotency-Key support for every authenticated, business-scoped write.

First request stores (request_hash, response, status). Same key + same hash
replays the stored response; same key + different hash returns 422. A request
still in flight returns 409. Keys expire after 24 hours."""
import hashlib
import json
import uuid
from datetime import timedelta

from sqlalchemy import and_, delete, select, update
from sqlalchemy.dialects.postgresql import insert
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exceptions import AppError
from app.core.security import decode_access_token
from app.db.models import BusinessMember, IdempotencyKey
from app.db.session import get_sessionmaker
from app.utils.dates import utcnow

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
TTL = timedelta(hours=24)


async def _json_response(send: Send, status: int, body: dict, extra_headers: list | None = None) -> None:
    raw = json.dumps(body).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(raw)).encode())]
                + (extra_headers or [])})
    await send({"type": "http.response.body", "body": raw})


class IdempotencyMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in WRITE_METHODS:
            await self.app(scope, receive, send)
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        key = headers.get("idempotency-key")
        auth = headers.get("authorization", "")
        bid_raw = headers.get("x-business-id")
        if not key or not auth.lower().startswith("bearer ") or not bid_raw:
            await self.app(scope, receive, send)
            return
        try:
            user_id = uuid.UUID(decode_access_token(auth[7:].strip())["sub"])
            business_id = uuid.UUID(bid_raw)
        except (AppError, ValueError, KeyError):
            await self.app(scope, receive, send)
            return
        if len(key) > 255:
            await _json_response(send, 422, {"error": {"code": "invalid_idempotency_key",
                                                       "message": "Idempotency-Key is too long", "details": {}}})
            return

        # Buffer the body so it can be hashed and replayed downstream.
        chunks = []
        more = True
        while more:
            msg = await receive()
            if msg["type"] == "http.disconnect":
                return
            chunks.append(msg.get("body", b""))
            more = msg.get("more_body", False)
        body = b"".join(chunks)
        route = f"{scope['method']} {scope['path']}"
        req_hash = hashlib.sha256(route.encode() + b"?" + scope.get("query_string", b"") + b"\n" + body).hexdigest()

        sm = get_sessionmaker()
        async with sm() as db:
            member = (await db.execute(select(BusinessMember.id).where(
                BusinessMember.business_id == business_id, BusinessMember.user_id == user_id))).first()
            if member is None:
                row_id = None
            else:
                ident = and_(IdempotencyKey.business_id == business_id, IdempotencyKey.user_id == user_id,
                             IdempotencyKey.route == route, IdempotencyKey.key == key)
                await db.execute(delete(IdempotencyKey).where(ident, IdempotencyKey.created_at < utcnow() - TTL))
                row_id = (await db.execute(
                    insert(IdempotencyKey).values(business_id=business_id, user_id=user_id, route=route, key=key,
                                                  request_hash=req_hash, status_code=0)
                    .on_conflict_do_nothing().returning(IdempotencyKey.id))).scalar_one_or_none()
                if row_id is None:
                    existing = (await db.execute(select(IdempotencyKey).where(ident))).scalar_one()
                    await db.commit()
                    if existing.request_hash != req_hash:
                        await _json_response(send, 422, {"error": {
                            "code": "idempotency_key_reused",
                            "message": "Idempotency-Key was already used with a different request",
                            "details": {}}})
                        return
                    if existing.status_code == 0:
                        await _json_response(send, 409, {"error": {
                            "code": "idempotency_in_progress",
                            "message": "A request with this Idempotency-Key is still in progress",
                            "details": {}}})
                        return
                    raw = (existing.response_body or "").encode()
                    await send({"type": "http.response.start", "status": existing.status_code, "headers": [
                        (b"content-type", b"application/json"), (b"content-length", str(len(raw)).encode()),
                        (b"idempotent-replayed", b"true")]})
                    await send({"type": "http.response.body", "body": raw})
                    return
            await db.commit()

        replayed = False

        async def replay_receive() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        status = 500
        content_type = b""
        out: list[bytes] = []

        async def capture_send(message: Message) -> None:
            nonlocal status, content_type
            if message["type"] == "http.response.start":
                status = message["status"]
                content_type = dict(message.get("headers", [])).get(b"content-type", b"")
            elif message["type"] == "http.response.body":
                out.append(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, replay_receive, capture_send)
        finally:
            if row_id is not None:
                async with sm() as db:
                    if status < 500 and status != 401 and content_type.startswith(b"application/json"):
                        await db.execute(update(IdempotencyKey).where(IdempotencyKey.id == row_id).values(
                            status_code=status, response_body=b"".join(out).decode("utf-8", "replace")))
                    else:
                        await db.execute(delete(IdempotencyKey).where(IdempotencyKey.id == row_id))
                    await db.commit()
