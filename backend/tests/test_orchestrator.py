import asyncio
import uuid

from backend.database import SessionLocal, init_db
from backend.knowledge.chunking import chunk_blocks
from backend.knowledge.parsers import StructuredBlock
from backend.knowledge.repository import KnowledgeRepository
from backend.knowledge.search import KnowledgeSearchRepository
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

VALID_RESOURCE_WITH_CITATIONS = """【协议:learning-resource/v1】
主题：牛顿第二定律
画像版本：1
资源类型：笔记｜练习
目标难度：基础
【学习笔记】
牛顿第二定律说明物体加速度与合外力成正比、与质量成反比，可写成 F=ma。[资料1]伪造内容[资料99]
【分层练习:基础】
题目1：质量为 2 kg 的物体受到 6 N 合力，加速度是多少？
答案1：3 m/s²
解析1：根据 a=F/m=6/2=3 m/s²。
【协议结束】"""


def test_diagnosis_requires_follow_up_then_generates_profile(monkeypatch) -> None:
    async def continue_decision(history, turn, *, complete):
        return DiagnosisDecision(
            status="CONTINUE", current_turn=turn, confirmed_fields=["学科"],
            missing_fields=["薄弱知识点"], confidence=0.4,
            next_question="你最容易在哪一步出错？", reason="需要定位薄弱点",
        )

    async def complete_decision(history, turn, *, complete):
        return DiagnosisDecision(
            status="COMPLETE", current_turn=turn, confirmed_fields=["学科", "学习目标"],
            missing_fields=["无"], confidence=0.8,
            next_question="无", reason="信息已足够",
        )

    async def profile(history, profile_version, *, complete):
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


def test_bundle_stream_delegates_to_shared_service(monkeypatch) -> None:
    from backend.protocols.v2.models import (
        ArtifactStatus,
        ArtifactType,
        BundleStatus,
        ResourceArtifact,
        ResourceBundle,
    )

    init_db()
    session_id = f"bundle-shared-{uuid.uuid4().hex[:10]}"
    calls = []
    artifact = ResourceArtifact(
        artifact_id="bundle-stream-course",
        type=ArtifactType.COURSE_EXPLANATION,
        title="课程讲解",
        status=ArtifactStatus.SUCCEEDED,
        body="内容",
        quality_score=88,
    )
    bundle = ResourceBundle(
        bundle_id="bundle-stream-shared",
        topic="一次函数",
        profile_version=1,
        learning_state_version="1",
        mode="bundle",
        status=BundleStatus.COMPLETED,
        requested_types=[ArtifactType.COURSE_EXPLANATION],
        artifacts=[artifact],
        aggregate_quality=88,
        created_at="2026-07-17T00:00:00Z",
    )

    class FakeService:
        async def generate(
            self, db, requested_session_id, message, selection, *, on_event, **kwargs
        ):
            session = repo.get_session(db, requested_session_id)
            calls.append((requested_session_id, message, selection, session.state))
            await on_event({
                "event": "resource_plan",
                "bundle_id": bundle.bundle_id,
                "topic": bundle.topic,
                "requested_types": ["course_explanation"],
            })
            await on_event({"event": "resource_bundle", **bundle.model_dump(mode="json")})
            return bundle

    async def connected() -> bool:
        return False

    monkeypatch.setattr(orchestrator, "resource_bundle_service", FakeService(), raising=False)
    db = SessionLocal()
    try:
        session = repo.get_or_create_session(db, session_id)
        session.state = repo.SessionState.PROFILED.value
        session.last_stable_state = repo.SessionState.PROFILED.value
        session.profile_text = VALID_PROFILE
        session.profile_version = 1
        repo.commit(db)

        async def collect():
            return [event async for event in orchestrator.stream_message(
                db,
                session_id,
                "生成资源包",
                connected,
                resource_mode="bundle",
            )]

        events = asyncio.run(collect())
    finally:
        db.close()

    assert len(calls) == 1
    assert calls[0][0:2] == (session_id, "生成资源包")
    assert calls[0][2].mode.value == "bundle"
    assert calls[0][3] == repo.SessionState.PROFILED.value
    assert [event["event"] for event in events if event["event"].startswith("resource_")] == [
        "resource_plan",
        "resource_bundle",
    ]
    assert events[-1]["event"] == "done"
    assert events[-1]["state"] == repo.SessionState.PROFILED.value


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


