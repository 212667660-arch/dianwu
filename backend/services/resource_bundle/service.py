from __future__ import annotations

import html
import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable

from sqlalchemy.orm import Session

from backend.errors import (
    AppError,
    DomainStateError,
    ResourceNotFoundError,
    UnexpectedBackendError,
)
from backend.knowledge.context import (
    KnowledgeContext,
    citation_payload,
    retrieve_knowledge_context,
)
from backend.protocols import parse_profile
from backend.protocols.v2.models import (
    ArtifactStatus,
    ArtifactType,
    ResourceArtifact,
    ResourceBundle,
    ResourceMode,
)
from backend.services import db as repo
from backend.services import learning
from backend.services.model_runtime import RuntimeSelection, model_runtime_router
from backend.services.content_safety.models import SafetyMetadata
from backend.services.content_safety.service import content_safety_service
from backend.services.resource_bundle.cancel import (
    cancel_bundle,
    cleanup_cancellation,
    get_or_create_cancellation,
)
from backend.services.resource_bundle.aggregator import aggregate_bundle
from backend.services.resource_bundle.pipeline import BundlePipeline
from backend.services.resource_db import (
    delete_bundle,
    get_bundle_for_session,
    save_bundle,
)
from backend.services.web_search import search_web_optional


logger = logging.getLogger(__name__)
EventSink = Callable[[dict[str, object]], Awaitable[None] | None]
DisconnectCheck = Callable[[], Awaitable[bool]]


@dataclass(frozen=True)
class ResourceSelection:
    mode: ResourceMode
    resource_type: ArtifactType | None = None

    def __post_init__(self) -> None:
        if self.mode == ResourceMode.SINGLE and self.resource_type is None:
            raise ValueError("single resource selection requires resource_type")
        if self.mode == ResourceMode.BUNDLE and self.resource_type is not None:
            raise ValueError("bundle resource selection does not accept resource_type")

    @classmethod
    def bundle(cls) -> "ResourceSelection":
        return cls(mode=ResourceMode.BUNDLE)

    @classmethod
    def single(cls, resource_type: ArtifactType) -> "ResourceSelection":
        return cls(mode=ResourceMode.SINGLE, resource_type=resource_type)


def build_knowledge_retrieval_query(db: Session, session_id: str, message: str) -> str:
    weak_points = (
        db.query(repo.KnowledgePoint)
        .filter_by(session_id=session_id)
        .order_by(repo.KnowledgePoint.mastery_score, repo.KnowledgePoint.updated_at.desc())
        .limit(3)
        .all()
    )
    due_reviews = (
        db.query(repo.ReviewTask)
        .filter(
            repo.ReviewTask.session_id == session_id,
            repo.ReviewTask.status == "PENDING",
            repo.ReviewTask.due_at <= datetime.now(),
        )
        .order_by(repo.ReviewTask.due_at, repo.ReviewTask.id)
        .limit(3)
        .all()
    )
    parts = [message]
    parts.extend(point.name for point in weak_points)
    parts.extend(task.knowledge_point.name for task in due_reviews)
    return " ".join(dict.fromkeys(part.strip() for part in parts if part.strip()))


def knowledge_source_payload(context: KnowledgeContext) -> list[dict[str, object]]:
    return [citation_payload(citation) for citation in context.citations]


def _public_source_context(
    sources: list[Any],
    *,
    first_reference: int,
) -> tuple[str, list[dict[str, object]]]:
    if not sources:
        return "", []
    sections = ['<public_sources untrusted="true">']
    snapshots: list[dict[str, object]] = []
    for offset, source in enumerate(sources[:8]):
        reference_id = f"资料{first_reference + offset}"
        source_data = source.model_dump() if hasattr(source, "model_dump") else dict(source)
        title = str(source_data.get("title") or "公开资料")[:300]
        snippet = str(source_data.get("snippet") or "")[:1000]
        url = str(source_data.get("url") or "")[:2048]
        sections.append(
            f"[{reference_id}] {html.escape(title, quote=False)}\n"
            f"{html.escape(snippet, quote=False)}"
        )
        snapshots.append({
            "reference_id": reference_id,
            "title": title,
            "url": url,
            "snippet": snippet,
        })
    sections.append("</public_sources>")
    return "\n".join(sections), snapshots


