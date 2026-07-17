from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.errors import AppError, ClientCancelledError, ContentCitationNotAllowedError, ContentSafetyInputBlockedError, DomainStateError, ProtocolValidationError, UnexpectedBackendError
from backend.knowledge.context import (
    KnowledgeContext,
    citation_payload,
    retrieve_knowledge_context,
    sanitize_citations,
    KnowledgeRetrievalScope,
)
from backend.protocols import parse_profile, parse_resource, serialize_profile, serialize_resource
from backend.protocols.v2.models import ArtifactType, ResourceBundle
from backend.services import db as repo
from backend.services import learning
from backend.services.model_runtime import RoutedStreamEvent, RuntimeSelection, model_runtime_router
from backend.services.content_safety.models import SafetyAction, SafetyStage
from backend.services.content_safety.citations import validate_citations
from backend.services.content_safety.service import content_safety_service
from backend.services.profile_agent import build_profile_messages, generate_diagnosis_decision, generate_profile
from backend.services.resource_agent import build_resource_messages, generate_resources
from backend.services.resource_quality import validate_resource_quality
import json
from backend.services.resource_bundle.cancel import cancel_bundle as _bundle_cancel
from backend.services.resource_bundle.service import (
    ResourceSelection,
    knowledge_source_payload,
    resource_bundle_service,
)
from backend.services.web_search import search_web_optional

_REDIAGNOSE_HINTS = ("重新诊断", "重新生成画像", "换画像", "重新分析我")
_FIRST_FOLLOW_UP = "为了更准确地帮你制定学习计划，你目前最容易在哪一步出错？"
_generation_cancel_events: dict[str, asyncio.Event] = {}
_generation_sessions: dict[str, str] = {}
_workflow_locks: dict[str, asyncio.Lock] = {}


def _workflow_lock(session_id: str) -> asyncio.Lock:
    """Serialize stateful work for one session within this API process."""
    lock = _workflow_locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _workflow_locks[session_id] = lock
    return lock


async def close_runtime() -> None:
    _generation_cancel_events.clear()
    _generation_sessions.clear()
    _workflow_locks.clear()
    repo.clear_runtime_state()
    await model_runtime_router.close()


def _runtime_selection(db: Session, session_id: str) -> RuntimeSelection:
    preference = repo.get_model_preference(db, session_id)
    failover = {
        "inherit": None,
        "on": True,
        "off": False,
    }[preference.failover_override or "inherit"]
    return RuntimeSelection(
        profile_mode=preference.profile_mode or "auto",
        preferred_profile_id=preference.preferred_profile_id,
        model_id=preference.model_id,
        reasoning_effort=preference.reasoning_effort or "auto",
        failover_enabled=failover,
    )


def _selected_complete(selection: RuntimeSelection):
    async def complete(messages: list[dict[str, str]], temperature: float = 0.2) -> str:
        result = await model_runtime_router.complete(selection, messages, temperature)
        complete.last_profile_id = result.profile_id
        return result.text
    complete.last_profile_id = None
    return complete


def _session_subject(session) -> str:
    if session is None or not session.profile_text:
        return "other"
    try:
        return parse_profile(session.profile_text).subject or "other"
    except Exception:
        return "other"


def _context_decision(safety_service: Any | None, text: str):
    if safety_service is None:
        return None
    filter_context = getattr(
        safety_service,
        "filter_context",
        content_safety_service.filter_context,
    )
    return filter_context(text)


def _safe_context_text(safety_service: Any | None, text: str) -> str:
    decision = _context_decision(safety_service, text)
    return text if decision is None else decision.safe_text


def _safe_knowledge_context(
    safety_service: Any | None,
    context: KnowledgeContext,
) -> KnowledgeContext:
    safe_prompt = _safe_context_text(safety_service, context.prompt)
    if not safe_prompt:
        return KnowledgeContext.empty()
    return KnowledgeContext(
        prompt=safe_prompt,
        citations=context.citations,
        retrieval_mode=context.retrieval_mode,
    )


