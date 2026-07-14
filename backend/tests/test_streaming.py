import asyncio
import uuid

from backend.database import SessionLocal, init_db
from backend.protocols import DiagnosisDecision
from backend.services import orchestrator


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
推荐难度：基础｜提高
置信度：0.80
待确认问题：无
【协议结束】"""


class FakeGateway:
    async def stream(self, messages, temperature=0.2):
        for part in (PROFILE[:60], PROFILE[60:]):
            yield part


def test_stream_emits_real_deltas_then_persists(monkeypatch) -> None:
    async def complete_decision(history, turn):
        return DiagnosisDecision(
            status="COMPLETE", current_turn=turn, confirmed_fields=["学科", "学习目标"],
            missing_fields=["无"], confidence=0.8, next_question="无", reason="信息足够",
        )

    async def connected():
        return False

    init_db()
    session_id = f"stream-{uuid.uuid4().hex}"
    monkeypatch.setattr(orchestrator, "generate_diagnosis_decision", complete_decision)
    monkeypatch.setattr(orchestrator, "_gateway", FakeGateway())
    db = SessionLocal()
    try:
        first_events = asyncio.run(_collect(orchestrator.stream_message(db, session_id, "我要学一次函数", connected)))
        assert any(event["event"] == "delta" for event in first_events)
        assert first_events[-1]["event"] == "done"

        second_events = asyncio.run(_collect(orchestrator.stream_message(db, session_id, "我最怕画图", connected)))
        assert any(event["event"] == "phase" and event["phase"] == "profile" for event in second_events)
        assert sum(1 for event in second_events if event["event"] == "delta") == 2
        assert any(event["event"] == "persisted" for event in second_events)
        assert second_events[-1]["status"] == "completed"
    finally:
        db.close()


async def _collect(stream):
    return [event async for event in stream]


def test_stream_can_be_cancelled_by_generation_id(monkeypatch) -> None:
    async def complete_decision(history, turn):
        return DiagnosisDecision(
            status="COMPLETE", current_turn=turn, confirmed_fields=["学科"],
            missing_fields=["无"], confidence=0.8, next_question="无", reason="信息足够",
        )

    async def connected():
        return False

    init_db()
    session_id = f"cancel-{uuid.uuid4().hex}"
    monkeypatch.setattr(orchestrator, "generate_diagnosis_decision", complete_decision)
    monkeypatch.setattr(orchestrator, "_gateway", FakeGateway())
    db = SessionLocal()
    try:
        asyncio.run(_collect(orchestrator.stream_message(db, session_id, "我要学一次函数", connected)))
        events = asyncio.run(_cancel_after_profile_phase(orchestrator.stream_message(db, session_id, "我最怕画图", connected), session_id))
        assert any(event["event"] == "error" and event["code"] == "CLIENT_CANCELLED" for event in events)
        assert events[-1]["status"] == "cancelled"
    finally:
        db.close()


def test_stream_unexpected_error_uses_structured_events(monkeypatch) -> None:
    async def complete_decision(history, turn):
        return DiagnosisDecision(
            status="COMPLETE", current_turn=turn, confirmed_fields=["学科"],
            missing_fields=["无"], confidence=0.8, next_question="无", reason="信息足够",
        )

    class BrokenGateway:
        async def stream(self, messages, temperature=0.2):
            raise RuntimeError("unexpected failure")
            yield ""

    async def connected():
        return False

    init_db()
    session_id = f"stream-error-{uuid.uuid4().hex}"
    monkeypatch.setattr(orchestrator, "generate_diagnosis_decision", complete_decision)
    monkeypatch.setattr(orchestrator, "_gateway", BrokenGateway())
    db = SessionLocal()
    try:
        asyncio.run(_collect(orchestrator.stream_message(db, session_id, "我要学一次函数", connected)))
        events = asyncio.run(_collect(orchestrator.stream_message(db, session_id, "我最怕画图", connected)))
        assert any(event["event"] == "error" and event["code"] == "BACKEND_UNEXPECTED_ERROR" for event in events)
        assert events[-1]["event"] == "done"
        assert events[-1]["status"] == "failed"
    finally:
        db.close()


async def _cancel_after_profile_phase(stream, session_id: str):
    events = []
    async for event in stream:
        events.append(event)
        if event["event"] == "phase" and event["phase"] == "profile":
            assert not orchestrator.cancel_generation(event["generation_id"], "other-session")
            assert orchestrator.cancel_generation(event["generation_id"], session_id)
    return events
