from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from enum import Enum
from threading import RLock

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, relationship

from backend.database import Base
from backend.errors import DomainStateError, PersistenceError
from backend.knowledge.safety import (
    build_locator_label,
    safe_document_name,
    safe_sheet_name,
)


class SessionState(str, Enum):
    NEW = "NEW"
    DIAGNOSING = "DIAGNOSING"
    PROFILE_READY = "PROFILE_READY"
    PROFILED = "PROFILED"
    GENERATING = "GENERATING"
    FAILED = "FAILED"


STABLE_STATES = {SessionState.NEW.value, SessionState.DIAGNOSING.value, SessionState.PROFILED.value}
ALLOWED_TRANSITIONS = {
    SessionState.NEW.value: {SessionState.DIAGNOSING.value},
    SessionState.DIAGNOSING.value: {SessionState.DIAGNOSING.value, SessionState.PROFILE_READY.value},
    SessionState.PROFILE_READY.value: {SessionState.PROFILED.value},
    SessionState.PROFILED.value: {SessionState.GENERATING.value, SessionState.DIAGNOSING.value},
    SessionState.GENERATING.value: {SessionState.PROFILED.value},
    SessionState.FAILED.value: {SessionState.NEW.value, SessionState.DIAGNOSING.value, SessionState.PROFILED.value},
}
_SESSION_LOCKS: dict[str, RLock] = {}
_SESSION_LOCKS_GUARD = RLock()


def _session_lock(session_id: str) -> RLock:
    with _SESSION_LOCKS_GUARD:
        return _SESSION_LOCKS.setdefault(session_id, RLock())


def clear_runtime_state() -> None:
    with _SESSION_LOCKS_GUARD:
        _SESSION_LOCKS.clear()


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), unique=True, index=True, nullable=False)
    diagnosed = Column(Boolean, default=False, nullable=False)
    profile_text = Column(Text, nullable=True)
    state = Column(String(32), default=SessionState.NEW.value, nullable=False)
    diagnosis_turns = Column(Integer, default=0, nullable=False)
    profile_version = Column(Integer, default=0, nullable=False)
    learning_state_version = Column(Integer, default=0, nullable=False)
    last_stable_state = Column(String(32), default=SessionState.NEW.value, nullable=False)
    last_error_code = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan", order_by="Message.seq")
    resources = relationship("Resource", back_populates="session", cascade="all, delete-orphan", order_by="Resource.id")
    diagnosis_snapshots = relationship("DiagnosisSnapshot", back_populates="session", cascade="all, delete-orphan", order_by="DiagnosisSnapshot.turn")
    knowledge_points = relationship("KnowledgePoint", back_populates="session", cascade="all, delete-orphan", order_by="KnowledgePoint.id")
    model_preference = relationship("SessionModelPreference", back_populates="session", cascade="all, delete-orphan", uselist=False)


class SessionModelPreference(Base):
    __tablename__ = "session_model_preferences"

    session_id = Column(String(64), ForeignKey("chat_sessions.session_id", ondelete="CASCADE"), primary_key=True)
    profile_mode = Column(String(16), nullable=False, default="auto")
    preferred_profile_id = Column(String(64), nullable=True)
    model_id = Column(String(128), nullable=True)
    reasoning_effort = Column(String(16), nullable=False, default="auto")
    failover_override = Column(String(16), nullable=False, default="inherit")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    session = relationship("ChatSession", back_populates="model_preference")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("chat_sessions.session_id"), index=True, nullable=False)
    seq = Column(Integer, nullable=False)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("ChatSession", back_populates="messages")


class Resource(Base):
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("chat_sessions.session_id"), index=True, nullable=False)
    kind = Column(String(16), default="mixed", nullable=False)
    topic = Column(String(128), nullable=True)
    request_message = Column(Text, nullable=False, default="")
    content = Column(Text, nullable=False)
    sources_json = Column(Text, nullable=False, default="[]")
    knowledge_sources_json = Column(Text, nullable=False, default="[]")
    profile_version = Column(Integer, default=0, nullable=False)
    learning_state_version = Column(Integer, default=0, nullable=False)
    protocol_version = Column(String(32), default="learning-resource/v1", nullable=False)
    status = Column(String(32), default="COMPLETED", nullable=False)
    error_code = Column(String(64), nullable=True)
    quality_score = Column(Integer, default=0, nullable=False)
    quality_issues_json = Column(Text, nullable=False, default="[]")
    safety_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("ChatSession", back_populates="resources")
    questions = relationship("QuestionItem", back_populates="resource", cascade="all, delete-orphan", order_by="QuestionItem.ordinal")


