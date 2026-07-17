from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.demo.service import demo_snapshot, reset_demo, seed_demo
from backend.demo.fixtures import DEMO_SESSION_ID
from backend.services import db as repo


router = APIRouter(prefix="/api/demo", tags=["competition-demo"])


@router.post("/seed")
async def seed(db: Session = Depends(get_db)) -> dict[str, object]:
    return seed_demo(db)


@router.post("/reset")
async def reset(db: Session = Depends(get_db)) -> dict[str, object]:
    return reset_demo(db)


@router.get("/status")
async def status(db: Session = Depends(get_db)) -> dict[str, object]:
    if repo.get_session(db, DEMO_SESSION_ID) is None:
        return {"session_id": DEMO_SESSION_ID, "seeded": False}
    return demo_snapshot(db)
