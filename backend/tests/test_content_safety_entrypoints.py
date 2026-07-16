from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from backend.database import SessionLocal, init_db
from backend.errors import ContentSecretDetectedError
from backend.models.schemas import ProfileRequest, ResourceRequest
from backend.protocols import DiagnosisDecision
from backend.routers import profile as profile_router
from backend.routers import resource as resource_router
from backend.services import db as repo
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

RESOURCE = """【协议:learning-resource/v1】
主题：一次函数
画像版本：1
资源类型：笔记｜练习
目标难度：基础
【学习目标】
理解斜率
【学习笔记】
UNSAFE-MARKER 一次函数是 y=kx+b。
【分层练习:基础】
题目1：斜率是什么？
答案1：变化率
解析1：表示因变量随自变量的变化速度。
【协议结束】"""


class FakeSafety:
    def __init__(self) -> None:
        self.request_inputs: list[str] = []
        self.output_inputs: list[str] = []

    async def gate_request(self, text, **_kwargs):
        self.request_inputs.append(text)
        if "SECRET-BLOCK" in text:
            raise ContentSecretDetectedError()
        return SimpleNamespace(
            safe_text=text.replace("13800138000", "[手机号已隐藏]"),
            metadata=None,
        )

    async def review_text(self, text, **_kwargs):
        self.output_inputs.append(text)
        return SimpleNamespace(
            safe_text=text.replace("UNSAFE-MARKER ", ""),
            metadata=None,
        )


def seed_profiled(session_id: str) -> None:
    init_db()
    with SessionLocal() as db:
        session = repo.get_or_create_session(db, session_id)
        session.state = repo.SessionState.PROFILED.value
        session.last_stable_state = repo.SessionState.PROFILED.value
        session.profile_text = PROFILE
        session.profile_version = 1
        repo.commit(db)


@pytest.mark.asyncio
async def test_secret_chat_is_blocked_before_message_persistence(monkeypatch):
    init_db()
    session_id = f"secret-entry-{uuid.uuid4().hex[:8]}"
    safety = FakeSafety()

    with SessionLocal() as db:
        with pytest.raises(ContentSecretDetectedError):
            await orchestrator.handle_message(
                db,
                session_id,
                "SECRET-BLOCK",
                safety_service=safety,
            )
        stored = db.query(repo.Message).filter_by(session_id=session_id).all()

    assert stored == []


@pytest.mark.asyncio
async def test_personal_data_chat_persists_only_redacted_text(monkeypatch):
    async def diagnosis(_history, turn, *, complete):
        return DiagnosisDecision(
            status="CONTINUE",
            current_turn=turn,
            confirmed_fields=[],
            missing_fields=["当前水平"],
            confidence=0.2,
            next_question="请补充当前水平",
            reason="信息不足",
        )

    monkeypatch.setattr(orchestrator, "generate_diagnosis_decision", diagnosis)
    init_db()
    session_id = f"pii-entry-{uuid.uuid4().hex[:8]}"
    safety = FakeSafety()

    with SessionLocal() as db:
        await orchestrator.handle_message(
            db,
            session_id,
            "电话 13800138000",
            safety_service=safety,
        )
        contents = [item.content for item in db.query(repo.Message).filter_by(session_id=session_id)]

    assert all("13800138000" not in content for content in contents)
    assert any("[手机号已隐藏]" in content for content in contents)


@pytest.mark.asyncio
async def test_stream_buffers_model_text_until_review_and_emits_no_provisional_delta(monkeypatch):
    session_id = f"safe-stream-{uuid.uuid4().hex[:8]}"
    seed_profiled(session_id)
    safety = FakeSafety()

    class Gateway:
        async def stream(self, messages, temperature=0.4):
            yield RESOURCE[:80]
            yield RESOURCE[80:]

    async def connected():
        return False

    async def no_web(_message):
        return []

    monkeypatch.setattr(orchestrator, "_gateway", Gateway())
    monkeypatch.setattr(orchestrator, "search_web_optional", no_web)
    with SessionLocal() as db:
        events = [
            event
            async for event in orchestrator.stream_message(
                db,
                session_id,
                "生成一次函数资料",
                connected,
                safety_service=safety,
            )
        ]

    assert not any(
        event["event"] == "delta" and event.get("provisional") is True
        for event in events
    )
    assert all("UNSAFE-MARKER" not in str(event) for event in events)
    assert any(
        event["event"] == "delta"
        and event.get("provisional") is False
        and "一次函数是" in str(event.get("content"))
        for event in events
    )


@pytest.mark.asyncio
async def test_standalone_profile_endpoint_gates_input_and_output(monkeypatch):
    safety = FakeSafety()

    async def complete(_selection, _messages, _temperature):
        return SimpleNamespace(text=PROFILE, profile_id="primary")

    monkeypatch.setattr(profile_router, "content_safety_service", safety, raising=False)
    monkeypatch.setattr(profile_router.model_runtime_router, "complete", complete)
    response = await profile_router.profile_endpoint(
        ProfileRequest(messages=["电话 13800138000"])
    )

    assert safety.request_inputs == ["电话 13800138000"]
    assert safety.output_inputs == [PROFILE]
    assert response.profile_text == PROFILE


@pytest.mark.asyncio
async def test_standalone_resource_endpoint_gates_profile_request_and_output(monkeypatch):
    safety = FakeSafety()

    async def complete(_selection, _messages, _temperature):
        return SimpleNamespace(text=RESOURCE, profile_id="primary")

    async def no_web(_message):
        return []

    monkeypatch.setattr(resource_router, "content_safety_service", safety, raising=False)
    monkeypatch.setattr(resource_router.model_runtime_router, "complete", complete)
    monkeypatch.setattr(resource_router, "search_web_optional", no_web)
    response = await resource_router.resource_endpoint(
        ResourceRequest(
            profile_text=PROFILE,
            message="电话 13800138000",
            use_web_search=False,
        )
    )

    assert safety.request_inputs == [PROFILE, "电话 13800138000"]
    assert safety.output_inputs == [RESOURCE]
    assert "UNSAFE-MARKER" not in response.resource_text
