from __future__ import annotations

from fastapi.testclient import TestClient

from backend.database import SessionLocal
from backend.demo.fixtures import DEMO_LICENSE, DEMO_SESSION_ID, DEMO_TEXTBOOK_TEXT
from backend.main import app
from backend.services import db as repo
from backend.services.resource_db import list_bundles
from backend.knowledge.models import KnowledgeChunk


def _cleanup() -> None:
    with SessionLocal() as db:
        repo.delete_session(db, DEMO_SESSION_ID)


def test_demo_seed_is_idempotent_original_and_available_without_a_model() -> None:
    _cleanup()
    try:
        with TestClient(app) as client:
            first = client.post("/api/demo/seed")
            second = client.post("/api/demo/seed")

        assert first.status_code == 200
        assert second.status_code == 200
        payload = first.json()
        assert payload["session_id"] == DEMO_SESSION_ID
        assert payload["dataset"]["license"] == "CC0-1.0"
        assert DEMO_LICENSE == "CC0-1.0"
        assert "人民教育出版社" not in DEMO_TEXTBOOK_TEXT
        assert payload["mastery_before"][0]["score"] < payload["mastery_after"][0]["score"]
        assert [step["status"] for step in payload["agent_steps"]] == ["COMPLETED"] * 5
        assert payload["mode"] in {"offline", "online_assisted"}
        if payload["mode"] == "offline":
            assert "模型不可用" in payload["degradation_message"]

        with SessionLocal() as db:
            session = repo.get_session(db, DEMO_SESSION_ID)
            assert session is not None
            assert len(session.resources) == 1
            bundles = list_bundles(db, DEMO_SESSION_ID)
            assert len(bundles) == 1
            source = bundles[0]["knowledge_sources"][0]
            chunk = db.get(KnowledgeChunk, source["chunk_id"])
            assert chunk is not None
            assert (chunk.locator_start, chunk.locator_end) == (2, 2)
    finally:
        _cleanup()


def test_demo_reset_recreates_one_clean_workspace() -> None:
    _cleanup()
    try:
        with TestClient(app) as client:
            client.post("/api/demo/seed")
            reset = client.post("/api/demo/reset")
            status = client.get("/api/demo/status")

        assert reset.status_code == 200
        assert reset.json()["session_id"] == DEMO_SESSION_ID
        assert status.status_code == 200
        assert status.json()["seeded"] is True
        with SessionLocal() as db:
            session = repo.get_session(db, DEMO_SESSION_ID)
            assert session is not None
            assert len(session.resources) == 1
            assert len(list_bundles(db, DEMO_SESSION_ID)) == 1
    finally:
        _cleanup()
