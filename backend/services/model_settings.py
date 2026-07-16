from __future__ import annotations

import os
import tempfile
import time

from backend.config import ENV_FILE, Settings, get_settings

_MODEL_ENV_KEYS = {
    "MODEL_PROVIDER",
    "MODEL_API_KEY",
    "MODEL_BASE_URL",
    "MODEL_NAME",
    "ANTHROPIC_VERSION",
    "REQUEST_TIMEOUT_SECONDS",
}
from backend.errors import DesktopAuthRequiredError, ModelCredentialStoreRequiredError, ModelSettingsAccessError
from backend.services.llm_service import ModelGateway
from backend.services.model_runtime import model_runtime_router
from backend.models.schemas import ModelConnectionTestResponse, ModelSettingsResponse, ModelSettingsUpdate
from backend.services.security import is_production, require_desktop_token, validate_model_base_url

_ENV_PATH = ENV_FILE


def _mask_key(value: str) -> str:
    if len(value) <= 8:
        return "configured" if value else ""
    return f"{value[:4]}...{value[-4:]}"


def current_model_settings() -> ModelSettingsResponse:
    current = get_settings()
    if not current.is_model_configured:
        runtime_settings = model_runtime_router.legacy_model_settings()
        if runtime_settings is not None:
            return runtime_settings
    return ModelSettingsResponse(
        provider=current.resolved_provider,
        base_url=current.resolved_base_url,
        model_name=current.resolved_model_name,
        api_key_configured=current.is_model_configured,
        api_key_hint=_mask_key(current.resolved_api_key),
        anthropic_version=current.anthropic_version,
        request_timeout_seconds=current.request_timeout_seconds,
    )


def save_model_settings(update: ModelSettingsUpdate) -> ModelSettingsResponse:
    current = get_settings()
    normalized_base_url = validate_model_base_url(update.base_url, current)
    if is_production(current):
        raise ModelCredentialStoreRequiredError()
    values = {
        "MODEL_PROVIDER": update.provider,
        "MODEL_API_KEY": update.api_key,
        "MODEL_BASE_URL": normalized_base_url,
        "MODEL_NAME": update.model_name,
        "ANTHROPIC_VERSION": update.anthropic_version,
        "REQUEST_TIMEOUT_SECONDS": str(update.request_timeout_seconds),
    }
    preserved: list[str] = []
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            key = line.split("=", 1)[0].strip()
            if key not in _MODEL_ENV_KEYS:
                preserved.append(line)
    content = "\n".join(preserved + [f"{key}={value}" for key, value in values.items()]) + "\n"
    _ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=_ENV_PATH.parent, delete=False) as temporary:
        temporary.write(content)
        temporary_path = temporary.name
    try:
        os.replace(temporary_path, _ENV_PATH)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
    get_settings.cache_clear()
    return current_model_settings()


def verify_desktop_token(provided_token: str | None, client_host: str | None) -> None:
    current = get_settings()
    try:
        require_desktop_token(provided_token, client_host, current)
    except DesktopAuthRequiredError as exc:
        raise ModelSettingsAccessError() from exc
    if not current.desktop_token.strip() and client_host not in {"127.0.0.1", "::1", "localhost"}:
        raise ModelSettingsAccessError()


async def test_model_connection(update: ModelSettingsUpdate) -> ModelConnectionTestResponse:
    current = get_settings()
    normalized_base_url = validate_model_base_url(update.base_url, current)
    candidate = Settings(
        model_provider=update.provider,
        model_api_key=update.api_key,
        model_base_url=normalized_base_url,
        model_name=update.model_name,
        anthropic_version=update.anthropic_version,
        request_timeout_seconds=update.request_timeout_seconds,
        openai_api_key="",
        hy_api_key="",
        app_env=current.app_env,
        allow_local_model_gateway=current.allow_local_model_gateway,
    )
    gateway = ModelGateway(candidate)
    started = time.perf_counter()
    try:
        await gateway.complete([{"role": "user", "content": "Reply with exactly: OK"}], temperature=0)
    finally:
        await gateway.aclose()
    return ModelConnectionTestResponse(
        provider=update.provider,
        model_name=update.model_name,
        status="connected",
        latency_ms=round((time.perf_counter() - started) * 1000),
    )
