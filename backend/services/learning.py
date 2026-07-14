from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from backend.services import db as repo

_INTERVAL_DAYS = (1, 3, 7, 14, 30)


def _normalize_answer(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    normalized = re.sub(r"\s+", "", normalized)
    return normalized.strip("。.;；")


def _decimal(value: str) -> Decimal | None:
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def answers_match(submitted: str, expected: str) -> bool:
    actual = _normalize_answer(submitted)
    alternatives = [_normalize_answer(item) for item in expected.split("｜") if item.strip()]
    if actual in alternatives:
        return True
    actual_number = _decimal(actual)
    return actual_number is not None and any(_decimal(item) == actual_number for item in alternatives)


def mastery_label(score: float) -> str:
    if score < 0.4:
        return "WEAK"
    if score < 0.7:
        return "LEARNING"
    if score < 0.9:
        return "PROFICIENT"
    return "MASTERED"


def _updated_mastery(point: repo.KnowledgePoint, correct: bool, hint_count: int) -> float:
    if not correct:
        return max(0.0, point.mastery_score * 0.75)
    gain = max(0.05, 0.18 - min(hint_count, 4) * 0.03)
    return min(1.0, point.mastery_score + gain * (1.0 - point.mastery_score))


def _review_schedule(correct: bool, correct_streak: int, now: datetime) -> tuple[datetime, int, str]:
    if not correct:
        return now, 0, "ANSWER_INCORRECT"
    interval = _INTERVAL_DAYS[min(max(correct_streak, 1), len(_INTERVAL_DAYS)) - 1]
    return now + timedelta(days=interval), interval, "SPACED_REVIEW"


def submit_attempt(
    db: Session,
    session_id: str,
    question_id: int,
    submitted_answer: str,
    hint_count: int = 0,
    idempotency_key: str | None = None,
) -> tuple[repo.AnswerAttempt, repo.QuestionItem, repo.KnowledgePoint, bool] | None:
    with repo.session_lock(session_id):
        if idempotency_key:
            existing = db.query(repo.AnswerAttempt).filter_by(session_id=session_id, idempotency_key=idempotency_key).first()
            if existing is not None:
                question = existing.question
                return existing, question, question.knowledge_point, True

        question = db.query(repo.QuestionItem).filter_by(id=question_id, session_id=session_id).first()
        if question is None:
            return None
        point = question.knowledge_point
        now = datetime.utcnow()
        correct = answers_match(submitted_answer, question.answer)
        point.attempts += 1
        point.last_practiced_at = now
        point.mastery_score = round(_updated_mastery(point, correct, hint_count), 4)
        if correct:
            point.correct_attempts += 1
            point.correct_streak += 1
            point.last_error_type = None
        else:
            point.correct_streak = 0
            point.last_error_type = "ANSWER_MISMATCH"
        due_at, interval_days, reason = _review_schedule(correct, point.correct_streak, now)
        point.next_review_at = due_at

        review = (
            db.query(repo.ReviewTask)
            .filter_by(session_id=session_id, knowledge_point_id=point.id, status="PENDING")
            .order_by(repo.ReviewTask.id.desc())
            .first()
        )
        if review is None:
            review = repo.ReviewTask(session_id=session_id, knowledge_point=point, reason=reason, due_at=due_at, interval_days=interval_days)
            db.add(review)
        else:
            review.reason = reason
            review.due_at = due_at
            review.interval_days = interval_days

        feedback = "回答正确，已提高该知识点掌握度。" if correct else "回答与参考答案不一致，已加入立即复习队列。"
        attempt = repo.AnswerAttempt(
            session_id=session_id,
            question=question,
            submitted_answer=submitted_answer,
            is_correct=correct,
            score=1.0 if correct else 0.0,
            error_type=None if correct else "ANSWER_MISMATCH",
            feedback=feedback,
            hint_count=hint_count,
            idempotency_key=idempotency_key,
            mastery_after=point.mastery_score,
            next_review_at=due_at,
        )
        db.add(attempt)
        session = repo.get_session(db, session_id)
        if session is not None:
            session.learning_state_version += 1
        repo.commit(db)
        db.refresh(attempt)
        return attempt, question, point, False


def progress_snapshot(db: Session, session_id: str) -> dict[str, object] | None:
    session = repo.get_session(db, session_id)
    if session is None:
        return None
    points = db.query(repo.KnowledgePoint).filter_by(session_id=session_id).order_by(repo.KnowledgePoint.mastery_score, repo.KnowledgePoint.name).all()
    total_attempts = sum(point.attempts for point in points)
    correct_attempts = sum(point.correct_attempts for point in points)
    return {
        "session_id": session_id,
        "learning_state_version": session.learning_state_version,
        "total_attempts": total_attempts,
        "correct_attempts": correct_attempts,
        "accuracy": round(correct_attempts / total_attempts, 4) if total_attempts else 0.0,
        "knowledge_points": [knowledge_point_payload(point) for point in points],
    }


def knowledge_point_payload(point: repo.KnowledgePoint) -> dict[str, object]:
    return {
        "id": point.id,
        "name": point.name,
        "subject": point.subject,
        "mastery_score": round(point.mastery_score, 4),
        "mastery_label": mastery_label(point.mastery_score),
        "attempts": point.attempts,
        "correct_attempts": point.correct_attempts,
        "correct_streak": point.correct_streak,
        "last_error_type": point.last_error_type,
        "last_practiced_at": point.last_practiced_at,
        "next_review_at": point.next_review_at,
    }


def pending_reviews(db: Session, session_id: str, due_only: bool = False) -> list[dict[str, object]]:
    query = db.query(repo.ReviewTask).filter_by(session_id=session_id, status="PENDING")
    if due_only:
        query = query.filter(repo.ReviewTask.due_at <= datetime.utcnow())
    tasks = query.order_by(repo.ReviewTask.due_at, repo.ReviewTask.id).all()
    return [{
        "id": task.id,
        "knowledge_point_id": task.knowledge_point_id,
        "knowledge_point": task.knowledge_point.name,
        "reason": task.reason,
        "due_at": task.due_at,
        "interval_days": task.interval_days,
        "status": task.status,
    } for task in tasks]


def mistake_items(db: Session, session_id: str, limit: int = 50) -> list[dict[str, object]]:
    attempts = (
        db.query(repo.AnswerAttempt)
        .filter_by(session_id=session_id, is_correct=False)
        .order_by(repo.AnswerAttempt.created_at.desc(), repo.AnswerAttempt.id.desc())
        .limit(limit)
        .all()
    )
    return [{
        "attempt_id": attempt.id,
        "question_id": attempt.question_id,
        "knowledge_point": attempt.question.knowledge_point.name,
        "prompt": attempt.question.prompt,
        "submitted_answer": attempt.submitted_answer,
        "expected_answer": attempt.question.answer,
        "explanation": attempt.question.explanation,
        "error_type": attempt.error_type,
        "created_at": attempt.created_at,
    } for attempt in attempts]


def learning_context(db: Session, session_id: str) -> str:
    points = (
        db.query(repo.KnowledgePoint)
        .filter_by(session_id=session_id)
        .order_by(repo.KnowledgePoint.mastery_score, repo.KnowledgePoint.updated_at.desc())
        .limit(8)
        .all()
    )
    if not points:
        return ""
    action = next_action(db, session_id)
    lines = ["以下是后端根据真实学习记录维护的状态："]
    if action is not None:
        lines.append(f"- 推荐下一步：{action['action']}，原因：{action['reason']}")
    for point in points:
        lines.append(
            f"- {point.name}：掌握度 {point.mastery_score:.2f}，答题 {point.correct_attempts}/{point.attempts}，"
            f"最近错误 {point.last_error_type or '无'}"
        )
    return "\n".join(lines)


def next_action(db: Session, session_id: str) -> dict[str, object] | None:
    session = repo.get_session(db, session_id)
    if session is None:
        return None
    due_review = (
        db.query(repo.ReviewTask)
        .filter(
            repo.ReviewTask.session_id == session_id,
            repo.ReviewTask.status == "PENDING",
            repo.ReviewTask.due_at <= datetime.utcnow(),
        )
        .order_by(repo.ReviewTask.due_at, repo.ReviewTask.id)
        .first()
    )
    if due_review is not None:
        point = due_review.knowledge_point
        return _next_action_payload(
            session_id,
            "REVIEW",
            point,
            "基础" if point.mastery_score < 0.7 else "提高",
            "该知识点已到复习时间。",
            due_review.due_at,
            f"请针对{point.name}生成一组复习笔记和巩固练习。",
        )
    point = (
        db.query(repo.KnowledgePoint)
        .filter_by(session_id=session_id)
        .order_by(repo.KnowledgePoint.mastery_score, repo.KnowledgePoint.attempts, repo.KnowledgePoint.name)
        .first()
    )
    if point is None:
        return {
            "session_id": session_id,
            "action": "DIAGNOSE",
            "knowledge_point_id": None,
            "knowledge_point": None,
            "recommended_difficulty": "基础",
            "reason": "尚无可用知识点，需要先完成学习诊断。",
            "due_at": None,
            "suggested_request": "请先通过对话完成学习诊断。",
        }
    if point.attempts == 0:
        return _next_action_payload(session_id, "START_PRACTICE", point, "基础", "该薄弱知识点尚未经过练习验证。", None, f"请针对{point.name}生成基础讲解和诊断练习。")
    if point.mastery_score < 0.4:
        return _next_action_payload(session_id, "REMEDIATE", point, "基础", "掌握度较低，需要纠错和基础巩固。", point.next_review_at, f"请针对{point.name}的近期错误生成纠错讲解和基础练习。")
    if point.mastery_score < 0.7:
        return _next_action_payload(session_id, "PRACTICE", point, "提高", "知识点正在学习阶段，需要继续练习。", point.next_review_at, f"请针对{point.name}生成基础到提高的渐进练习。")
    if point.mastery_score < 0.9:
        return _next_action_payload(session_id, "CONSOLIDATE", point, "提高", "知识点已较熟练，需要综合巩固。", point.next_review_at, f"请针对{point.name}生成综合应用练习。")
    return _next_action_payload(session_id, "CHALLENGE", point, "挑战", "知识点已掌握，可以进入迁移和挑战。", point.next_review_at, f"请针对{point.name}生成挑战题和迁移应用任务。")


def _next_action_payload(
    session_id: str,
    action: str,
    point: repo.KnowledgePoint,
    difficulty: str,
    reason: str,
    due_at: datetime | None,
    suggested_request: str,
) -> dict[str, object]:
    return {
        "session_id": session_id,
        "action": action,
        "knowledge_point_id": point.id,
        "knowledge_point": point.name,
        "recommended_difficulty": difficulty,
        "reason": reason,
        "due_at": due_at,
        "suggested_request": suggested_request,
    }
