from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime

from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.errors import AppError, ClientCancelledError, DomainStateError, ProtocolValidationError, UnexpectedBackendError
from backend.knowledge.context import (
    citation_payload,
    retrieve_knowledge_context,
    sanitize_citations,
)
from backend.protocols import parse_profile, parse_resource, serialize_profile, serialize_resource
from backend.services import db as repo
from backend.services import learning
from backend.services.model_runtime import RoutedStreamEvent, RuntimeSelection, model_runtime_router
from backend.services.profile_agent import build_profile_messages, generate_diagnosis_decision, generate_profile
from backend.services.resource_agent import build_resource_messages, generate_resources
from backend.services.resource_quality import validate_resource_quality
from backend.protocols.v2.sse_events import artifact_event, bundle_event, plan_event, progress_event
from backend.services.resource_bundle.pipeline import BundlePipeline
from backend.services.resource_bundle.cancel import get_or_create_cancellation as _bundle_get_cancel, cleanup_cancellation as _bundle_cleanup, cancel_bundle as _bundle_cancel
from backend.protocols.v2.models import ArtifactType
from backend.services.resource_bundle.planner import derive_requested_types
from backend.services.resource_db import save_bundle
import json
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
        return result.text
    return complete


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
    ) -> None:
        self.reply = reply
        self.phase = phase
        self.state = state
        self.profile_version = profile_version
        self.cached = cached
        self.sources = sources or []
        self.knowledge_sources = knowledge_sources or []


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


