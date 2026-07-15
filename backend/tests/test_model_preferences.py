from __future__ import annotations

from fastapi.testclient import TestClient

from backend.database import SessionLocal, init_db
from backend.main import app
from backend.services import db as repo


def test_session_model_preference_defaults_and_persists_override() -> None:
    init_db()
    session_id = "model-pref-default"
    db = SessionLocal()
    try:
        repo.get_or_create_session(db, session_id)
    finally:
        db.close()

    with TestClient(app) as client:
        default = client.get(f"/api/sessions/{session_id}/model-preference")
        updated = client.put(
            f"/api/sessions/{session_id}/model-preference",
            json={
                "profile_mode": "manual",
                "preferred_profile_id": "backup_1",
                "model_id": "reasoning-model",
                "reasoning_effort": "high",
                "failover_override": "off",
            },
        )
        loaded = client.get(f"/api/sessions/{session_id}/model-preference")

    assert default.status_code == 200
    assert default.json() == {
        "session_id": session_id,
        "profile_mode": "auto",
        "preferred_profile_id": None,
        "model_id": None,
        "reasoning_effort": "auto",
        "failover_override": "inherit",
    }
    assert updated.status_code == 200
    assert loaded.json() == updated.json()
    assert loaded.json()["preferred_profile_id"] == "backup_1"


def test_model_preference_rejects_invalid_ids_with_safe_envelope() -> None:
    init_db()
    session_id = "model-pref-invalid"
    db = SessionLocal()
    try:
        repo.get_or_create_session(db, session_id)
    finally:
        db.close()
    with TestClient(app) as client:
        response = client.put(
            f"/api/sessions/{session_id}/model-preference",
            json={
                "profile_mode": "manual",
                "preferred_profile_id": "../secret",
                "model_id": None,
                "reasoning_effort": "auto",
                "failover_override": "inherit",
            },
        )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_ERROR"
    assert "secret" not in response.text


def test_deleting_session_cascades_model_preference() -> None:
    init_db()
    session_id = "model-pref-delete"
    db = SessionLocal()
    try:
        repo.get_or_create_session(db, session_id)
        repo.upsert_model_preference(
            db,
            session_id,
            profile_mode="manual",
            preferred_profile_id="primary",
            model_id=None,
            reasoning_effort="medium",
            failover_override="inherit",
        )
        assert db.query(repo.SessionModelPreference).filter_by(session_id=session_id).count() == 1
        assert repo.delete_session(db, session_id) is True
        assert db.query(repo.SessionModelPreference).filter_by(session_id=session_id).count() == 0
    finally:
        db.close()