def _runtime_selection(db: Session, session_id: str) -> RuntimeSelection:
    preference = repo.get_model_preference(db, session_id)
    failover = {"inherit": None, "on": True, "off": False}[
        preference.failover_override or "inherit"
    ]
    return RuntimeSelection(
        profile_mode=preference.profile_mode or "auto",
        preferred_profile_id=preference.preferred_profile_id,
        model_id=preference.model_id,
        reasoning_effort=preference.reasoning_effort or "auto",
        failover_enabled=failover,
    )


def _bundle_from_record(record: dict[str, Any]) -> ResourceBundle:
    artifacts = [
        ResourceArtifact(
            artifact_id=str(item["artifact_id"]),
            type=ArtifactType(str(item["type"])),
            title=str(item["title"]),
            status=ArtifactStatus(str(item["status"])),
            body=str(item.get("body") or ""),
            type_specific_data=dict(item.get("type_specific_data") or {}),
            quality_score=float(item.get("quality_score") or 0),
            quality_issues=list(item.get("quality_issues") or []),
            error_code=item.get("error_code"),
            retryable=bool(item.get("retryable")),
            safety=(
                SafetyMetadata.model_validate(item["safety"])
                if item.get("safety") is not None
                else None
            ),
        )
        for item in record.get("artifacts", [])
    ]
    return ResourceBundle(
        bundle_id=str(record["bundle_id"]),
        protocol_version=str(record["protocol_version"]),
        topic=str(record["topic"]),
        profile_version=int(record["profile_version"]),
        learning_state_version=str(record["learning_state_version"]),
        mode=str(record["mode"]),
        status=str(record["status"]),
        requested_types=[ArtifactType(item) for item in record.get("requested_types", [])],
        artifacts=artifacts,
        aggregate_quality=float(record.get("aggregate_quality") or 0),
        created_at=str(record["created_at"]),
        knowledge_sources=list(record.get("knowledge_sources") or []),
        public_sources=list(record.get("public_sources") or []),
    )


class _RuntimeGateway:
    def __init__(self, db: Session, session_id: str) -> None:
        self._db = db
        self._session_id = session_id

    async def complete(self, messages, temperature=0.3) -> Any:
        return await model_runtime_router.complete(
            _runtime_selection(self._db, self._session_id),
            messages,
            temperature,
        )