def _safe_public_sources(
    safety_service: Any | None,
    sources: list[Any],
) -> list[dict[str, object]]:
    if safety_service is None:
        return [item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in sources]
    safe_sources: list[dict[str, object]] = []
    for item in sources:
        source = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        title = _context_decision(safety_service, str(source.get("title") or ""))
        snippet = _context_decision(safety_service, str(source.get("snippet") or ""))
        url_text = str(source.get("url") or "")
        url = _context_decision(safety_service, url_text)
        if (
            title is None
            or snippet is None
            or url is None
            or not title.safe_text
            or (source.get("snippet") and not snippet.safe_text)
            or url.metadata.decision != SafetyAction.ALLOW
            or url.safe_text != url_text
        ):
            continue
        safe_sources.append({
            **source,
            "title": title.safe_text,
            "snippet": snippet.safe_text,
            "url": url.safe_text,
        })
    return safe_sources


def _number_public_sources(
    sources: list[dict[str, object]],
    *,
    first_reference: int,
) -> list[dict[str, object]]:
    return [
        {
            **source,
            "reference_id": f"资料{first_reference + index}",
        }
        for index, source in enumerate(sources)
    ]


async def _gate_message(
    safety_service: Any | None,
    message: str,
    session,
    generation_profile_id: str | None = None,
    request_id: str = "",
):
    if safety_service is None:
        return message, None
    result = await safety_service.gate_request(
        message,
        intent=message,
        subject_category=_session_subject(session),
        generation_profile_id=generation_profile_id,
        request_id=request_id,
        session_tag=session.session_id,
    )
    return result.safe_text, result


async def _review_output(
    safety_service: Any | None,
    text: str,
    *,
    intent: str,
    session,
    generation_profile_id: str | None = None,
    artifact_type: str | None = None,
    request_id: str = "",
):
    if safety_service is None:
        return text, None
    result = await safety_service.review_text(
        text,
        stage=SafetyStage.ARTIFACT,
        intent=intent,
        subject_category=_session_subject(session),
        artifact_type=artifact_type,
        generation_profile_id=generation_profile_id,
        request_id=request_id,
        session_tag=session.session_id,
    )
    return result.safe_text, result.metadata


class _RuntimeStreamAdapter:
    async def stream(self, messages, temperature=0.2, *, selection=None):
        async for event in model_runtime_router.stream(selection or RuntimeSelection(), messages, temperature):
            yield event


_gateway = _RuntimeStreamAdapter()


async def _stream_items(gateway, selection, messages, temperature):
    if isinstance(gateway, _RuntimeStreamAdapter):
        async for item in gateway.stream(messages, temperature, selection=selection):
            yield item
        return
    async for item in gateway.stream(messages, temperature):
        yield item


def _stream_meta_payload(event: RoutedStreamEvent, request_id: str) -> dict[str, object]:
    return {
        "event": "meta",
        "request_id": request_id,
        "profile_id": event.profile_id,
        "model_id": event.model_id,
        "requested_reasoning_effort": event.requested_reasoning_effort,
        "effective_reasoning_effort": event.effective_reasoning_effort,
        "failover_used": event.failover_used,
    }


def _stream_interrupted_payload(event: RoutedStreamEvent, request_id: str) -> dict[str, object]:
    return {
        "event": "interrupted",
        "request_id": request_id,
        "code": event.code or "MODEL_STREAM_INTERRUPTED",
        "profile_id": event.profile_id,
        "model_id": event.model_id,
        "can_continue_with_backup": event.can_continue_with_backup,
    }


def cancel_generation(generation_id: str, session_id: str) -> bool:
    if _generation_sessions.get(generation_id) != session_id:
        return False
    event = _generation_cancel_events.get(generation_id)
    if event is None:
        return False
    event.set()
    _bundle_cancel(f"bundle-{generation_id}")
    return True


class ChatResult:
    def __init__(
        self,
        reply: str,
        phase: str,
        state: str,
        profile_version: int = 0,
        cached: bool = False,
        sources: list[dict[str, str]] | None = None,
        knowledge_sources: list[dict[str, object]] | None = None,
        bundle: ResourceBundle | None = None,
        evidence_status: str = "unavailable",
        knowledge_scope: dict[str, object] | None = None,
        recovery_actions: list[str] | None = None,
    ) -> None:
        self.reply = reply
        self.phase = phase
        self.state = state
        self.profile_version = profile_version
        self.cached = cached
        self.sources = sources or []
        self.knowledge_sources = knowledge_sources or []
        self.bundle = bundle
        self.evidence_status = evidence_status
        self.knowledge_scope = knowledge_scope
        self.recovery_actions = recovery_actions or []


