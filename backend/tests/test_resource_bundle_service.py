from __future__ import annotations

import uuid

import pytest

from backend.database import SessionLocal, init_db
from backend.errors import UnexpectedBackendError
from backend.knowledge.context import KnowledgeCitation, KnowledgeContext
from backend.models.schemas import WebSearchResult
from backend.protocols.v2.models import (
    ArtifactStatus,
    ArtifactType,
    BundleStatus,
    ResourceArtifact,
    ResourceBundle,
)
from backend.services import db as repo
from backend.services.resource_bundle.pipeline import PipelineResult
from backend.services.resource_bundle.service import ResourceBundleService, ResourceSelection
from backend.services.resource_db import get_bundle_for_session


def _session_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _seed_profiled_session(session_id: str) -> None:
    init_db()
    with SessionLocal() as db:
        session = repo.get_or_create_session(db, session_id)
        session.state = repo.SessionState.PROFILED.value
        session.last_stable_state = repo.SessionState.PROFILED.value
        session.profile_text = "[协议 learning-profile/v1]\n学科: 数学\n[协议结束]"
        session.profile_version = 3
        session.learning_state_version = 7
        repo.commit(db)


def _bundle(bundle_id: str) -> ResourceBundle:
    artifact = ResourceArtifact(
        artifact_id=f"{bundle_id}-course",
        type=ArtifactType.COURSE_EXPLANATION,
        title="课程讲解",
        status=ArtifactStatus.SUCCEEDED,
        body="讲解内容",
        quality_score=90,
    )
    return ResourceBundle(
        bundle_id=bundle_id,
        topic="一次函数",
        profile_version=3,
        learning_state_version="7",
        mode="bundle",
        status=BundleStatus.COMPLETED,
        requested_types=[ArtifactType.COURSE_EXPLANATION],
        artifacts=[artifact],
        aggregate_quality=90,
        created_at="2026-07-17T00:00:00Z",
    )


class CapturingPipeline:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.failure = failure

    async def run(self, **kwargs):
        self.calls.append(kwargs)
        if self.failure is not None:
            raise self.failure
        return PipelineResult(bundle=_bundle(str(kwargs["bundle_id"])))


def _knowledge_context() -> KnowledgeContext:
    citation = KnowledgeCitation(
        reference_id="资料1",
        document_id=1,
        document_name="一次函数.md",
        locator_label="第 1 段",
        locator={"type": "paragraph", "start": 1, "end": 1},
        chunk_id=1,
        parser_version="chunk-v1",
        index_version="fts-v1",
        retrieval_mode="keyword",
    )
    return KnowledgeContext(
        prompt='<knowledge_data untrusted="true">\n[资料1] 一次函数定义\n</knowledge_data>',
        citations=(citation,),
        retrieval_mode="keyword",
    )


@pytest.mark.asyncio
async def test_service_passes_learning_knowledge_and_sources_to_pipeline() -> None:
    session_id = _session_id("bundle-service-context")
    _seed_profiled_session(session_id)
    pipeline = CapturingPipeline()
    service = ResourceBundleService(
        pipeline=pipeline,
        learning_context_provider=lambda _db, _sid: "薄弱知识点：斜率",
        knowledge_retriever=lambda _db, _sid, _query: _knowledge_context(),
        web_search=lambda _message: _async_value([
            WebSearchResult(
                title="公开课程",
                url="https://example.com/lesson",
                snippet="一次函数公开资料",
            )
        ]),
    )

    with SessionLocal() as db:
        result = await service.generate(
            db,
            session_id,
            "生成一次函数资源",
            ResourceSelection.bundle(),
            generation_id="generation-1",
        )
        session = repo.get_session(db, session_id)
        stored = get_bundle_for_session(db, session_id, result.bundle_id)

    call = pipeline.calls[0]
    assert call["learning_context"] == "薄弱知识点：斜率"
    assert "[资料1]" in str(call["knowledge_context"])
    assert "[资料2]" in str(call["knowledge_context"])
    assert call["source_allowlist"] == ["资料1", "资料2"]
    assert result.protocol_version == "learning-resource-bundle/v2"
    assert result.knowledge_sources[0]["reference_id"] == "资料1"
    assert result.public_sources[0]["reference_id"] == "资料2"
    assert session is not None and session.state == repo.SessionState.PROFILED.value
    assert stored is not None and stored["protocol_version"] == "learning-resource-bundle/v2"


@pytest.mark.asyncio
async def test_service_restores_profiled_state_and_maps_unexpected_failure() -> None:
    session_id = _session_id("bundle-service-failure")
    _seed_profiled_session(session_id)
    service = ResourceBundleService(
        pipeline=CapturingPipeline(failure=ValueError("private failure detail")),
        learning_context_provider=lambda _db, _sid: "",
        knowledge_retriever=lambda _db, _sid, _query: KnowledgeContext.empty(),
        web_search=lambda _message: _async_value([]),
    )

    with SessionLocal() as db:
        with pytest.raises(UnexpectedBackendError) as captured:
            await service.generate(
                db,
                session_id,
                "生成资源",
                ResourceSelection.bundle(),
                generation_id="generation-failure",
            )
        session = repo.get_session(db, session_id)

    assert captured.value.code == "BACKEND_UNEXPECTED_ERROR"
    assert "private failure detail" not in captured.value.public_message
    assert session is not None and session.state == repo.SessionState.PROFILED.value
    assert session.last_error_code == "BUNDLE_FAILED"


@pytest.mark.asyncio
async def test_v2_request_never_reads_v1_resource_cache(monkeypatch) -> None:
    session_id = _session_id("bundle-service-cache")
    _seed_profiled_session(session_id)
    pipeline = CapturingPipeline()
    service = ResourceBundleService(
        pipeline=pipeline,
        learning_context_provider=lambda _db, _sid: "",
        knowledge_retriever=lambda _db, _sid, _query: KnowledgeContext.empty(),
        web_search=lambda _message: _async_value([]),
    )

    def cache_must_not_be_read(*_args, **_kwargs):
        raise AssertionError("v2 generation must not read the v1 cache")

    monkeypatch.setattr(repo, "find_cached_resource", cache_must_not_be_read)
    with SessionLocal() as db:
        result = await service.generate(
            db,
            session_id,
            "same request",
            ResourceSelection.bundle(),
            generation_id="generation-cache",
        )

    assert result.protocol_version == "learning-resource-bundle/v2"
    assert len(pipeline.calls) == 1


async def _async_value(value):
    return value
