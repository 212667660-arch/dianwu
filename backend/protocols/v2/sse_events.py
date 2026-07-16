from __future__ import annotations

import json
from typing import Any

from backend.protocols.v2.models import ResourceArtifact, ResourceBundle


def _event(kind: str, **kwargs: Any) -> str:
    return json.dumps({"event": kind, **kwargs}, ensure_ascii=False)


def plan_event(bundle_id: str, topic: str, requested_types: list[str]) -> str:
    return _event("resource_plan", bundle_id=bundle_id, topic=topic,
                  requested_types=requested_types)


def progress_event(current_type: str, completed_count: int, total_count: int,
                   status: str = "GENERATING") -> str:
    return _event("resource_progress", current_type=current_type,
                  completed_count=completed_count, total_count=total_count, status=status)


def artifact_event(artifact: ResourceArtifact) -> str:
    return _event("resource_artifact", **artifact.model_dump())


def bundle_event(bundle: ResourceBundle) -> str:
    return _event("resource_bundle", **bundle.model_dump())