def _is_rediagnose(message: str) -> bool:
    return any(hint in message for hint in _REDIAGNOSE_HINTS)


def _needs_forced_follow_up(session, decision) -> bool:
    return session.diagnosis_turns == 0 and decision.status == "COMPLETE"


def _history_texts(db: Session, session_id: str) -> list[str]:
    settings = get_settings()
    return repo.history_texts(
        db,
        session_id,
        maximum_messages=settings.diagnosis_history_message_limit,
        maximum_characters=settings.diagnosis_history_max_characters,
    )


def _safe_history_texts(
    db: Session,
    session_id: str,
    safety_service: Any | None,
) -> list[str]:
    safe_history: list[str] = []
    for item in _history_texts(db, session_id):
        safe_item = _safe_context_text(safety_service, item)
        if safe_item:
            safe_history.append(safe_item)
    return safe_history


async def _generate_adaptive_resource(
    db: Session,
    session_id: str,
    profile_text: str,
    message: str,
    sources: list[dict[str, str]],
    knowledge_context: str = "",
    complete=None,
    safety_service: Any | None = None,
) -> str:
    keyword_arguments = {
        "learning_context": _safe_context_text(
            safety_service,
            learning.learning_context(db, session_id),
        ),
    }
    if knowledge_context:
        keyword_arguments["knowledge_context"] = knowledge_context
    return await generate_resources(
        profile_text,
        message,
        sources,
        complete=complete,
        **keyword_arguments,
    )


def _knowledge_retrieval_query(db: Session, session_id: str, message: str) -> str:
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
            repo.ReviewTask.due_at <= datetime.utcnow(),
        )
        .order_by(repo.ReviewTask.due_at, repo.ReviewTask.id)
        .limit(3)
        .all()
    )
    parts = [message]
    parts.extend(point.name for point in weak_points)
    parts.extend(task.knowledge_point.name for task in due_reviews)
    return " ".join(dict.fromkeys(part.strip() for part in parts if part.strip()))


def _knowledge_payload(
    context: KnowledgeContext,
    safety_service: Any | None = None,
) -> list[dict[str, object]]:
    if safety_service is None:
        return [citation_payload(citation) for citation in context.citations]
    return knowledge_source_payload(context, safety_service)


def _retrieve_scoped_knowledge(
    db: Session,
    session_id: str,
    query: str,
    scope: KnowledgeRetrievalScope | None,
) -> KnowledgeContext:
    if scope is None:
        return retrieve_knowledge_context(db, session_id, query)
    return retrieve_knowledge_context(db, session_id, query, scope=scope)


async def _diagnosis_reply(
    db: Session,
    session,
    session_id: str,
    complete,
    *,
    safety_service: Any | None = None,
    intent: str = "学习诊断",
    request_id: str = "",
):
    decision = await generate_diagnosis_decision(
        _safe_history_texts(db, session_id, safety_service),
        session.diagnosis_turns + 1,
        complete=complete,
    )
    decision_text, _ = await _review_output(
        safety_service,
        decision.model_dump_json(),
        intent=intent,
        session=session,
        generation_profile_id=getattr(complete, "last_profile_id", None),
        artifact_type="diagnosis-decision/v1",
        request_id=request_id,
    )
    decision = decision.__class__.model_validate_json(decision_text)
    if _needs_forced_follow_up(session, decision):
        repo.record_diagnosis_snapshot(db, session, decision.model_dump_json(), ["当前水平", "薄弱知识点"], decision.confidence)
        return False, _FIRST_FOLLOW_UP
    if decision.status == "CONTINUE" and session.diagnosis_turns < 4:
        repo.record_diagnosis_snapshot(db, session, decision.model_dump_json(), decision.missing_fields, decision.confidence)
        return False, decision.next_question
    return True, ""


