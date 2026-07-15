from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.schemas import SessionModelPreferenceResponse, SessionModelPreferenceUpdate
from backend.services import db as repo


router = APIRouter(prefix="/api/sessions", tags=["model-preferences"])
SessionPath = Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]


@router.get("/{session_id}/model-preference", response_model=SessionModelPreferenceResponse)
async def get_preference(session_id: SessionPath, db: Session = Depends(get_db)) -> SessionModelPreferenceResponse:
    return SessionModelPreferenceResponse.model_validate(
        repo.get_model_preference(db, session_id),
        from_attributes=True,
    )


@router.put("/{session_id}/model-preference", response_model=SessionModelPreferenceResponse)
async def put_preference(
    session_id: SessionPath,
    update: SessionModelPreferenceUpdate,
    db: Session = Depends(get_db),
) -> SessionModelPreferenceResponse:
    return SessionModelPreferenceResponse.model_validate(
        repo.upsert_model_preference(
            db,
            session_id,
            profile_mode=update.profile_mode,
            preferred_profile_id=update.preferred_profile_id,
            model_id=update.model_id,
            reasoning_effort=update.reasoning_effort,
            failover_override=update.failover_override,
        ),
        from_attributes=True,
    )
