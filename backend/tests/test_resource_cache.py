import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.database import SessionLocal, init_db
from backend.main import app
from backend.models.schemas import WebSearchResult
from backend.routers import chat
from backend.services import db as repo
from backend.services import orchestrator
from backend.services.content_safety.models import (
    RiskLevel,
    SafetyAction,
    SafetyMetadata,
    SafetyStage,
)
from backend.services.content_safety.policy import evaluate_context

RESOURCE = """【协议:learning-resource/v1】
主题：一次函数图像
画像版本：1
资源类型：笔记｜练习
目标难度：基础
【学习笔记】
斜率决定图像倾斜方向。
【分层练习:基础】
题目1：画出 y=x 的图像。
答案1：取两个点后连线。
解析1：令 x 分别为 0 和 1，得到两个点。
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
推荐难度：基础｜提高
置信度：0.80
待确认问题：无
【协议结束】"""


def _allow_metadata() -> SafetyMetadata:
    return SafetyMetadata(
        stage=SafetyStage.ARTIFACT,
        decision=SafetyAction.ALLOW,
        risk_level=RiskLevel.LOW,
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


class AllowSafety:
    async def gate_request(self, text, **_kwargs):
        return SimpleNamespace(safe_text=text, metadata=_allow_metadata())

    async def review_text(self, text, **_kwargs):
        return SimpleNamespace(safe_text=text, metadata=_allow_metadata())

    def filter_context(self, text):
        decision = evaluate_context(text)
        return SimpleNamespace(
            safe_text=decision.safe_text,
            metadata=decision.metadata,
        )


def _profiled_session(db, session_id: str):
    session = repo.get_or_create_session(db, session_id)
    repo.set_state(db, session, repo.SessionState.DIAGNOSING)
    repo.set_state(db, session, repo.SessionState.PROFILE_READY)
    repo.save_profile(db, session, PROFILE)
    return session


def test_identical_resource_request_uses_persistent_cache(monkeypatch) -> None:
    calls = 0

    async def generate_resources(profile_text: str, request_message: str, sources, learning_context="", *, complete) -> str:
        nonlocal calls
        assert "一次函数图像" in learning_context
        calls += 1
        return RESOURCE

    init_db()
    db = SessionLocal()
    session_id = f"cache-{uuid.uuid4().hex}"
    monkeypatch.setattr(orchestrator, "generate_resources", generate_resources)
    async def no_search(query: str):
        return []

    monkeypatch.setattr(orchestrator, "search_web_optional", no_search)
    try:
        _profiled_session(db, session_id)
        safety = AllowSafety()
        first = asyncio.run(orchestrator.handle_message(
            db, session_id, "生成一次函数练习", safety_service=safety,
        ))
        second = asyncio.run(orchestrator.handle_message(
            db, session_id, "生成一次函数练习", safety_service=safety,
        ))
        assert first.cached is False
        assert second.cached is True
        assert calls == 1
        session = repo.get_session(db, session_id)
        assert session is not None
        assert len(session.resources) == 1
    finally:
        db.close()


def test_legacy_resource_without_safety_metadata_is_not_a_cache_hit() -> None:
    init_db()
    db = SessionLocal()
    session_id = f"legacy-cache-{uuid.uuid4().hex}"
    try:
        session = _profiled_session(db, session_id)
        repo.begin_generation(db, session)
        legacy = repo.complete_generation(
            db,
            session,
            "一次函数图像",
            "生成一次函数练习",
            RESOURCE,
            session.profile_version,
        )

        assert legacy.safety_json is None
        assert (
            repo.find_cached_resource(
                db,
                session,
                "生成一次函数练习",
                86400,
            )
            is None
        )
    finally:
        db.close()


def test_resource_with_valid_safety_metadata_remains_cacheable() -> None:
    init_db()
    db = SessionLocal()
    session_id = f"safe-cache-{uuid.uuid4().hex}"
    try:
        session = _profiled_session(db, session_id)
        repo.begin_generation(db, session)
        stored = repo.complete_generation(
            db,
            session,
            "一次函数图像",
            "生成一次函数练习",
            RESOURCE,
            session.profile_version,
            safety_metadata=SafetyMetadata(
                stage=SafetyStage.ARTIFACT,
                decision=SafetyAction.ALLOW,
                risk_level=RiskLevel.LOW,
                checked_at=datetime.now(timezone.utc).isoformat(),
            ),
        )

        assert (
            repo.find_cached_resource(
                db,
                session,
                "生成一次函数练习",
                86400,
            )
            == stored
        )
    finally:
        db.close()


def test_streamed_identical_request_emits_cache_event(monkeypatch) -> None:
    async def disconnected() -> bool:
        return False

    init_db()
    db = SessionLocal()
    session_id = f"stream-cache-{uuid.uuid4().hex}"
    try:
        session = _profiled_session(db, session_id)
        repo.begin_generation(db, session)
        source = {"title": "一次函数资料", "url": "https://example.test/linear", "snippet": "图像与斜率讲解"}
        stored = repo.complete_generation(
            db,
            session,
            "一次函数图像",
            "生成一次函数练习",
            RESOURCE,
            session.profile_version,
            [source],
            safety_metadata=_allow_metadata(),
        )
        events = asyncio.run(_collect(orchestrator.stream_message(
            db,
            session_id,
            "生成一次函数练习",
            disconnected,
            safety_service=AllowSafety(),
        )))
        assert any(event["event"] == "cache" and event["resource_id"] == stored.id for event in events)
        assert any(event["event"] == "sources" and event["cached"] is True and event["sources"] == [source] for event in events)
        assert events[-1]["cached"] is True
    finally:
        db.close()


def test_resource_sources_are_persisted_and_reused_by_cache(monkeypatch) -> None:
    source = WebSearchResult(title="一次函数资料", url="https://example.test/linear", snippet="图像与斜率讲解")

    async def generate_resources(profile_text: str, request_message: str, sources: list[dict[str, str]], learning_context="", *, complete) -> str:
        assert sources == [{**source.model_dump(), "reference_id": "资料1"}]
        assert "一次函数图像" in learning_context
        return RESOURCE

    async def search(query: str) -> list[WebSearchResult]:
        return [source]

    init_db()
    db = SessionLocal()
    session_id = f"source-cache-{uuid.uuid4().hex}"
    monkeypatch.setattr(orchestrator, "generate_resources", generate_resources)
    monkeypatch.setattr(orchestrator, "search_web_optional", search)
    try:
        _profiled_session(db, session_id)
        safety = AllowSafety()
        first = asyncio.run(orchestrator.handle_message(
            db, session_id, "生成一次函数练习", safety_service=safety,
        ))
        second = asyncio.run(orchestrator.handle_message(
            db, session_id, "生成一次函数练习", safety_service=safety,
        ))
        assert first.sources == [source.model_dump()]
        assert second.cached is True
        assert second.sources == [source.model_dump()]
        session = repo.get_session(db, session_id)
        assert session is not None
        assert repo.resource_sources(session.resources[0]) == [source.model_dump()]
    finally:
        db.close()


def test_legacy_resource_accepts_server_assigned_public_citation(monkeypatch) -> None:
    source = WebSearchResult(
        title="一次函数资料",
        url="https://example.test/linear",
        snippet="图像与斜率讲解",
    )
    cited_resource = RESOURCE.replace(
        "斜率决定图像倾斜方向。",
        "斜率决定图像倾斜方向。[资料1]",
    )
    captured = {}

    async def generate_resources(
        profile_text,
        request_message,
        sources,
        learning_context="",
        *,
        complete,
    ):
        captured["sources"] = sources
        return cited_resource

    async def search(_query):
        return [source]

    init_db()
    db = SessionLocal()
    session_id = f"public-citation-{uuid.uuid4().hex}"
    monkeypatch.setattr(orchestrator, "generate_resources", generate_resources)
    monkeypatch.setattr(orchestrator, "search_web_optional", search)
    try:
        _profiled_session(db, session_id)
        result = asyncio.run(orchestrator.handle_message(
            db,
            session_id,
            "生成一次函数练习",
            safety_service=AllowSafety(),
        ))

        assert captured["sources"][0]["reference_id"] == "资料1"
        assert "[资料1]" in result.reply
        assert result.sources == [source.model_dump()]
    finally:
        db.close()


def test_streamed_resource_emits_sources_before_persistence(monkeypatch) -> None:
    source = WebSearchResult(title="一次函数资料", url="https://example.test/linear", snippet="图像与斜率讲解")

    class ResourceGateway:
        async def stream(self, messages, temperature=0.4):
            yield RESOURCE

    async def disconnected() -> bool:
        return False

    async def search(query: str) -> list[WebSearchResult]:
        return [source]

    init_db()
    db = SessionLocal()
    session_id = f"stream-source-{uuid.uuid4().hex}"
    monkeypatch.setattr(orchestrator, "_gateway", ResourceGateway())
    monkeypatch.setattr(orchestrator, "search_web_optional", search)
    try:
        _profiled_session(db, session_id)
        events = asyncio.run(_collect(orchestrator.stream_message(db, session_id, "生成一次函数练习", disconnected)))
        source_index = next(index for index, event in enumerate(events) if event["event"] == "sources")
        persisted_index = next(index for index, event in enumerate(events) if event["event"] == "persisted")
        assert source_index < persisted_index
        assert events[source_index]["sources"] == [source.model_dump()]
        session = repo.get_session(db, session_id)
        assert session is not None
        assert repo.resource_sources(session.resources[0]) == [source.model_dump()]
    finally:
        db.close()


def test_chat_response_includes_resource_sources(monkeypatch) -> None:
    source = {"title": "一次函数资料", "url": "https://example.test/linear", "snippet": "图像与斜率讲解"}

    async def resource_reply(*args, **kwargs):
        return orchestrator.ChatResult(
            RESOURCE,
            "resource",
            repo.SessionState.PROFILED.value,
            profile_version=1,
            sources=[source],
        )

    monkeypatch.setattr(chat, "handle_message", resource_reply)
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"session_id": f"chat-source-{uuid.uuid4().hex}", "message": "生成一次函数练习"})
    assert response.status_code == 200
    assert response.json()["sources"] == [source]


async def _collect(stream):
    return [event async for event in stream]