async def handle_message(
    db: Session,
    session_id: str,
    message: str,
    resource_mode: str | None = None,
    resource_type: str | None = None,
    safety_service: Any | None = None,
    knowledge_scope: KnowledgeRetrievalScope | None = None,
) -> ChatResult:
    async with _workflow_lock(session_id):
        return await _handle_message(
            db,
            session_id,
            message,
            resource_mode=resource_mode,
            resource_type=resource_type,
            safety_service=safety_service,
            knowledge_scope=knowledge_scope,
        )


async def _handle_message(
    db: Session,
    session_id: str,
    message: str,
    resource_mode: str | None = None,
    resource_type: str | None = None,
    safety_service: Any | None = None,
    knowledge_scope: KnowledgeRetrievalScope | None = None,
) -> ChatResult:
    session = repo.get_or_create_session(db, session_id)
    request_id = uuid.uuid4().hex
    selection = _runtime_selection(db, session_id)
    message, request_safety = await _gate_message(
        safety_service,
        message,
        session,
        model_runtime_router.generation_candidate_id(selection),
        request_id,
    )
    repo.append_message(db, session_id, "user", message)
    complete = _selected_complete(selection)
    if _is_rediagnose(message):
        repo.restart_diagnosis(db, session)

    try:
        if session.state in {repo.SessionState.NEW.value, repo.SessionState.DIAGNOSING.value}:
            if session.state == repo.SessionState.NEW.value:
                repo.set_state(db, session, repo.SessionState.DIAGNOSING)
            diagnosis_complete, reply = await _diagnosis_reply(
                db,
                session,
                session_id,
                complete,
                safety_service=safety_service,
                intent=message,
                request_id=request_id,
            )
            if not diagnosis_complete:
                repo.append_message(db, session_id, "assistant", reply)
                return ChatResult(reply, "diagnosis", session.state, session.profile_version)
            repo.set_state(db, session, repo.SessionState.PROFILE_READY)
            profile_text = await generate_profile(
                _safe_history_texts(db, session_id, safety_service),
                session.profile_version + 1,
                complete=complete,
            )
            profile_text, _ = await _review_output(
                safety_service,
                profile_text,
                intent=message,
                session=session,
                generation_profile_id=getattr(complete, "last_profile_id", None),
                request_id=request_id,
            )
            version = repo.save_profile(db, session, profile_text)
            repo.append_message(db, session_id, "assistant", profile_text)
            return ChatResult(profile_text, "profile", session.state, version)

        if session.state == repo.SessionState.PROFILED.value:
            if not session.profile_text:
                raise DomainStateError("会话画像缺失，请重新诊断。", "PROFILE_MISSING")
            safe_profile_text = _safe_context_text(
                safety_service,
                session.profile_text,
            )
            if not safe_profile_text:
                raise ContentSafetyInputBlockedError()
            if resource_mode:
                selection = (
                    ResourceSelection.single(ArtifactType(resource_type))
                    if resource_mode == "single" and resource_type is not None
                    else ResourceSelection.bundle()
                )
                bundle = await resource_bundle_service.generate(
                    db,
                    session_id,
                    message,
                    selection,
                    generation_id=uuid.uuid4().hex,
                    request_safety=request_safety,
                    knowledge_scope=knowledge_scope,
                )
                bundle_text = json.dumps(bundle.model_dump(mode="json"), ensure_ascii=False)
                repo.append_message(db, session_id, "assistant", bundle_text)
                stable_session = repo.get_session(db, session_id)
                return ChatResult(
                    "",
                    "resource",
                    stable_session.state if stable_session is not None else repo.SessionState.PROFILED.value,
                    session.profile_version,
                    bundle=bundle,
                    evidence_status=bundle.evidence_status,
                    knowledge_scope=bundle.knowledge_scope,
                    recovery_actions=bundle.recovery_actions,
                )
            knowledge_context = _safe_knowledge_context(
                safety_service,
                _retrieve_scoped_knowledge(
                    db,
                    session_id,
                    _knowledge_retrieval_query(db, session_id, message),
                    knowledge_scope,
                ),
            )
            knowledge_sources = _knowledge_payload(knowledge_context, safety_service)
            cached = None
            if not knowledge_sources:
                cached = repo.find_cached_resource(
                    db,
                    session,
                    message,
                    get_settings().resource_cache_ttl_seconds,
                )
            if cached is not None:
                repo.append_message(db, session_id, "assistant", cached.content)
                return ChatResult(
                    cached.content,
                    "resource",
                    session.state,
                    session.profile_version,
                    cached=True,
                    sources=repo.resource_sources(cached),
                    knowledge_sources=repo.resource_knowledge_sources(cached),
                )
            repo.begin_generation(db, session)
            sources = await search_web_optional(message)
            source_payload = _safe_public_sources(safety_service, sources)
            model_source_payload = _number_public_sources(
                source_payload,
                first_reference=len(knowledge_sources) + 1,
            )
            public_reference_ids = {
                str(item["reference_id"])
                for item in model_source_payload
            }
            resource_text = await _generate_adaptive_resource(
                db,
                session_id,
                safe_profile_text,
                message,
                model_source_payload,
                knowledge_context.prompt,
                complete,
                safety_service,
            )
            citation_decision = validate_citations(
                resource_text,
                allowed={
                    item.reference_id for item in knowledge_context.citations
                } | public_reference_ids,
            )
            if not citation_decision.allowed:
                raise ContentCitationNotAllowedError()
            resource_text, _used, citation_issues = sanitize_citations(
                resource_text,
                knowledge_context.citations,
                additional_allowed=public_reference_ids,
            )
            resource = parse_resource(resource_text)
            validate_resource_quality(resource)
            resource_text, safety_metadata = await _review_output(
                safety_service,
                resource_text,
                intent=message,
                session=session,
                generation_profile_id=getattr(complete, "last_profile_id", None),
                artifact_type="learning-resource/v1",
                request_id=request_id,
            )
            resource = parse_resource(resource_text)
            validate_resource_quality(resource)
            repo.complete_generation(
                db,
                session,
                resource.topic,
                message,
                resource_text,
                session.profile_version,
                source_payload,
                knowledge_sources=knowledge_sources,
                extra_quality_issues=citation_issues,
                safety_metadata=safety_metadata,
            )
            repo.append_message(db, session_id, "assistant", resource_text)
            return ChatResult(
                resource_text,
                "resource",
                session.state,
                session.profile_version,
                sources=source_payload,
                knowledge_sources=knowledge_sources,
                evidence_status=knowledge_context.evidence_status,
                knowledge_scope=knowledge_context.scope,
                recovery_actions=list(knowledge_context.recovery_actions),
            )

        if session.state == repo.SessionState.GENERATING.value:
            raise DomainStateError("当前会话正在生成学习资源，请等待完成。", "GENERATION_IN_PROGRESS")
        raise DomainStateError("会话当前不可处理，请重新诊断。", "SESSION_NOT_READY")
    except AppError as exc:
        repo.fail_to_stable_state(db, session, exc.code)
        raise


