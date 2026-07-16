from __future__ import annotations

import json
import re
from typing import Any


_BLOCK_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _truncate(value: Any, limit: int) -> Any:
    if isinstance(value, str):
        return value[:limit]
    if isinstance(value, list):
        return [_truncate(item, limit) for item in value]
    if isinstance(value, tuple):
        return [_truncate(item, limit) for item in value]
    if isinstance(value, dict):
        return {str(key)[:128]: _truncate(item, limit) for key, item in value.items()}
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:limit]


def _serialized(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=False)


def _string_paths(value: Any, path: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    if isinstance(value, str):
        return [path]
    paths: list[tuple[Any, ...]] = []
    if isinstance(value, list):
        for index, item in enumerate(value):
            paths.extend(_string_paths(item, (*path, index)))
    elif isinstance(value, dict):
        for key, item in value.items():
            paths.extend(_string_paths(item, (*path, key)))
    return paths


def _get(value: Any, path: tuple[Any, ...]) -> str:
    current = value
    for key in path:
        current = current[key]
    return current


def _set(value: Any, path: tuple[Any, ...], replacement: str) -> None:
    current = value
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = replacement


def bounded_untrusted_payload(
    value: dict[str, Any],
    *,
    field_limit: int = 8_000,
    total_limit: int = 30_000,
) -> str:
    if field_limit < 1 or total_limit < 2:
        raise ValueError("invalid payload limits")
    bounded = _truncate(value, field_limit)
    payload = _serialized(bounded)
    if len(payload) <= total_limit:
        return payload
    for path in reversed(_string_paths(bounded)):
        current = _get(bounded, path)
        excess = len(payload) - total_limit
        keep = max(0, len(current) - excess)
        _set(bounded, path, current[:keep])
        payload = _serialized(bounded)
        if len(payload) <= total_limit:
            return payload
    if len(payload) > total_limit:
        raise ValueError("untrusted payload structure exceeds total limit")
    return payload


def _escape_markup(value: str) -> str:
    return value.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


def untrusted_json_block(
    name: str,
    value: Any,
    *,
    field_limit: int = 8_000,
    total_limit: int = 30_000,
) -> str:
    if not _BLOCK_NAME.fullmatch(name):
        raise ValueError("invalid untrusted block name")
    payload = bounded_untrusted_payload(
        {"value": value},
        field_limit=field_limit,
        total_limit=total_limit,
    )
    return (
        f'<{name} trust="untrusted">'
        f"{_escape_markup(payload)}"
        f"</{name}>"
    )
