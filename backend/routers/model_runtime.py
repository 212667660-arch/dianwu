from __future__ import annotations

from fastapi import APIRouter

from backend.models.schemas import (
    ModelConnectionTestResponse,
    ModelProfileSecret,
    ModelRuntimeSnapshotInput,
    ModelRuntimeStatusResponse,
)
from backend.services.model_runtime import model_runtime_router


router = APIRouter(prefix="/internal/model-runtime", include_in_schema=False)


def _status_response(value) -> ModelRuntimeStatusResponse:
    return ModelRuntimeStatusResponse.model_validate(value, from_attributes=True)


@router.post("/bootstrap", response_model=ModelRuntimeStatusResponse)
async def bootstrap(snapshot: ModelRuntimeSnapshotInput) -> ModelRuntimeStatusResponse:
    return _status_response(await model_runtime_router.apply_snapshot(snapshot))


@router.post("/test", response_model=ModelConnectionTestResponse)
async def test_profile(profile: ModelProfileSecret) -> ModelConnectionTestResponse:
    return await model_runtime_router.test_profile(profile)


@router.put("/snapshot", response_model=ModelRuntimeStatusResponse)
async def apply_snapshot(snapshot: ModelRuntimeSnapshotInput) -> ModelRuntimeStatusResponse:
    return _status_response(await model_runtime_router.apply_snapshot(snapshot))


@router.get("/status", response_model=ModelRuntimeStatusResponse)
async def runtime_status() -> ModelRuntimeStatusResponse:
    return _status_response(model_runtime_router.status())