class ResourceBundleService:
    def __init__(
        self,
        *,
        pipeline: Any | None = None,
        learning_context_provider: Callable[[Session, str], str] = learning.learning_context,
        knowledge_retriever: Callable[[Session, str, str], KnowledgeContext] = retrieve_knowledge_context,
        web_search: Callable[[str], Awaitable[list[Any]]] = search_web_optional,
        safety_service: Any = content_safety_service,
    ) -> None:
        self._pipeline = pipeline
        self._learning_context_provider = learning_context_provider
        self._knowledge_retriever = knowledge_retriever
        self._web_search = web_search
        self._safety_service = safety_service

    async def generate(
        self,
        db: Session,
        session_id: str,
        message: str,
        selection: ResourceSelection,
        *,
        generation_id: str,
        is_disconnected: DisconnectCheck | None = None,
        on_event: EventSink | None = None,
    ) -> ResourceBundle:
        session = repo.get_session(db, session_id)
        if session is None or session.state != repo.SessionState.PROFILED.value:
            raise DomainStateError("会话尚未完成诊断，请先继续诊断。", "RESOURCE_NOT_READY")
        if not session.profile_text:
            raise DomainStateError("会话画像缺失，请重新诊断。", "PROFILE_MISSING")

        try:
            subject_category = "other"
            try:
                subject_category = parse_profile(session.profile_text).subject or "other"
            except Exception:
                logger.info("Profile subject unavailable for bundle generation")
            request_safety = await self._safety_service.gate_request(
                message,
                intent=message,
                subject_category=subject_category,
            )
            safe_message = request_safety.safe_text
            repo.begin_generation(db, session)
            learning_context = self._learning_context_provider(db, session_id)
            query = build_knowledge_retrieval_query(db, session_id, safe_message)
            knowledge_context = self._knowledge_retriever(db, session_id, query)
            knowledge_sources = knowledge_source_payload(knowledge_context)
            public_results = await self._web_search(safe_message)
            public_context, public_sources = _public_source_context(
                public_results,
                first_reference=len(knowledge_sources) + 1,
            )
            prompt_context = "\n\n".join(
                item for item in (knowledge_context.prompt, public_context) if item
            )
            source_allowlist = [
                str(source["reference_id"])
                for source in [*knowledge_sources, *public_sources]
            ]
            bundle_id = f"bundle-{generation_id or uuid.uuid4().hex}"
            pipeline = self._pipeline or BundlePipeline(
                _RuntimeGateway(db, session_id),
                safety_service=self._safety_service,
            )
            get_or_create_cancellation(bundle_id)
            disconnect_task = None
            if is_disconnected is not None:
                async def _watch_disconnect() -> None:
                    while True:
                        if await is_disconnected():
                            cancel_bundle(bundle_id)
                            return
                        await asyncio.sleep(0.05)

                disconnect_task = asyncio.create_task(_watch_disconnect())
            try:
                result = await pipeline.run(
                    bundle_id=bundle_id,
                    mode=selection.mode.value,
                    single_type=selection.resource_type,
                    profile_text=session.profile_text,
                    learning_context=learning_context,
                    knowledge_context=prompt_context,
                    user_request=safe_message,
                    source_allowlist=source_allowlist,
                    subject_category_hint=subject_category,
                    profile_version=session.profile_version,
                    learning_state_version=str(session.learning_state_version),
                    knowledge_sources=knowledge_sources,
                    public_sources=public_sources,
                    on_event=on_event,
                )
            finally:
                if disconnect_task is not None:
                    disconnect_task.cancel()
                    try:
                        await disconnect_task
                    except asyncio.CancelledError:
                        pass
                cleanup_cancellation(bundle_id)
            bundle = result.bundle.model_copy(update={
                "knowledge_sources": knowledge_sources,
                "public_sources": public_sources,
            })
            save_bundle(db, session_id, bundle)
            repo.finish_bundle_generation(db, session)
            return bundle
        except AppError as exc:
            db.rollback()
            repo.fail_to_stable_state(db, session, exc.code)
            raise
        except Exception as exc:
            logger.exception("Resource bundle generation failed with %s", type(exc).__name__)
            db.rollback()
            repo.fail_to_stable_state(db, session, "BUNDLE_FAILED")
            raise UnexpectedBackendError() from exc

    async def retry_artifact(
        self,
        db: Session,
        session_id: str,
        bundle_id: str,
        artifact_type: ArtifactType,
        *,
        generation_id: str,
    ) -> ResourceBundle:
        record = get_bundle_for_session(db, session_id, bundle_id)
        if record is None:
            raise ResourceNotFoundError(
                "RESOURCE_BUNDLE_NOT_FOUND",
                "资源包不存在或不属于当前会话。",
            )
        original = _bundle_from_record(record)
        target = next(
            (artifact for artifact in original.artifacts if artifact.type == artifact_type),
            None,
        )
        if target is None:
            raise ResourceNotFoundError(
                "RESOURCE_ARTIFACT_NOT_FOUND",
                "资源产物不存在。",
            )
        if target.status == ArtifactStatus.SUCCEEDED or not target.retryable:
            raise DomainStateError(
                "当前资源产物不可重试。",
                "RESOURCE_ARTIFACT_NOT_RETRYABLE",
            )

        temporary = await self.generate(
            db,
            session_id,
            f"重新生成{original.topic}的{artifact_type.value}",
            ResourceSelection.single(artifact_type),
            generation_id=generation_id,
        )
        generated = temporary.artifacts[0]
        replacement = generated.model_copy(update={"artifact_id": target.artifact_id})
        artifacts = [
            replacement if artifact.type == artifact_type else artifact
            for artifact in original.artifacts
        ]
        updated = aggregate_bundle(
            original.bundle_id,
            original.topic,
            original.profile_version,
            original.learning_state_version,
            original.mode.value,
            original.requested_types,
            artifacts,
            False,
            original.knowledge_sources,
            original.public_sources,
        ).model_copy(update={"created_at": original.created_at})
        delete_bundle(db, temporary.bundle_id)
        save_bundle(db, session_id, updated)
        repo.commit(db)
        return updated


resource_bundle_service = ResourceBundleService()
