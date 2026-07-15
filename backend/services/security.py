from __future__ import annotations

import ipaddress
import secrets
import socket
from urllib.parse import urlparse

from backend.config import Settings, get_settings
from backend.errors import DesktopAuthRequiredError, ModelSettingsValidationError

_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}
_PUBLIC_PATHS = {"/", "/health/live", "/docs", "/openapi.json", "/redoc"}


def is_production(settings: Settings | object) -> bool:
    return str(getattr(settings, "app_env", "development")).strip().lower() == "production"


def desktop_token_required(settings: Settings | object) -> bool:
    return is_production(settings) or bool(str(getattr(settings, "desktop_token", "")).strip())


def is_local_client(client_host: str | None) -> bool:
    return client_host in _LOCAL_HOSTS


def require_desktop_token(provided_token: str | None, client_host: str | None, settings: Settings | object | None = None) -> None:
    current = settings or get_settings()
    expected_token = str(getattr(current, "desktop_token", "")).strip()
    if not desktop_token_required(current):
        return
    if not expected_token or not provided_token or not secrets.compare_digest(provided_token, expected_token):
        raise DesktopAuthRequiredError()


def should_protect_path(path: str, settings: Settings | object | None = None) -> bool:
    current = settings or get_settings()
    if path in _PUBLIC_PATHS:
        return False
    if path == "/health/ready":
        return desktop_token_required(current)
    if path.startswith("/internal/"):
        return True
    return path.startswith("/api/") and desktop_token_required(current)


def require_internal_desktop_token(provided_token: str | None, client_host: str | None, settings: Settings | object | None = None) -> None:
    current = settings or get_settings()
    expected_token = str(getattr(current, "desktop_token", "")).strip()
    if (
        not is_local_client(client_host)
        or not expected_token
        or not provided_token
        or not secrets.compare_digest(provided_token, expected_token)
    ):
        raise DesktopAuthRequiredError()


def _is_private_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_unspecified
        or address.is_multicast
        or address.is_reserved
    )


def validate_model_base_url(value: str, settings: Settings | object | None = None) -> str:
    current = settings or get_settings()
    raw = value.strip().rstrip("/")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ModelSettingsValidationError("模型网关地址必须是完整的 HTTP(S) 地址。")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ModelSettingsValidationError("模型网关地址不能包含账号、查询参数或片段。")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ModelSettingsValidationError("模型网关地址端口无效。") from exc
    if is_production(current) and port is not None and port not in {80, 443}:
        raise ModelSettingsValidationError("模型网关地址仅允许标准 HTTP(S) 端口。")
    if is_production(current) and parsed.scheme != "https":
        raise ModelSettingsValidationError("生产模式仅允许 HTTPS 模型网关。")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        if is_production(current):
            try:
                resolved = socket.getaddrinfo(parsed.hostname, port or 443, type=socket.SOCK_STREAM)
            except socket.gaierror as exc:
                raise ModelSettingsValidationError("模型网关域名无法解析。") from exc
            for item in resolved:
                if _is_private_address(ipaddress.ip_address(item[4][0])):
                    raise ModelSettingsValidationError("模型网关地址不能指向本机或内网地址。")
        return raw
    if _is_private_address(address):
        if not (not is_production(current) and bool(getattr(current, "allow_local_model_gateway", False))):
            raise ModelSettingsValidationError("模型网关地址不能指向本机或内网地址。")
    return raw
