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
    ContentSafetyInputBlockedError,
    DomainStateError,
    ResourceNotFoundError,
    UnexpectedBackendError,
)
from backend.knowledge.context import (
    KnowledgeContext,
    KnowledgeRetrievalScope,
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
from backend.services.content_safety.models import SafetyAction, SafetyMetadata
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


def _filter_context(safety_service: Any, text: str):
    filter_context = getattr(
        safety_service,
        "filter_context",
        content_safety_service.filter_context,
    )
    return filter_context(text)


def knowledge_source_payload(
    context: KnowledgeContext,
    safety_service: Any = content_safety_service,
) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for citation in context.citations:
        payload = citation_payload(citation)
        payload["document_name"] = _filter_context(
            safety_service,
            str(payload["document_name"]),
        ).safe_text
        payload["locator_label"] = _filter_context(
            safety_service,
            str(payload["locator_label"]),
        ).safe_text
        locator = dict(payload.get("locator") or {})
        if "sheet_name" in locator:
            locator["sheet_name"] = _filter_context(
                safety_service,
                str(locator["sheet_name"]),
            ).safe_text
        payload["locator"] = locator
        payloads.append(payload)
    return payloads


def _public_source_context(
    sources: list[Any],
    *,
    first_reference: int,
    safety_service: Any = content_safety_service,
) -> tuple[str, list[dict[str, object]]]:
    if not sources:
        return "", []
    sections = ['<public_sources untrusted="true">']
    snapshots: list[dict[str, object]] = []
    for source in sources[:8]:
        source_data = source.model_dump() if hasattr(source, "model_dump") else dict(source)
        title_result = _filter_context(
            safety_service,
            str(source_data.get("title") or "公开资料")[:300],
        )
        snippet_result = _filter_context(
            safety_service,
            str(source_data.get("snippet") or "")[:1000],
        )
        url = str(source_data.get("url") or "")[:2048]
        url_result = _filter_context(safety_service, url)
        if (
            not title_result.safe_text
            or (source_data.get("snippet") and not snippet_result.safe_text)
            or url_result.metadata.decision != SafetyAction.ALLOW
            or url_result.safe_text != url
        ):
            continue
        reference_id = f"资料{first_reference + len(snapshots)}"
        title = title_result.safe_text
        snippet = snippet_result.safe_text
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
        evidence_status=str(record.get("evidence_status") or "unavailable"),
        knowledge_scope=(
            dict(record["knowledge_scope"])
            if isinstance(record.get("knowledge_scope"), dict)
            else None
        ),
        recovery_actions=list(record.get("recovery_actions") or []),
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
        request_safety: Any | None = None,
        knowledge_scope: KnowledgeRetrievalScope | None = None,
    ) -> ResourceBundle:
        session = repo.get_session(db, session_id)
        if session is None or session.state != repo.SessionState.PROFILED.value:
            raise DomainStateError("会话尚未完成诊断，请先继续诊断。", "RESOURCE_NOT_READY")
        if not session.profile_text:
            raise DomainStateError("会话画像缺失，请重新诊断。", "PROFILE_MISSING")

        try:
            runtime_selection = _runtime_selection(db, session_id)
            safe_profile_text = _filter_context(
                self._safety_service,
                session.profile_text,
            ).safe_text
            if not safe_profile_text:
                raise ContentSafetyInputBlockedError()
            subject_category = "other"
            try:
                subject_category = parse_profile(safe_profile_text).subject or "other"
            except Exception:
                logger.info("Profile subject unavailable for bundle generation")
            if request_safety is None:
                request_safety = await self._safety_service.gate_request(
                    message,
                    intent=message,
                    subject_category=subject_category,
                    generation_profile_id=(
                        model_runtime_router.generation_candidate_id(runtime_selection)
                    ),
                    request_id=generation_id,
                    session_tag=session_id,
                )
            safe_message = request_safety.safe_text
            repo.begin_generation(db, session)
            learning_context = _filter_context(
                self._safety_service,
                self._learning_context_provider(db, session_id),
            ).safe_text
            query = build_knowledge_retrieval_query(db, session_id, safe_message)
            knowledge_context = (
                self._knowledge_retriever(db, session_id, query, scope=knowledge_scope)
                if knowledge_scope is not None
                else self._knowledge_retriever(db, session_id, query)
            )
            safe_knowledge = _filter_context(
                self._safety_service,
                knowledge_context.prompt,
            )
            if safe_knowledge.safe_text:
                knowledge_context = KnowledgeContext(
                    prompt=safe_knowledge.safe_text,
                    citations=knowledge_context.citations,
                    retrieval_mode=knowledge_context.retrieval_mode,
                    evidence_status=knowledge_context.evidence_status,
                    scope=knowledge_context.scope,
                    recovery_actions=knowledge_context.recovery_actions,
                )
            else:
                knowledge_context = KnowledgeContext.empty(
                    evidence_status=knowledge_context.evidence_status
                    if knowledge_context.evidence_status != "grounded"
                    else "unavailable",
                    scope=knowledge_scope,
                )
            knowledge_sources = knowledge_source_payload(
                knowledge_context,
                self._safety_service,
            )
            public_results = await self._web_search(safe_message)
            public_context, public_sources = _public_source_context(
                public_results,
                first_reference=len(knowledge_sources) + 1,
                safety_service=self._safety_service,
            )
            prompt_context = "\n\n".join(
                item for item in (knowledge_context.prompt, public_context) if item
            )
            if knowledge_context.evidence_status != "grounded":
                prompt_context = "\n\n".join(filter(None, (
                    prompt_context,
                    '<evidence_status trusted="true">教材证据不足；不得伪造教材引用，必须明确说明证据不足。</evidence_status>',
                )))
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
                    profile_text=safe_profile_text,
                    learning_context=learning_context,
                    knowledge_context=prompt_context,
                    user_request=safe_message,
                    source_allowlist=source_allowlist,
                    subject_category_hint=subject_category,
                    profile_version=session.profile_version,
                    learning_state_version=str(session.learning_state_version),
                    knowledge_sources=knowledge_sources,
                    public_sources=public_sources,
                    audit_session_tag=session_id,
                    evidence_status=knowledge_context.evidence_status,
                    knowledge_scope=knowledge_context.scope,
                    recovery_actions=list(knowledge_context.recovery_actions),
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
                "evidence_status": knowledge_context.evidence_status,
                "knowledge_scope": knowledge_context.scope,
                "recovery_actions": list(knowledge_context.recovery_actions),
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
        updated = updated.model_copy(update={
            "evidence_status": original.evidence_status,
            "knowledge_scope": original.knowledge_scope,
            "recovery_actions": original.recovery_actions,
        })
        delete_bundle(db, temporary.bundle_id)
        save_bundle(db, session_id, updated)
        repo.commit(db)
        return updated


resource_bundle_service = ResourceBundleService()