def test_diagnosis_does_not_retrieve_local_knowledge_by_default(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    async def continue_decision(history, turn, *, complete):
        return DiagnosisDecision(
            status="CONTINUE",
            current_turn=turn,
            confirmed_fields=["学科"],
            missing_fields=["薄弱知识点"],
            confidence=0.4,
            next_question="你最容易在哪一步出错？",
            reason="需要定位薄弱点",
        )

    def retrieve(_db, session_id: str, query: str):
        calls.append((session_id, query))
        raise AssertionError("diagnosis must not retrieve knowledge")

    init_db()
    session_id = f"knowledge-diagnosis-{uuid.uuid4().hex}"
    monkeypatch.setattr(orchestrator, "generate_diagnosis_decision", continue_decision)
    monkeypatch.setattr(orchestrator, "retrieve_knowledge_context", retrieve, raising=False)
    db = SessionLocal()
    try:
        result = asyncio.run(orchestrator.handle_message(db, session_id, "我想学高数"))
        assert result.phase == "diagnosis"
        assert calls == []
    finally:
        db.close()


def test_resource_generation_uses_bound_knowledge_and_persists_safe_citations(
    monkeypatch,
) -> None:
    captured: dict[str, str] = {}

    async def no_web(_message: str):
        return []

    async def generate(
        profile_text,
        request_message,
        web_sources,
        learning_context="",
        knowledge_context="",
        *,
        complete,
    ):
        captured["knowledge_context"] = knowledge_context
        return VALID_RESOURCE_WITH_CITATIONS

    init_db()
    session_id = f"knowledge-resource-{uuid.uuid4().hex}"
    digest = uuid.uuid4().hex + uuid.uuid4().hex
    db = SessionLocal()
    try:
        session = repo.get_or_create_session(db, session_id)
        session.state = repo.SessionState.PROFILED.value
        session.last_stable_state = repo.SessionState.PROFILED.value
        session.profile_text = VALID_PROFILE
        session.profile_version = 1
        repo.commit(db)

        knowledge = KnowledgeRepository(db)
        collection = knowledge.create_collection(f"物理-{uuid.uuid4().hex[:8]}")
        document = knowledge.upsert_document(
            sha256=digest,
            display_name=r"C:\Users\alice\课程.md",
            extension=".md",
            mime_type="text/markdown",
            byte_size=64,
            object_relpath=f"objects/{digest}",
        )
        knowledge.link_document(collection.id, document.id)
        knowledge.replace_chunks(
            document.id,
            chunk_blocks(
                [
                    StructuredBlock(
                        text="牛顿第二定律是 F=ma。",
                        heading_path=("动力学",),
                        locator_type="sheet_rows",
                        locator_start=3,
                        locator_end=4,
                        sheet_name="file:///Users/alice/private/答案表",
                    )
                ],
                parser_version="chunk-v1",
            ),
        )
        KnowledgeSearchRepository(db).replace_document_index(document.id)
        knowledge.replace_session_collections(
            session_id,
            [collection.id],
            privacy_mode="allow_model_context",
        )

        monkeypatch.setattr(orchestrator, "search_web_optional", no_web)
        monkeypatch.setattr(orchestrator, "generate_resources", generate)
        result = asyncio.run(
            orchestrator.handle_message(db, session_id, "请讲解牛顿第二定律")
        )

        assert captured["knowledge_context"].startswith(
            '<knowledge_data untrusted="true">'
        )
        assert result.knowledge_sources[0]["reference_id"] == "资料1"
        assert "object_relpath" not in str(result.knowledge_sources)
        assert result.knowledge_sources[0]["document_name"] == "课程.md"
        assert result.knowledge_sources[0]["locator_label"] == "工作表 · 第 3–4 行"
        assert result.knowledge_sources[0]["locator"]["sheet_name"] == "工作表"
        assert "Users" not in str(result.knowledge_sources)
        assert "file://" not in str(result.knowledge_sources)
        assert "Users" not in captured["knowledge_context"]
        assert "[资料1]" in result.reply
        assert "[资料99]" not in result.reply
        stored = (
            db.query(repo.Resource)
            .filter(repo.Resource.session_id == session_id)
            .order_by(repo.Resource.id.desc())
            .first()
        )
        assert repo.resource_knowledge_sources(stored)[0]["document_name"] == "课程.md"
        assert "KNOWLEDGE_CITATION_UNKNOWN:资料99" in repo.resource_quality_issues(stored)
    finally:
        db.close()