async def _generate_adaptive_resource(
    db: Session,
    session_id: str,
    profile_text: str,
    message: str,
    sources: list[dict[str, str]],
    knowledge_context: str = "",
    complete=None,
) -> str:
    keyword_arguments = {
        "learning_context": learning.learning_context(db, session_id),
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


def _knowledge_payload(context) -> list[dict[str, object]]:
    return [citation_payload(citation) for citation in context.citations]


async def _diagnosis_reply(db: Session, session, session_id: str, complete):
    decision = await generate_diagnosis_decision(_history_texts(db, session_id), session.diagnosis_turns + 1, complete=complete)
    if _needs_forced_follow_up(session, decision):
        repo.record_diagnosis_snapshot(db, session, decision.model_dump_json(), ["当前水平", "薄弱知识点"], decision.confidence)
        return False, _FIRST_FOLLOW_UP
    if decision.status == "CONTINUE" and session.diagnosis_turns < 4:
        repo.record_diagnosis_snapshot(db, session, decision.model_dump_json(), decision.missing_fields, decision.confidence)
        return False, decision.next_question
    return True, ""


async def handle_message(db: Session, session_id: str, message: str) -> ChatResult:
    async with _workflow_lock(session_id):
        return await _handle_message(db, session_id, message)


async def _handle_message(db: Session, session_id: str, message: str) -> ChatResult:
    repo.append_message(db, session_id, "user", message)
    session = repo.get_or_create_session(db, session_id)
    complete = _selected_complete(_runtime_selection(db, session_id))
    if _is_rediagnose(message):
        repo.restart_diagnosis(db, session)

    try:
        if session.state in {repo.SessionState.NEW.value, repo.SessionState.DIAGNOSING.value}:
            if session.state == repo.SessionState.NEW.value:
                repo.set_state(db, session, repo.SessionState.DIAGNOSING)
            diagnosis_complete, reply = await _diagnosis_reply(db, session, session_id, complete)
            if not diagnosis_complete:
                repo.append_message(db, session_id, "assistant", reply)
                return ChatResult(reply, "diagnosis", session.state, session.profile_version)
            repo.set_state(db, session, repo.SessionState.PROFILE_READY)
            profile_text = await generate_profile(_history_texts(db, session_id), session.profile_version + 1, complete=complete)
            version = repo.save_profile(db, session, profile_text)
            repo.append_message(db, session_id, "assistant", profile_text)
            return ChatResult(profile_text, "profile", session.state, version)

        if session.state == repo.SessionState.PROFILED.value:
            if not session.profile_text:
                raise DomainStateError("会话画像缺失，请重新诊断。", "PROFILE_MISSING")
            knowledge_context = retrieve_knowledge_context(
                db,
                session_id,
                _knowledge_retrieval_query(db, session_id, message),
            )
            knowledge_sources = _knowledge_payload(knowledge_context)
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
            source_payload = [item.model_dump() for item in sources]
            resource_text = await _generate_adaptive_resource(
                db,
                session_id,
                session.profile_text,
                message,
                source_payload,
                knowledge_context.prompt,
                complete,
            )
            resource_text, _used, citation_issues = sanitize_citations(
                resource_text,
                knowledge_context.citations,
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
            )
            repo.append_message(db, session_id, "assistant", resource_text)
            return ChatResult(
                resource_text,
                "resource",
                session.state,
                session.profile_version,
                sources=source_payload,
                knowledge_sources=knowledge_sources,
            )

        if session.state == repo.SessionState.GENERATING.value:
            raise DomainStateError("当前会话正在生成学习资源，请等待完成。", "GENERATION_IN_PROGRESS")
        raise DomainStateError("会话当前不可处理，请重新诊断。", "SESSION_NOT_READY")
    except AppError as exc:
        repo.fail_to_stable_state(db, session, exc.code)
        raise


async def stream_message(db: Session, session_id: str, message: str, is_disconnected,
                         resource_mode: str | None = None,
                         resource_type: str | None = None) -> AsyncIterator[dict[str, object]]:
    async with _workflow_lock(session_id):
        async for event in _stream_message(db, session_id, message, is_disconnected,
                                        resource_mode=resource_mode,
                                        resource_type=resource_type):
            yield event


async def _stream_message(db: Session, session_id: str, message: str, is_disconnected,
                          resource_mode: str | None = None,
                          resource_type: str | None = None) -> AsyncIterator[dict[str, object]]:
    request_id = uuid.uuid4().hex
    generation_id = uuid.uuid4().hex
    cancel_event = asyncio.Event()
    _generation_cancel_events[generation_id] = cancel_event
    _generation_sessions[generation_id] = session_id
    session = None

    try:
        repo.append_message(db, session_id, "user", message)
        session = repo.get_or_create_session(db, session_id)
        complete = _selected_complete(_runtime_selection(db, session_id))
        if _is_rediagnose(message):
            repo.restart_diagnosis(db, session)
        if session.state in {repo.SessionState.NEW.value, repo.SessionState.DIAGNOSING.value}:
            if session.state == repo.SessionState.NEW.value:
                repo.set_state(db, session, repo.SessionState.DIAGNOSING)
            yield {"event": "phase", "request_id": request_id, "generation_id": generation_id, "phase": "diagnosis"}
            diagnosis_complete, reply = await _diagnosis_reply(db, session, session_id, complete)
            if not diagnosis_complete:
                repo.append_message(db, session_id, "assistant", reply)
                yield {"event": "delta", "request_id": request_id, "content": reply, "provisional": False}
                yield {"event": "done", "request_id": request_id, "status": "completed", "state": session.state}
                return
            repo.set_state(db, session, repo.SessionState.PROFILE_READY)
            yield {"event": "phase", "request_id": request_id, "generation_id": generation_id, "phase": "profile"}
            raw = ""
            selection = _runtime_selection(db, session_id)
            async for item in _stream_items(_gateway, selection, build_profile_messages(_history_texts(db, session_id), session.profile_version + 1), 0.2):
                if cancel_event.is_set() or await is_disconnected():
                    raise ClientCancelledError()
                if isinstance(item, RoutedStreamEvent):
                    if item.event == "meta":
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
                yield {"event": "delta", "request_id": request_id, "content": delta, "provisional": True}
            try:
                canonical = serialize_profile(parse_profile(raw))
                repaired = False
                error_code = None
            except ProtocolValidationError as exc:
                canonical = await generate_profile(_history_texts(db, session_id), session.profile_version + 1, complete=complete)
                repaired = True
                error_code = exc.code
            yield {"event": "validation", "request_id": request_id, "valid": True, "repair_attempted": repaired, "error_code": error_code}
            if canonical.strip() != raw.strip():
                yield {"event": "replace", "request_id": request_id, "content": canonical}
            version = repo.save_profile(db, session, canonical)
            repo.append_message(db, session_id, "assistant", canonical)
            yield {"event": "persisted", "request_id": request_id, "profile_version": version}
            yield {"event": "done", "request_id": request_id, "status": "completed", "state": session.state}
            return

        if session.state != repo.SessionState.PROFILED.value or not session.profile_text:
            raise DomainStateError("会话尚未完成诊断，请先继续诊断。", "RESOURCE_NOT_READY")
        knowledge_context = retrieve_knowledge_context(
            db,
            session_id,
            _knowledge_retrieval_query(db, session_id, message),
        )
        knowledge_sources = _knowledge_payload(knowledge_context)
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

        if resource_mode:
            bundle_id = f"bundle-{uuid.uuid4().hex[:12]}"
            profile_text = session.profile_text or ""
            profile_subject = "other"
            try:
                parsed_profile = parse_profile(profile_text)
                profile_subject = parsed_profile.subject or "other"
            except Exception:
                pass

            class _BundleGateway:
                async def complete(self, messages, temperature=0.3):
                    result = await model_runtime_router.complete(
                        _runtime_selection(db, session_id), messages, temperature,
                    )
                    return result.text

            pipeline = BundlePipeline(_BundleGateway())

            try:
                single_type: ArtifactType | None = None
                if resource_mode == "single" and resource_type:
                    try:
                        single_type = ArtifactType(resource_type)
                    except ValueError:
                        pass

                requested_types = derive_requested_types(resource_mode, single_type)

                yield {"event": "resource_plan", "bundle_id": bundle_id,
                       "topic": "generating...",
                       "requested_types": [t.value for t in requested_types]}

                result = await pipeline.run(
                    bundle_id=bundle_id, mode=resource_mode, single_type=single_type,
                    profile_text=profile_text, learning_context="", knowledge_context="",
                    user_request=message, source_allowlist=[],
                    subject_category_hint=profile_subject,
                    profile_version=session.profile_version,
                    learning_state_version=str(session.learning_state_version),
                )

                bundle_dict = result.bundle.model_dump()
                yield {"event": "resource_bundle", **bundle_dict}

                save_bundle(db, result.bundle)

                yield {"event": "persisted", "bundle_id": bundle_id}

                repo.append_message(db, session_id, "assistant", json.dumps(bundle_dict, ensure_ascii=False))
                yield {"event": "done", "request_id": request_id, "status": "completed",
                       "state": session.state}

            except Exception as exc:
                yield {"event": "error", "request_id": request_id,
                       "code": "BUNDLE_FAILED", "message": str(exc)}
            finally:
                _bundle_cleanup(bundle_id)

            return

        raw = ""
        sources = await search_web_optional(message)
        source_payload = [item.model_dump() for item in sources]
        yield {"event": "sources", "request_id": request_id, "sources": source_payload, "cached": False}
        yield {"event": "knowledge_sources", "request_id": request_id, "sources": knowledge_sources, "cached": False}
        learning_context = learning.learning_context(db, session_id)
        selection = _runtime_selection(db, session_id)
        async for item in _stream_items(
            _gateway,
            selection,
            build_resource_messages(
                session.profile_text,
                message,
                source_payload,
                learning_context,
                knowledge_context.prompt,
            ),
            0.4,
        ):
            if cancel_event.is_set() or await is_disconnected():
                raise ClientCancelledError()
            if isinstance(item, RoutedStreamEvent):
                if item.event == "meta":
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
            yield {"event": "delta", "request_id": request_id, "content": delta, "provisional": True}
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
                session.profile_text,
                message,
                source_payload,
                knowledge_context.prompt,
                complete,
            )
            resource = parse_resource(canonical)
            repaired = True
            error_code = exc.code
        canonical, _used, citation_issues = sanitize_citations(
            canonical,
            knowledge_context.citations,
        )
        resource = parse_resource(canonical)
        validate_resource_quality(resource)
        yield {"event": "validation", "request_id": request_id, "valid": True, "repair_attempted": repaired, "error_code": error_code}
        if canonical.strip() != raw.strip():
            yield {"event": "replace", "request_id": request_id, "content": canonical}
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
