import uuid

from fastapi.testclient import TestClient

from backend.database import SessionLocal, init_db
from backend.main import app
from backend.services import db as repo
from backend.services import learning

PROFILE = """【协议:learner-profile/v1】
画像版本：1
年级：初二
学科：数学
当前水平：基础
薄弱知识点：一次函数
学习风格偏好：视觉型
学习风格证据：偏好图像
认知层次：理解
学习目标：掌握一次函数
推荐难度：基础
置信度：0.80
待确认问题：无
【协议结束】"""

RESOURCE = """【协议:learning-resource/v1】
主题：一次函数
画像版本：1
资源类型：笔记｜练习
目标难度：基础
【学习笔记】
一次函数可写为 y=kx+b。
【分层练习:基础】
题目1：求 y=2x+1 的截距。
答案1：1
解析1：令 x=0，可得截距为 1。
【协议结束】"""


def _seed_learning_session() -> tuple[str, int, int]:
    init_db()
    session_id = f"learning-{uuid.uuid4().hex}"
    db = SessionLocal()
    try:
        session = repo.get_or_create_session(db, session_id)
        repo.set_state(db, session, repo.SessionState.DIAGNOSING)
        repo.set_state(db, session, repo.SessionState.PROFILE_READY)
        repo.save_profile(db, session, PROFILE)
        repo.begin_generation(db, session)
        resource = repo.complete_generation(db, session, "一次函数", "生成练习", RESOURCE, session.profile_version)
        return session_id, resource.id, resource.questions[0].id
    finally:
        db.close()


def test_generated_resource_indexes_questions_and_initial_progress() -> None:
    session_id, resource_id, question_id = _seed_learning_session()
    with TestClient(app) as client:
        history = client.get(f"/api/sessions/{session_id}")
        progress = client.get(f"/api/sessions/{session_id}/progress")

    assert history.status_code == 200
    question = history.json()["resources"][0]["questions"][0]
    assert question == {"id": question_id, "ordinal": 1, "difficulty": "基础", "prompt": "求 y=2x+1 的截距。"}
    assert history.json()["resources"][0]["id"] == resource_id
    assert history.json()["resources"][0]["quality_score"] == 75
    assert "QUESTION_COUNT_LOW" in history.json()["resources"][0]["quality_issues"]
    assert progress.status_code == 200
    assert progress.json()["knowledge_points"][0]["name"] == "一次函数"
    assert progress.json()["knowledge_points"][0]["mastery_score"] == 0.25


def test_answer_attempt_updates_mastery_review_queue_and_mistakes() -> None:
    session_id, _, question_id = _seed_learning_session()
    with TestClient(app) as client:
        wrong = client.post(
            f"/api/sessions/{session_id}/questions/{question_id}/attempts",
            json={"answer": "2", "idempotency_key": "attempt-001"},
        )
        duplicate = client.post(
            f"/api/sessions/{session_id}/questions/{question_id}/attempts",
            json={"answer": "2", "idempotency_key": "attempt-001"},
        )
        progress_after_wrong = client.get(f"/api/sessions/{session_id}/progress")
        due_reviews = client.get(f"/api/sessions/{session_id}/reviews?due_only=true")
        mistakes = client.get(f"/api/sessions/{session_id}/mistakes")
        correct = client.post(
            f"/api/sessions/{session_id}/questions/{question_id}/attempts",
            json={"answer": "1.0", "hint_count": 1, "idempotency_key": "attempt-002"},
        )
        future_reviews = client.get(f"/api/sessions/{session_id}/reviews")
        due_after_correct = client.get(f"/api/sessions/{session_id}/reviews?due_only=true")

    assert wrong.status_code == 200
    assert wrong.json()["correct"] is False
    assert wrong.json()["mastery_score"] < 0.25
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["attempt_id"] == wrong.json()["attempt_id"]
    assert progress_after_wrong.json()["total_attempts"] == 1
    assert progress_after_wrong.json()["learning_state_version"] == 1
    assert due_reviews.json()[0]["reason"] == "ANSWER_INCORRECT"
    assert mistakes.json()[0]["question_id"] == question_id
    assert correct.json()["correct"] is True
    assert correct.json()["mastery_score"] > wrong.json()["mastery_score"]
    assert future_reviews.json()[0]["reason"] == "SPACED_REVIEW"
    assert future_reviews.json()[0]["interval_days"] == 1
    assert due_after_correct.json() == []


def test_question_attempt_is_scoped_to_session_and_invalidates_old_cache() -> None:
    session_id, _, question_id = _seed_learning_session()
    other_session_id = f"other-{uuid.uuid4().hex}"
    db = SessionLocal()
    try:
        session = repo.get_session(db, session_id)
        assert session is not None
        assert repo.find_cached_resource(db, session, "生成练习", 86400) is not None
        result = learning.submit_attempt(db, session_id, question_id, "1")
        assert result is not None
        assert repo.find_cached_resource(db, session, "生成练习", 86400) is None
    finally:
        db.close()

    with TestClient(app) as client:
        response = client.post(
            f"/api/sessions/{other_session_id}/questions/{question_id}/attempts",
            json={"answer": "1"},
        )
    assert response.status_code == 404


def test_deleting_session_cascades_learning_records() -> None:
    session_id, _, question_id = _seed_learning_session()
    with TestClient(app) as client:
        attempt = client.post(
            f"/api/sessions/{session_id}/questions/{question_id}/attempts",
            json={"answer": "2"},
        )
        deleted = client.delete(f"/api/sessions/{session_id}")
    assert attempt.status_code == 200
    assert deleted.status_code == 204

    db = SessionLocal()
    try:
        assert db.query(repo.KnowledgePoint).filter_by(session_id=session_id).count() == 0
        assert db.query(repo.QuestionItem).filter_by(session_id=session_id).count() == 0
        assert db.query(repo.AnswerAttempt).filter_by(session_id=session_id).count() == 0
        assert db.query(repo.ReviewTask).filter_by(session_id=session_id).count() == 0
    finally:
        db.close()


def test_next_action_prioritizes_due_review_then_remediation() -> None:
    session_id, _, question_id = _seed_learning_session()
    with TestClient(app) as client:
        initial = client.get(f"/api/sessions/{session_id}/next-action")
        wrong = client.post(
            f"/api/sessions/{session_id}/questions/{question_id}/attempts",
            json={"answer": "2"},
        )
        due = client.get(f"/api/sessions/{session_id}/next-action")
        correct = client.post(
            f"/api/sessions/{session_id}/questions/{question_id}/attempts",
            json={"answer": "1"},
        )
        after_correct = client.get(f"/api/sessions/{session_id}/next-action")

    assert initial.json()["action"] == "START_PRACTICE"
    assert wrong.status_code == 200
    assert due.json()["action"] == "REVIEW"
    assert correct.status_code == 200
    assert after_correct.json()["action"] == "REMEDIATE"
    assert after_correct.json()["recommended_difficulty"] == "基础"


def test_answer_matching_preserves_math_absolute_value_symbols() -> None:
    expected = "|k| 越大，直线越陡。"
    assert learning.answers_match(expected, expected)
    assert learning.answers_match("答案 A", "答案 A｜答案 B")
    assert learning.answers_match("答案 B", "答案 A｜答案 B")
