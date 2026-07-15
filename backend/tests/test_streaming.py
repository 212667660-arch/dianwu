import asyncio
import uuid

from backend.database import SessionLocal, init_db
from backend.knowledge.chunking import chunk_blocks
from backend.knowledge.parsers import StructuredBlock
from backend.knowledge.repository import KnowledgeRepository
from backend.knowledge.search import KnowledgeSearchRepository
from backend.protocols import DiagnosisDecision
from backend.services import db as repo
from backend.services import orchestrator
from backend.services.model_runtime import RoutedStreamEvent


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
主题：牛顿第二定律
画像版本：1
资源类型：笔记｜练习
目标难度：基础
【学习笔记】
牛顿第二定律说明合外力等于质量和加速度的乘积，即 F=ma。[资料1]
【分层练习:基础】
题目1：质量 2 kg、合力 8 N 时加速度是多少？
答案1：4 m/s²
解析1：a=F/m=8/2=4 m/s²。
【协议结束】"""


class FakeGateway:
    async def stream(self, messages, temperature=0.2):
        for part in (PROFILE[:60], PROFILE[60:]):
            yield part


class ResourceGateway:
    async def stream(self, messages, temperature=0.4):
        assert any('<knowledge_data untrusted="true">' in item["content"] for item in messages)
        for part in (RESOURCE[:80], RESOURCE[80:]):
            yield part


def test_stream_emits_real_deltas_then_persists(monkeypatch) -> None:
    async def complete_decision(history, turn, *, complete):
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
    async def complete_decision(history, turn, *, complete):
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
    async def complete_decision(history, turn, *, complete):
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


def test_resource_stream_emits_knowledge_sources_before_first_delta(monkeypatch) -> None:
    async def connected():
        return False

    async def no_web(_message: str):
        return []

    init_db()
    session_id = f"knowledge-stream-{uuid.uuid4().hex}"
    digest = uuid.uuid4().hex + uuid.uuid4().hex
    db = SessionLocal()
    try:
        session = repo.get_or_create_session(db, session_id)
        session.state = repo.SessionState.PROFILED.value
        session.last_stable_state = repo.SessionState.PROFILED.value
        session.profile_text = PROFILE
        session.profile_version = 1
        repo.commit(db)
        knowledge = KnowledgeRepository(db)
        collection = knowledge.create_collection(f"流式资料-{uuid.uuid4().hex[:8]}")
        document = knowledge.upsert_document(
            sha256=digest,
            display_name="file:///Users/alice/物理讲义.md",
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
                        locator_start=2,
                        locator_end=3,
                        sheet_name=r"C:\Users\alice\答案表",
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
        monkeypatch.setattr(orchestrator, "_gateway", ResourceGateway())

        events = asyncio.run(
            _collect(
                orchestrator.stream_message(
                    db,
                    session_id,
                    "请讲解牛顿第二定律",
                    connected,
                )
            )
        )

        source_index = next(
            index for index, event in enumerate(events)
            if event["event"] == "knowledge_sources"
        )
        delta_index = next(
            index for index, event in enumerate(events)
            if event["event"] == "delta"
        )
        assert source_index < delta_index
        source = events[source_index]["sources"][0]
        assert source["reference_id"] == "资料1"
        assert source["document_name"] == "物理讲义.md"
        assert source["locator_label"] == "工作表 · 第 2–3 行"
        assert source["locator"]["sheet_name"] == "工作表"
        assert "text" not in source
        assert "object_relpath" not in source
        assert "Users" not in str(source)
        assert "file://" not in str(source)
        assert events[-1]["status"] == "completed"
    finally:
        db.close()


def test_runtime_stream_interruption_preserves_delta_and_emits_metadata(monkeypatch) -> None:
    class InterruptedGateway:
        async def stream(self, messages, temperature=0.4):
            yield RoutedStreamEvent(
                event="meta",
                profile_id="backup",
                model_id="model-b",
                requested_reasoning_effort="high",
                effective_reasoning_effort="medium",
                failover_used=True,
            )
            yield RoutedStreamEvent(event="delta", content="partial")
            yield RoutedStreamEvent(
                event="interrupted",
                profile_id="backup",
                model_id="model-b",
                code="MODEL_STREAM_INTERRUPTED",
                can_continue_with_backup=True,
            )

    async def connected():
        return False

    async def no_web(_message: str):
        return []

    init_db()
    session_id = f"runtime-interrupted-{uuid.uuid4().hex}"
    db = SessionLocal()
    try:
        session = repo.get_or_create_session(db, session_id)
        session.state = repo.SessionState.PROFILED.value
        session.last_stable_state = repo.SessionState.PROFILED.value
        session.profile_text = PROFILE
        session.profile_version = 1
        repo.commit(db)
        monkeypatch.setattr(orchestrator, "search_web_optional", no_web)
        monkeypatch.setattr(orchestrator, "_gateway", InterruptedGateway())

        events = asyncio.run(_collect(orchestrator.stream_message(
            db,
            session_id,
            "继续学习",
            connected,
        )))

        meta = next(event for event in events if event["event"] == "meta")
        assert meta["profile_id"] == "backup"
        assert meta["failover_used"] is True
        assert any(event["event"] == "delta" and event["content"] == "partial" for event in events)
        interrupted = next(event for event in events if event["event"] == "interrupted")
        assert interrupted["can_continue_with_backup"] is True
        assert not any(event["event"] == "replace" for event in events)
        assert events[-1]["event"] == "done"
        assert events[-1]["status"] == "interrupted"
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
