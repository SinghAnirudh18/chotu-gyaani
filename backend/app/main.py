import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.v1 import agents, assistant, audio, auth, businesses, health, integrations, ledger
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.idempotency import IdempotencyMiddleware
from app.core.logging import configure_logging, log_event, request_id_var
from app.db.session import dispose_engine, get_sessionmaker
from app.workers import reminders as reminder_worker

logger = logging.getLogger("app.request")


class RequestContextMiddleware:
    """Assigns a request id, times the request and logs route/status/latency (never bodies)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope.get("headers", [])).get(b"x-request-id", b"").decode()[:64]
        rid = incoming if incoming and all(c.isalnum() or c in "-_" for c in incoming) else uuid.uuid4().hex
        token = request_id_var.set(rid)
        started = time.perf_counter()
        status = 500

        async def _send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message.setdefault("headers", [])
                message["headers"] = list(message["headers"]) + [(b"x-request-id", rid.encode())]
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            route = scope.get("route")
            log_event(logger, "request", method=scope["method"],
                      route=getattr(route, "path", scope["path"]), status=status,
                      latency_ms=round((time.perf_counter() - started) * 1000, 1))
            request_id_var.reset(token)


def _error(status: int, code: str, message: str, details: object = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, "details": details or {}}},
                        status_code=status)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.validate_for_startup()
    stop = asyncio.Event()
    task = None
    if settings.enable_workers and settings.app_env != "test":
        task = asyncio.create_task(reminder_worker.loop(get_sessionmaker(), stop))
    yield
    stop.set()
    if task:
        await task
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()
    app = FastAPI(title="Chotu-Gyani API", version="0.1.0", lifespan=lifespan,
                  description="Your business. Your language. Your AI.")

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [{"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
        return _error(422, "validation_error", "Request validation failed", {"errors": details})

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _error(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logging.getLogger("app.error").error("unhandled_error", exc_info=exc)
        return _error(500, "internal_error", "Something went wrong. Please try again.")

    for r in (health.router, auth.router, businesses.router, ledger.router, assistant.router, agents.router,
              audio.router, integrations.router):
        app.include_router(r)

    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
                       allow_headers=["Authorization", "Content-Type", "X-Business-ID", "Idempotency-Key",
                                      "X-Request-ID"],
                       expose_headers=["X-Request-ID", "Idempotent-Replayed", "X-TTS-Provider"])
    app.add_middleware(RequestContextMiddleware)
    return app


app = create_app()
