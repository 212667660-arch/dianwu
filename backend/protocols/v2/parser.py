from __future__ import annotations

import json

from backend.errors import ProtocolValidationError
from backend.protocols.v2.models import ResourceBundle


def bundle_to_json(bundle: ResourceBundle) -> str:
    return bundle.model_dump_json(indent=2)


def parse_bundle_from_json(data: str) -> ResourceBundle:
    try:
        obj = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ProtocolValidationError("BUNDLE_PARSE_ERROR", f"Invalid JSON: {exc}") from exc
    try:
        return ResourceBundle.model_validate(obj)
    except Exception as exc:
        raise ProtocolValidationError("BUNDLE_VALIDATION_ERROR", str(exc)) from exc


def validate_bundle(bundle: ResourceBundle) -> None:
    requested = set(bundle.requested_types)
    actual = {a.type for a in bundle.artifacts}
    if actual != requested:
        missing = requested - actual
        extra = actual - requested
        parts: list[str] = []
        if missing:
            parts.append(f"missing types {missing}")
        if extra:
            parts.append(f"extra types {extra}")
        raise ProtocolValidationError(
            "BUNDLE_TYPE_MISMATCH",
            "; ".join(parts),
        )


def bundle_to_sse_payload(bundle: ResourceBundle) -> str:
    from backend.protocols.v2.sse_events import bundle_event
    return bundle_event(bundle)
