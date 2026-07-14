import asyncio
import uuid

from backend.database import SessionLocal, init_db
from backend.protocols import DiagnosisDecision
from backend.errors import DomainStateError
from backend.services import db as repo
from backend.services import db as repo
from backend.services import orchestrator


VALID_PROFILE = """【协议:learner-profile/v1】
画像版本：1
年级：初二
学科：数学
当前水平：基础
薄弱知识点：一次函数图像
学习风格偏好：视觉型
学习风格证据：偏好图像
认知层次：理解
学习目标：掌握一次函数
推荐难度：基础｜提高
置信度：0.80
待确认问题：无
【协议结束】"""


def test_diagnosis_requires_follow_up_then_generates_profile(monkeypatch) -> None:
    async def continue_decision(history, turn):
        return DiagnosisDecision(
            status="CONTINUE", current_turn=turn, confirmed_fields=["学科"],
            missing_fields=["薄弱知识点"], confidence=0.4,
            next_question="你最容易在哪一步出错？", reason="需要定位薄弱点",
        )

    async def complete_decision(history, turn):
        return DiagnosisDecision(
            status="COMPLETE", current_turn=turn, confirmed_fields=["学科", "学习目标"],
            missing_fields=["无"], confidence=0.8,
            next_question="无", reason="信息已足够",
        )

    async def profile(history, profile_version):
        return VALID_PROFILE.replace("画像版本：1", f"画像版本：{profile_version}")

    init_db()
    session_id = f"test-{uuid.uuid4().hex}"
    monkeypatch.setattr(orchestrator, "generate_diagnosis_decision", continue_decision)
    db = SessionLocal()
    try:
        first = asyncio.run(orchestrator.handle_message(db, session_id, "我想学一次函数"))
        assert first.phase == "diagnosis"
        assert first.reply == "你最容易在哪一步出错？"
        session = repo.get_session(db, session_id)
        assert session.state == repo.SessionState.DIAGNOSING.value
        assert session.diagnosis_turns == 1

        monkeypatch.setattr(orchestrator, "generate_diagnosis_decision", complete_decision)
        monkeypatch.setattr(orchestrator, "generate_profile", profile)
        second = asyncio.run(orchestrator.handle_message(db, session_id, "画图和求解析式都会卡住"))
        assert second.phase == "profile"
        session = repo.get_session(db, session_id)
        assert session.state == repo.SessionState.PROFILED.value
        assert session.profile_version == 1
        assert "【协议:learner-profile/v1】" in session.profile_text
    finally:
        db.close()


def test_repository_rejects_illegal_state_transition() -> None:
    init_db()
    session_id = f"state-{uuid.uuid4().hex}"
    db = SessionLocal()
    try:
        session = repo.get_or_create_session(db, session_id)
        try:
            repo.set_state(db, session, repo.SessionState.PROFILED)
        except DomainStateError as exc:
            assert exc.code == "INVALID_STATE_TRANSITION"
        else:
            raise AssertionError("非法状态转换必须失败")
    finally:
        db.close()


def test_history_window_keeps_goal_and_most_recent_messages() -> None:
    init_db()
    session_id = f"history-{uuid.uuid4().hex}"
    db = SessionLocal()
    try:
        for message in ("goal", "old-middle", "recent-one", "recent-two"):
            repo.append_message(db, session_id, "user", message)

        history = repo.history_texts(db, session_id, maximum_messages=3, maximum_characters=14)

        assert history == ["goal", "recent-two"]
        assert "old-middle" not in history
        assert sum(len(message) for message in history) <= 14
    finally:
        db.close()
