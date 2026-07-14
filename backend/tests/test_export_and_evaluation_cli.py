from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from backend.database import SessionLocal, init_db
from backend.evaluation.cli import evaluate_outputs
from backend.main import app
from backend.services import db as repo

RESOURCE = """【协议:learning-resource/v1】
主题：一次函数
画像版本：1
资源类型：笔记｜练习
目标难度：基础
【学习笔记】
一次函数可写为 y=kx+b。
【分层练习:基础】
题目1：求截距。
答案1：1
解析1：令 x=0。
【协议结束】"""
PROFILE = """【协议:learner-profile/v1】
画像版本：1
年级：初二
学科：数学
当前水平：基础
薄弱知识点：一次函数图像
学习风格偏好：视觉型
学习风格证据：偏好图像
认知层次：理解
学习目标：掌握一次函数
推荐难度：基础
置信度：0.80
待确认问题：无
【协议结束】"""


def _stored_resource(session_id: str, sources: list[dict[str, str]] | None = None) -> int:
    init_db()
    db = SessionLocal()
    try:
        session = repo.get_or_create_session(db, session_id)
        repo.set_state(db, session, repo.SessionState.DIAGNOSING)
        repo.set_state(db, session, repo.SessionState.PROFILE_READY)
        repo.save_profile(db, session, PROFILE)
        repo.begin_generation(db, session)
        return repo.complete_generation(db, session, "一次函数", "生成练习", RESOURCE, 1, sources).id
    finally:
        db.close()


def test_resource_export_is_scoped_to_its_session() -> None:
    session_id = f"export-{uuid.uuid4().hex}"
    resource_id = _stored_resource(session_id)
    with TestClient(app) as client:
        response = client.get(f"/api/sessions/{session_id}/resources/{resource_id}/export?format=markdown")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/markdown")
        assert 'attachment; filename="learning-resource-' in response.headers["content-disposition"]
        assert response.text == RESOURCE
        missing = client.get(f"/api/sessions/other/resources/{resource_id}/export")
        assert missing.status_code == 404
        assert missing.json()["code"] == "LEARNING_RESOURCE_NOT_FOUND"
        invalid = client.get(f"/api/sessions/{session_id}/resources/{resource_id}/export?format=pdf")
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "REQUEST_VALIDATION_ERROR"


def test_session_history_and_export_include_persisted_sources() -> None:
    session_id = f"export-source-{uuid.uuid4().hex}"
    source = {"title": "一次函数公开资料", "url": "https://example.test/linear", "snippet": "图像和斜率说明"}
    resource_id = _stored_resource(session_id, [source])
    with TestClient(app) as client:
        history = client.get(f"/api/sessions/{session_id}")
        assert history.status_code == 200
        assert history.json()["resources"][0]["sources"] == [source]

        response = client.get(f"/api/sessions/{session_id}/resources/{resource_id}/export?format=markdown")
        assert response.status_code == 200
        assert "【参考来源】" in response.text
        assert source["title"] in response.text
        assert source["url"] in response.text


def test_evaluation_cli_covers_sample_outputs() -> None:
    evaluation_dir = Path(__file__).parents[1] / "evaluation"
    report = evaluate_outputs(evaluation_dir / "cases.json", evaluation_dir / "sample_outputs.json", evaluation_dir / "baseline.json")
    assert report["all_cases_covered"] is True
    assert report["protocol_pass_rate"] == 1
    assert report["average_score"] == 100
    assert report["baseline_comparison"]["passed"] is True
