from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, Request

from backend.models.schemas import ModelConnectionTestResponse, ModelSettingsResponse, ModelSettingsUpdate
from backend.services.model_settings import current_model_settings, save_model_settings, test_model_connection, verify_desktop_token

router = APIRouter(prefix="/api/settings/model", tags=["model-settings"])


@router.get("", response_model=ModelSettingsResponse)
async def get_model_settings(request: Request, x_a3_desktop_token: Optional[str] = Header(default=None)) -> ModelSettingsResponse:
    verify_desktop_token(x_a3_desktop_token, request.client.host if request.client else None)
    return current_model_settings()


@router.put("", response_model=ModelSettingsResponse)
async def update_model_settings(
    update: ModelSettingsUpdate,
    request: Request,
    x_a3_desktop_token: Optional[str] = Header(default=None),
) -> ModelSettingsResponse:
    verify_desktop_token(x_a3_desktop_token, request.client.host if request.client else None)
    return save_model_settings(update)


@router.post("/test", response_model=ModelConnectionTestResponse)
async def test_model_settings(
    update: ModelSettingsUpdate,
    request: Request,
    x_a3_desktop_token: Optional[str] = Header(default=None),
) -> ModelConnectionTestResponse:
    verify_desktop_token(x_a3_desktop_token, request.client.host if request.client else None)
    return await test_model_connection(update)