class DiagnosisSnapshot(Base):
    __tablename__ = "diagnosis_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("chat_sessions.session_id"), index=True, nullable=False)
    turn = Column(Integer, nullable=False)
    decision_text = Column(Text, nullable=False)
    missing_fields = Column(Text, nullable=False, default="")
    confidence = Column(String(16), nullable=False, default="0")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("ChatSession", back_populates="diagnosis_snapshots")


class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"
    __table_args__ = (UniqueConstraint("session_id", "name", name="uq_knowledge_point_session_name"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("chat_sessions.session_id"), index=True, nullable=False)
    name = Column(String(128), nullable=False)
    subject = Column(String(80), nullable=False, default="")
    mastery_score = Column(Float, nullable=False, default=0.25)
    attempts = Column(Integer, nullable=False, default=0)
    correct_attempts = Column(Integer, nullable=False, default=0)
    correct_streak = Column(Integer, nullable=False, default=0)
    last_error_type = Column(String(64), nullable=True)
    last_practiced_at = Column(DateTime, nullable=True)
    next_review_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    session = relationship("ChatSession", back_populates="knowledge_points")
    questions = relationship("QuestionItem", back_populates="knowledge_point")
    review_tasks = relationship("ReviewTask", back_populates="knowledge_point", cascade="all, delete-orphan", order_by="ReviewTask.due_at")


class QuestionItem(Base):
    __tablename__ = "question_items"
    __table_args__ = (UniqueConstraint("resource_id", "ordinal", name="uq_question_resource_ordinal"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    resource_id = Column(Integer, ForeignKey("resources.id"), index=True, nullable=False)
    session_id = Column(String(64), ForeignKey("chat_sessions.session_id"), index=True, nullable=False)
    knowledge_point_id = Column(Integer, ForeignKey("knowledge_points.id"), index=True, nullable=False)
    ordinal = Column(Integer, nullable=False)
    difficulty = Column(String(16), nullable=False)
    prompt = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    explanation = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    resource = relationship("Resource", back_populates="questions")
    knowledge_point = relationship("KnowledgePoint", back_populates="questions")
    attempts = relationship("AnswerAttempt", back_populates="question", cascade="all, delete-orphan", order_by="AnswerAttempt.id")


class AnswerAttempt(Base):
    __tablename__ = "answer_attempts"
    __table_args__ = (UniqueConstraint("session_id", "idempotency_key", name="uq_attempt_session_idempotency"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("chat_sessions.session_id"), index=True, nullable=False)
    question_id = Column(Integer, ForeignKey("question_items.id"), index=True, nullable=False)
    submitted_answer = Column(Text, nullable=False)
    is_correct = Column(Boolean, nullable=False)
    score = Column(Float, nullable=False)
    error_type = Column(String(64), nullable=True)
    feedback = Column(Text, nullable=False)
    hint_count = Column(Integer, nullable=False, default=0)
    idempotency_key = Column(String(64), nullable=True)
    mastery_after = Column(Float, nullable=False)
    next_review_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    question = relationship("QuestionItem", back_populates="attempts")


class ReviewTask(Base):
    __tablename__ = "review_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("chat_sessions.session_id"), index=True, nullable=False)
    knowledge_point_id = Column(Integer, ForeignKey("knowledge_points.id"), index=True, nullable=False)
    reason = Column(String(64), nullable=False)
    due_at = Column(DateTime, index=True, nullable=False)
    interval_days = Column(Integer, nullable=False, default=0)
    status = Column(String(16), nullable=False, default="PENDING")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    knowledge_point = relationship("KnowledgePoint", back_populates="review_tasks")


def _commit(db: Session) -> None:
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError() from exc


def commit(db: Session) -> None:
    _commit(db)


def session_lock(session_id: str) -> RLock:
    return _session_lock(session_id)


def get_session(db: Session, session_id: str) -> ChatSession | None:
    return db.query(ChatSession).filter_by(session_id=session_id).first()


def get_or_create_session(db: Session, session_id: str) -> ChatSession:
    with _session_lock(session_id):
        session = get_session(db, session_id)
        if session is None:
            session = ChatSession(session_id=session_id)
            db.add(session)
            _commit(db)
            db.refresh(session)
        return session


def get_model_preference(db: Session, session_id: str) -> SessionModelPreference:
    if get_session(db, session_id) is None:
        raise DomainStateError("会话不存在。", "SESSION_NOT_FOUND")
    value = db.get(SessionModelPreference, session_id)
    return value or SessionModelPreference(
        session_id=session_id,
        profile_mode="auto",
        preferred_profile_id=None,
        model_id=None,
        reasoning_effort="auto",
        failover_override="inherit",
    )


def upsert_model_preference(
    db: Session,
    session_id: str,
    *,
    profile_mode: str,
    preferred_profile_id: str | None,
    model_id: str | None,
    reasoning_effort: str,
    failover_override: str,
) -> SessionModelPreference:
    get_or_create_session(db, session_id)
    value = db.get(SessionModelPreference, session_id)
    if value is None:
        value = SessionModelPreference(session_id=session_id)
        db.add(value)
    value.profile_mode = profile_mode
    value.preferred_profile_id = preferred_profile_id
    value.model_id = model_id
    value.reasoning_effort = reasoning_effort
    value.failover_override = failover_override
    _commit(db)
    db.refresh(value)
    return value


def _get_or_create_knowledge_point(db: Session, session_id: str, name: str, subject: str = "") -> KnowledgePoint:
    normalized = name.strip()[:128]
    point = next(
        (
            candidate for candidate in db.new
            if isinstance(candidate, KnowledgePoint)
            and candidate.session_id == session_id
            and candidate.name == normalized
        ),
        None,
    )
    if point is None:
        point = db.query(KnowledgePoint).filter_by(session_id=session_id, name=normalized).first()
    if point is None:
        point = KnowledgePoint(session_id=session_id, name=normalized, subject=subject.strip()[:80])
        db.add(point)
    elif subject and not point.subject:
        point.subject = subject.strip()[:80]
    return point


def _sync_profile_knowledge_points(db: Session, session: ChatSession, profile_text: str) -> None:
    from backend.protocols import parse_profile

    profile = parse_profile(profile_text)
    for weakness in profile.weaknesses:
        if weakness not in {"无", "未明确"}:
            _get_or_create_knowledge_point(db, session.session_id, weakness, profile.subject)


def _index_resource_questions(db: Session, resource: Resource) -> None:
    from backend.protocols import parse_resource

    parsed = parse_resource(resource.content)
    knowledge_point = _get_or_create_knowledge_point(db, resource.session_id, parsed.topic)
    for question in parsed.questions:
        resource.questions.append(QuestionItem(
            session_id=resource.session_id,
            knowledge_point=knowledge_point,
            ordinal=question.ordinal,
            difficulty=question.difficulty,
            prompt=question.prompt,
            answer=question.answer,
            explanation=question.explanation,
        ))


def backfill_learning_state(db: Session) -> None:
    from backend.errors import ProtocolValidationError
    from backend.protocols import parse_resource
    from backend.services.resource_quality import assess_resource_quality

    for session in db.query(ChatSession).all():
        if session.profile_text:
            try:
                _sync_profile_knowledge_points(db, session, session.profile_text)
            except ProtocolValidationError:
                continue
    for resource in db.query(Resource).all():
        try:
            if not resource.questions:
                _index_resource_questions(db, resource)
            quality = assess_resource_quality(parse_resource(resource.content))
            resource.quality_score = quality.score
            resource.quality_issues_json = json.dumps(quality.issues, ensure_ascii=False)
        except ProtocolValidationError:
            continue
    _commit(db)


def append_message(db: Session, session_id: str, role: str, content: str) -> Message:
    with _session_lock(session_id):
        get_or_create_session(db, session_id)
        next_seq = (db.query(func.max(Message.seq)).filter_by(session_id=session_id).scalar() or 0) + 1
        message = Message(session_id=session_id, seq=next_seq, role=role, content=content)
        db.add(message)
        _commit(db)
        db.refresh(message)
        return message


def history_texts(
    db: Session,
    session_id: str,
    maximum_messages: int | None = None,
    maximum_characters: int | None = None,
) -> list[str]:
    session = get_or_create_session(db, session_id)
    messages = [message.content for message in session.messages if message.role == "user"]
    if maximum_messages is not None and len(messages) > maximum_messages:
        messages = [messages[0], *messages[-(maximum_messages - 1):]]
    if maximum_characters is None or sum(len(message) for message in messages) <= maximum_characters:
        return messages
    first = messages[0]
    retained: list[str] = []
    remaining = maximum_characters - len(first)
    for message in reversed(messages[1:]):
        if len(message) > remaining:
            continue
        retained.append(message)
        remaining -= len(message)
    return [first, *reversed(retained)]


def set_state(db: Session, session: ChatSession, state: SessionState, error_code: str | None = None) -> None:
    previous = session.state
    if state.value not in ALLOWED_TRANSITIONS.get(previous, set()):
        raise DomainStateError(f"非法会话状态转换：{previous} -> {state.value}", "INVALID_STATE_TRANSITION")
    session.state = state.value
    session.last_error_code = error_code
    if state.value in STABLE_STATES:
        session.last_stable_state = state.value
    if state == SessionState.DIAGNOSING and previous == SessionState.NEW.value:
        session.diagnosis_turns = 0
    _commit(db)


def record_diagnosis_snapshot(db: Session, session: ChatSession, decision_text: str, missing_fields: list[str], confidence: float) -> None:
    session.diagnosis_turns += 1
    db.add(DiagnosisSnapshot(session_id=session.session_id, turn=session.diagnosis_turns, decision_text=decision_text, missing_fields="｜".join(missing_fields), confidence=f"{confidence:.2f}"))
    _commit(db)


def save_profile(db: Session, session: ChatSession, profile_text: str) -> int:
    if session.state != SessionState.PROFILE_READY.value:
        raise DomainStateError("当前状态不能保存画像。", "PROFILE_STATE_INVALID")
    session.profile_version += 1
    session.profile_text = profile_text
    session.diagnosed = True
    session.state = SessionState.PROFILED.value
    session.last_stable_state = SessionState.PROFILED.value
    session.last_error_code = None
    _sync_profile_knowledge_points(db, session, profile_text)
    _commit(db)
    return session.profile_version


def begin_generation(db: Session, session: ChatSession) -> None:
    if session.state != SessionState.PROFILED.value:
        raise DomainStateError("当前会话尚未完成诊断，不能生成学习资源。", "RESOURCE_NOT_READY")
    session.state = SessionState.GENERATING.value
    session.last_error_code = None
    _commit(db)


def get_resource(db: Session, session_id: str, resource_id: int) -> Resource | None:
    return db.query(Resource).filter(Resource.session_id == session_id, Resource.id == resource_id).first()


def normalize_source_snapshots(sources: list[dict[str, object]] | None) -> list[dict[str, str]]:
    """Keep a bounded, display-safe copy of public search result metadata."""
    normalized: list[dict[str, str]] = []
    for item in sources or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()[:300]
        url = str(item.get("url", "")).strip()[:2048]
        snippet = str(item.get("snippet", "")).strip()[:1000]
        if not title or not url:
            continue
        normalized.append({"title": title, "url": url, "snippet": snippet})
        if len(normalized) == 10:
            break
    return normalized


def resource_sources(resource: Resource) -> list[dict[str, str]]:
    try:
        parsed = json.loads(resource.sources_json or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return normalize_source_snapshots(parsed if isinstance(parsed, list) else [])


def normalize_knowledge_source_snapshots(
    sources: list[dict[str, object]] | None,
) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for item in sources or []:
        if not isinstance(item, dict):
            continue
        reference_id = str(item.get("reference_id", "")).strip()
        document_name = safe_document_name(item.get("document_name", ""))
        retrieval_mode = str(item.get("retrieval_mode", "keyword"))
        locator = item.get("locator")
        if (
            not re.fullmatch(r"资料[1-9]\d{0,2}", reference_id)
            or not document_name
            or retrieval_mode not in {"keyword", "hybrid"}
            or not isinstance(locator, dict)
        ):
            continue
        try:
            document_id = int(item.get("document_id", 0))
            chunk_id = int(item.get("chunk_id", 0))
            start = int(locator.get("start", 0))
            end = int(locator.get("end", 0))
        except (TypeError, ValueError):
            continue
        locator_type = str(locator.get("type", ""))
        if (
            document_id < 1
            or chunk_id < 1
            or start < 1
            or end < start
            or locator_type not in {"page", "slide", "sheet_rows", "paragraph"}
        ):
            continue
        safe_locator: dict[str, object] = {
            "type": locator_type,
            "start": start,
            "end": end,
        }
        if locator_type == "sheet_rows":
            sheet_name = safe_sheet_name(locator.get("sheet_name", ""))
            safe_locator["sheet_name"] = sheet_name
        else:
            sheet_name = None
        locator_label = build_locator_label(locator_type, start, end, sheet_name)
        normalized.append(
            {
                "reference_id": reference_id,
                "document_id": document_id,
                "document_name": document_name,
                "locator_label": locator_label,
                "locator": safe_locator,
                "chunk_id": chunk_id,
                "retrieval_mode": retrieval_mode,
            }
        )
        if len(normalized) == 8:
            break
    return normalized


def resource_knowledge_sources(resource: Resource) -> list[dict[str, object]]:
    try:
        parsed = json.loads(resource.knowledge_sources_json or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return normalize_knowledge_source_snapshots(
        parsed if isinstance(parsed, list) else []
    )


def resource_quality_issues(resource: Resource) -> list[str]:
    try:
        parsed = json.loads(resource.quality_issues_json or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def find_cached_resource(db: Session, session: ChatSession, request_message: str, ttl_seconds: int) -> Resource | None:
    if ttl_seconds <= 0:
        return None
    cutoff = datetime.utcnow() - timedelta(seconds=ttl_seconds)
    candidates = (
        db.query(Resource)
        .filter(
            Resource.session_id == session.session_id,
            Resource.profile_version == session.profile_version,
            Resource.learning_state_version == session.learning_state_version,
            Resource.request_message == request_message,
            Resource.knowledge_sources_json == "[]",
            Resource.status == "COMPLETED",
            Resource.created_at >= cutoff,
            Resource.safety_json.is_not(None),
        )
        .order_by(Resource.created_at.desc())
        .limit(20)
        .all()
    )
    from backend.services.content_safety.models import SafetyAction, SafetyMetadata

    for candidate in candidates:
        try:
            metadata = SafetyMetadata.model_validate_json(candidate.safety_json)
        except (TypeError, ValueError):
            continue
        if metadata.decision in {SafetyAction.ALLOW, SafetyAction.REDACT}:
            return candidate
    return None


def complete_generation(
    db: Session,
    session: ChatSession,
    topic: str,
    request_message: str,
    content: str,
    profile_version: int,
    sources: list[dict[str, object]] | None = None,
    knowledge_sources: list[dict[str, object]] | None = None,
    extra_quality_issues: list[str] | None = None,
    safety_metadata: object | None = None,
) -> Resource:
    if session.state != SessionState.GENERATING.value:
        raise DomainStateError("当前状态不能完成资源生成。", "GENERATION_STATE_INVALID")
    from backend.protocols import parse_resource
    from backend.services.resource_quality import assess_resource_quality

    quality = assess_resource_quality(parse_resource(content))
    additional_issues = [str(item)[:128] for item in extra_quality_issues or []]
    combined_issues = list(dict.fromkeys([*quality.issues, *additional_issues]))
    resource = Resource(
        session_id=session.session_id,
        kind="mixed",
        topic=topic,
        request_message=request_message,
        content=content,
        sources_json=json.dumps(normalize_source_snapshots(sources), ensure_ascii=False),
        knowledge_sources_json=json.dumps(
            normalize_knowledge_source_snapshots(knowledge_sources),
            ensure_ascii=False,
        ),
        profile_version=profile_version,
        learning_state_version=session.learning_state_version,
        quality_score=max(0, quality.score - 10 * len(additional_issues)),
        quality_issues_json=json.dumps(combined_issues, ensure_ascii=False),
        safety_json=(
            json.dumps(safety_metadata.model_dump(mode="json"), ensure_ascii=False)
            if hasattr(safety_metadata, "model_dump")
            else None
        ),
    )
    db.add(resource)
    _index_resource_questions(db, resource)
    session.state = SessionState.PROFILED.value
    session.last_stable_state = SessionState.PROFILED.value
    session.last_error_code = None
    _commit(db)
    db.refresh(resource)
    return resource


def finish_bundle_generation(db: Session, session: ChatSession) -> None:
    if session.state != SessionState.GENERATING.value:
        raise DomainStateError("当前状态不能完成资源包生成。", "GENERATION_STATE_INVALID")
    session.state = SessionState.PROFILED.value
    session.last_stable_state = SessionState.PROFILED.value
    session.last_error_code = None
    _commit(db)


def fail_to_stable_state(db: Session, session: ChatSession, error_code: str) -> None:
    session.state = session.last_stable_state or SessionState.NEW.value
    session.last_error_code = error_code
    _commit(db)


def restart_diagnosis(db: Session, session: ChatSession) -> None:
    if SessionState.DIAGNOSING.value not in ALLOWED_TRANSITIONS.get(session.state, set()):
        raise DomainStateError("当前状态不能重新诊断。", "REDIAGNOSE_STATE_INVALID")
    session.state = SessionState.DIAGNOSING.value
    session.diagnosis_turns = 0
    session.last_error_code = None
    _commit(db)


def delete_session(db: Session, session_id: str) -> bool:
    session = get_session(db, session_id)
    if session is None:
        return False
    from backend.knowledge.models import SessionKnowledgeCollection

    db.query(SessionKnowledgeCollection).filter_by(session_id=session_id).delete(
        synchronize_session=False
    )
    from backend.services.resource_db import delete_bundles_for_session

    delete_bundles_for_session(db, session_id)
    db.delete(session)
    _commit(db)
    return True