async def stream_message(db: Session, session_id: str, message: str, is_disconnected,
                         resource_mode: str | None = None,
                         resource_type: str | None = None,
                         safety_service: Any | None = None,
                         knowledge_scope: KnowledgeRetrievalScope | None = None) -> AsyncIterator[dict[str, object]]:
    async with _workflow_lock(session_id):
        async for event in _stream_message(db, session_id, message, is_disconnected,
                                        resource_mode=resource_mode,
                                        resource_type=resource_type,
                                        safety_service=safety_service,
                                        knowledge_scope=knowledge_scope):
            yield event


async def _stream_message(db: Session, session_id: str, message: str, is_disconnected,
                          resource_mode: str | None = None,
                          resource_type: str | None = None,
                          safety_service: Any | None = None,
                          knowledge_scope: KnowledgeRetrievalScope | None = None) -> AsyncIterator[dict[str, object]]:
    request_id = uuid.uuid4().hex
    generation_id = uuid.uuid4().hex
    cancel_event = asyncio.Event()
    _generation_cancel_events[generation_id] = cancel_event
    _generation_sessions[generation_id] = session_id
    session = None
    request_safety = None

    try:
        session = repo.get_or_create_session(db, session_id)
        selection = _runtime_selection(db, session_id)
        message, request_safety = await _gate_message(
            safety_service,
            message,
            session,
            model_runtime_router.generation_candidate_id(selection),
            request_id,
        )
        repo.append_message(db, session_id, "user", message)
        complete = _selected_complete(selection)
        if _is_rediagnose(message):
            repo.restart_diagnosis(db, session)
        if session.state in {repo.SessionState.NEW.value, repo.SessionState.DIAGNOSING.value}:
            if session.state == repo.SessionState.NEW.value:
                repo.set_state(db, session, repo.SessionState.DIAGNOSING)
            yield {"event": "phase", "request_id": request_id, "generation_id": generation_id, "phase": "diagnosis"}
            diagnosis_complete, reply = await _diagnosis_reply(
                db,
                session,
                session_id,
                complete,
                safety_service=safety_service,
                intent=message,
                request_id=request_id,
            )
            if not diagnosis_complete:
                repo.append_message(db, session_id, "assistant", reply)
                yield {"event": "delta", "request_id": request_id, "content": reply, "provisional": False}
                yield {"event": "done", "request_id": request_id, "status": "completed", "state": session.state}
                return
            repo.set_state(db, session, repo.SessionState.PROFILE_READY)
            yield {"event": "phase", "request_id": request_id, "generation_id": generation_id, "phase": "profile"}
            raw = ""
            last_profile_id = None
            selection = _runtime_selection(db, session_id)
            async for item in _stream_items(
                _gateway,
                selection,
                build_profile_messages(
                    _safe_history_texts(db, session_id, safety_service),
                    session.profile_version + 1,
                ),
                0.2,
            ):
                if cancel_event.is_set() or await is_disconnected():
                    raise ClientCancelledError()
                if isinstance(item, RoutedStreamEvent):
                    if item.event == "meta":
                        last_profile_id = item.profile_id
                        yield _stream_meta_payload(item, request_id)
                        continue
                    if item.event == "interrupted":
                        repo.fail_to_stable_state(db, session, item.code or "MODEL_STREAM_INTERRUPTED")
                        yield _stream_interrupted_payload(item, request_id)
                        yield {"event": "done", "request_id": request_id, "status": "interrupted", "state": session.state}
                        return
                    delta = item.content or ""
                else:
                    delta = item
                raw += delta
            try:
                canonical = serialize_profile(parse_profile(raw))
                repaired = False
                error_code = None
            except ProtocolValidationError as exc:
                canonical = await generate_profile(
                    _safe_history_texts(db, session_id, safety_service),
                    session.profile_version + 1,
                    complete=complete,
                )
                repaired = True
                error_code = exc.code
                last_profile_id = getattr(complete, "last_profile_id", last_profile_id)
            canonical, _ = await _review_output(
                safety_service,
                canonical,
                intent=message,
                session=session,
                generation_profile_id=last_profile_id,
                request_id=request_id,
            )
            yield {"event": "validation", "request_id": request_id, "valid": True, "repair_attempted": repaired, "error_code": error_code}
            if canonical.strip() != raw.strip():
                yield {"event": "replace", "request_id": request_id, "content": canonical}
            yield {"event": "delta", "request_id": request_id, "content": canonical, "provisional": False}
            version = repo.save_profile(db, session, canonical)
            repo.append_message(db, session_id, "assistant", canonical)
            yield {"event": "persisted", "request_id": request_id, "profile_version": version}
            yield {"event": "done", "request_id": request_id, "status": "completed", "state": session.state}
            return

        if session.state != repo.SessionState.PROFILED.value or not session.profile_text:
            raise DomainStateError("会话尚未完成诊断，请先继续诊断。", "RESOURCE_NOT_READY")
        safe_profile_text = _safe_context_text(safety_service, session.profile_text)
        if not safe_profile_text:
            raise ContentSafetyInputBlockedError()

        if resource_mode:
            selection = (
                ResourceSelection.single(ArtifactType(resource_type))
                if resource_mode == "single" and resource_type is not None
                else ResourceSelection.bundle()
            )
            yield {
                "event": "phase",
                "request_id": request_id,
                "generation_id": generation_id,
                "phase": "resource",
            }
            event_queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

            async def on_bundle_event(event: dict[str, object]) -> None:
                await event_queue.put({"request_id": request_id, **event})

            service_task = asyncio.create_task(resource_bundle_service.generate(
                db,
                session_id,
                message,
                selection,
                generation_id=generation_id,
                is_disconnected=is_disconnected,
                on_event=on_bundle_event,
                request_safety=request_safety,
                knowledge_scope=knowledge_scope,
            ))
            while True:
                queue_task = asyncio.create_task(event_queue.get())
                done, _ = await asyncio.wait(
                    {service_task, queue_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if queue_task in done:
                    yield queue_task.result()
                else:
                    queue_task.cancel()
                    try:
                        await queue_task
                    except asyncio.CancelledError:
                        pass
                if service_task in done:
                    while not event_queue.empty():
                        yield event_queue.get_nowait()
                    break

            bundle = await service_task
            bundle_dict = bundle.model_dump(mode="json")
            repo.append_message(
                db,
                session_id,
                "assistant",
                json.dumps(bundle_dict, ensure_ascii=False),
            )
            yield {"event": "persisted", "request_id": request_id, "bundle_id": bundle.bundle_id}
            stable_session = repo.get_session(db, session_id)
            yield {
                "event": "done",
                "request_id": request_id,
                "status": "completed",
                "state": stable_session.state if stable_session is not None else repo.SessionState.PROFILED.value,
            }
            return

        knowledge_context = _safe_knowledge_context(
            safety_service,
            _retrieve_scoped_knowledge(
                db,
                session_id,
                _knowledge_retrieval_query(db, session_id, message),
                knowledge_scope,
            ),
        )
        knowledge_sources = _knowledge_payload(knowledge_context, safety_service)
        cached = None
        if not knowledge_sources:
            cached = repo.find_cached_resource(
                db,
                session,
                message,
                get_settings().resource_cache_ttl_seconds,
            )
        if cached is not None:
            yield {"event": "phase", "request_id": request_id, "generation_id": generation_id, "phase": "resource"}
            yield {"event": "cache", "request_id": request_id, "hit": True, "resource_id": cached.id}
            yield {"event": "sources", "request_id": request_id, "sources": repo.resource_sources(cached), "cached": True}
            yield {"event": "knowledge_sources", "request_id": request_id, "sources": repo.resource_knowledge_sources(cached), "cached": True}
            repo.append_message(db, session_id, "assistant", cached.content)
            yield {"event": "delta", "request_id": request_id, "content": cached.content, "provisional": False}
            yield {"event": "persisted", "request_id": request_id, "resource_id": cached.id, "cached": True}
            yield {"event": "done", "request_id": request_id, "status": "completed", "state": session.state, "cached": True}
            return
        repo.begin_generation(db, session)
        yield {"event": "phase", "request_id": request_id, "generation_id": generation_id, "phase": "resource"}

        raw = ""
        sources = await search_web_optional(message)
        source_payload = _safe_public_sources(safety_service, sources)
        model_source_payload = _number_public_sources(
            source_payload,
            first_reference=len(knowledge_sources) + 1,
        )
        public_reference_ids = {
            str(item["reference_id"])
            for item in model_source_payload
        }
        yield {"event": "sources", "request_id": request_id, "sources": source_payload, "cached": False}
        yield {"event": "knowledge_sources", "request_id": request_id, "sources": knowledge_sources, "cached": False}
        yield {
            "event": "knowledge_evidence",
            "request_id": request_id,
            "status": knowledge_context.evidence_status,
            "scope": knowledge_context.scope,
            "recovery_actions": list(knowledge_context.recovery_actions),
        }
        learning_context = _safe_context_text(
            safety_service,
            learning.learning_context(db, session_id),
        )
        selection = _runtime_selection(db, session_id)
        last_profile_id = None
        async for item in _stream_items(
            _gateway,
            selection,
            build_resource_messages(
                safe_profile_text,
                message,
                model_source_payload,
                learning_context,
                knowledge_context.prompt,
            ),
            0.4,
        ):
            if cancel_event.is_set() or await is_disconnected():
                raise ClientCancelledError()
            if isinstance(item, RoutedStreamEvent):
                if item.event == "meta":
                    last_profile_id = item.profile_id
                    yield _stream_meta_payload(item, request_id)
                    continue
                if item.event == "interrupted":
                    repo.fail_to_stable_state(db, session, item.code or "MODEL_STREAM_INTERRUPTED")
                    yield _stream_interrupted_payload(item, request_id)
                    yield {"event": "done", "request_id": request_id, "status": "interrupted", "state": session.state}
                    return
                delta = item.content or ""
            else:
                delta = item
            raw += delta
        try:
            resource = parse_resource(raw)
            validate_resource_quality(resource)
            canonical = serialize_resource(resource)
            repaired = False
            error_code = None
        except ProtocolValidationError as exc:
            canonical = await _generate_adaptive_resource(
                db,
                session_id,
                safe_profile_text,
                message,
                model_source_payload,
                knowledge_context.prompt,
                complete,
                safety_service,
            )
            resource = parse_resource(canonical)
            repaired = True
            error_code = exc.code
            last_profile_id = getattr(complete, "last_profile_id", last_profile_id)
        citation_decision = validate_citations(
            canonical,
            allowed={
                item.reference_id for item in knowledge_context.citations
            } | public_reference_ids,
        )
        if not citation_decision.allowed:
            raise ContentCitationNotAllowedError()
        canonical, _used, citation_issues = sanitize_citations(
            canonical,
            knowledge_context.citations,
            additional_allowed=public_reference_ids,
        )
        resource = parse_resource(canonical)
        validate_resource_quality(resource)
        canonical, safety_metadata = await _review_output(
            safety_service,
            canonical,
            intent=message,
            session=session,
            generation_profile_id=last_profile_id,
            artifact_type="learning-resource/v1",
            request_id=request_id,
        )
        resource = parse_resource(canonical)
        validate_resource_quality(resource)
        yield {"event": "validation", "request_id": request_id, "valid": True, "repair_attempted": repaired, "error_code": error_code}
        if canonical.strip() != raw.strip():
            yield {"event": "replace", "request_id": request_id, "content": canonical}
        yield {"event": "delta", "request_id": request_id, "content": canonical, "provisional": False}
        stored = repo.complete_generation(
            db,
            session,
            resource.topic,
            message,
            canonical,
            session.profile_version,
            source_payload,
            knowledge_sources=knowledge_sources,
            extra_quality_issues=citation_issues,
            safety_metadata=safety_metadata,
        )
        repo.append_message(db, session_id, "assistant", canonical)
        yield {"event": "persisted", "request_id": request_id, "resource_id": stored.id}
        yield {"event": "done", "request_id": request_id, "status": "completed", "state": session.state}
    except ClientCancelledError as exc:
        if session is not None:
            repo.fail_to_stable_state(db, session, exc.code)
        yield {"event": "error", "request_id": request_id, "code": exc.code, "message": exc.public_message, "retryable": False}
        yield {"event": "done", "request_id": request_id, "status": "cancelled", "state": session.state if session is not None else "UNKNOWN"}
    except AppError as exc:
        if session is not None:
            repo.fail_to_stable_state(db, session, exc.code)
        yield {"event": "error", "request_id": request_id, "code": exc.code, "message": exc.public_message, "retryable": exc.retryable}
        yield {"event": "done", "request_id": request_id, "status": "failed", "state": session.state if session is not None else "UNKNOWN"}
    except Exception:
        logging.getLogger("backend").exception("unexpected_sse_error request_id=%s", request_id)
        error = UnexpectedBackendError()
        if session is not None:
            repo.fail_to_stable_state(db, session, error.code)
        yield {"event": "error", "request_id": request_id, "code": error.code, "message": error.public_message, "retryable": error.retryable}
        yield {"event": "done", "request_id": request_id, "status": "failed", "state": session.state if session is not None else "UNKNOWN"}
    finally:
        _generation_cancel_events.pop(generation_id, None)
        _generation_sessions.pop(generation_id, None)
