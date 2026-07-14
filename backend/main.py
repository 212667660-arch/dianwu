from __future__ import annotations

import logging
from hashlib import sha256
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.config import get_settings
from backend.database import init_db
from backend.errors import AppError, DesktopAuthRequiredError, RequestRateLimitedError
from backend.services.orchestrator import close_runtime
from backend.services.rate_limit import rate_limiter
from backend.services.security import desktop_token_required, is_local_client, require_desktop_token, should_protect_path
from backend.routers import chat, learning, model_settings, profile, resource, sessions, web

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

TEST_UI_PATH = Path(__file__).resolve().with_name("test_console.html")

_HIGH_COST_RATE_LIMIT_PATHS = {
    "/api/chat",
    "/api/chat/stream",
    "/api/profile",
    "/api/resource",
}


def _rate_limit_for_path(path: str, settings) -> int | None:
    if path in _HIGH_COST_RATE_LIMIT_PATHS:
        return settings.api_rate_limit_per_minute
    if path == "/api/web/search":
        return settings.web_search_rate_limit_per_minute
    return None


def _rate_limit_identity(request: Request) -> str:
    token = request.headers.get("X-A3-Desktop-Token")
    if token:
        return f"token:{sha256(token.encode('utf-8')).hexdigest()}"
    return f"local:{request.client.host if request.client else 'unknown'}"


class DesktopAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if request.method != "OPTIONS" and should_protect_path(request.url.path, settings):
            try:
                if not is_local_client(request.client.host if request.client else None):
                    raise DesktopAuthRequiredError()
                require_desktop_token(
                    request.headers.get("X-A3-Desktop-Token"),
                    request.client.host if request.client else None,
                    settings,
                )
            except DesktopAuthRequiredError as exc:
                request_id = request.headers.get("X-Request-ID") or uuid4().hex
                return JSONResponse(
                    status_code=exc.http_status,
                    content={"code": exc.code, "message": exc.public_message, "retryable": exc.retryable, "request_id": request_id},
                )
        if desktop_token_required(settings):
            maximum = _rate_limit_for_path(request.url.path, settings)
            if maximum is not None:
                retry_after = rate_limiter.check(_rate_limit_identity(request), maximum)
                if retry_after is not None:
                    error = RequestRateLimitedError()
                    request_id = request.headers.get("X-Request-ID") or uuid4().hex
                    return JSONResponse(
                        status_code=error.http_status,
                        content={"code": error.code, "message": error.public_message, "retryable": error.retryable, "request_id": request_id},
                        headers={"Retry-After": str(retry_after)},
                    )
        return await call_next(request)


@asynccontextmanager
async def lifespan(_: FastAPI):
    rate_limiter.clear()
    init_db()
    try:
        yield
    finally:
        rate_limiter.clear()
        await close_runtime()


app = FastAPI(title="Learning Agent System API", version="0.2.0", lifespan=lifespan)
app.add_middleware(DesktopAuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-Request-ID", "X-A3-Desktop-Token"],
)
app.include_router(chat.router)
app.include_router(profile.router)
app.include_router(resource.router)
app.include_router(sessions.router)
app.include_router(learning.router)
app.include_router(model_settings.router)
app.include_router(web.router)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    request_id = request.headers.get("X-Request-ID") or uuid4().hex
    logging.getLogger("backend").warning("request_id=%s code=%s path=%s", request_id, exc.code, request.url.path)
    return JSONResponse(status_code=exc.http_status, content={"code": exc.code, "message": exc.public_message, "retryable": exc.retryable, "request_id": request_id})


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Learning Agent System API"}


@app.get("/test", include_in_schema=False)
async def test_console() -> FileResponse:
    return FileResponse(TEST_UI_PATH, media_type="text/html; charset=utf-8")


@app.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "live"}


@app.get("/health/ready")
async def ready() -> JSONResponse:
    if not get_settings().is_model_configured:
        return JSONResponse(status_code=503, content={"status": "not_ready", "reason": "model_not_configured"})
    return JSONResponse(status_code=200, content={"status": "ready"})
