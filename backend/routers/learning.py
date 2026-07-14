from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.schemas import (
    AnswerAttemptRequest,
    AnswerAttemptResponse,
    MistakeItemResponse,
    NextActionResponse,
    ProgressResponse,
    ReviewTaskResponse,
)
from backend.services import db as repo
from backend.services import learning

router = APIRouter(prefix="/api/sessions", tags=["learning-progress"])
SessionPath = Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]
QuestionPath = Annotated[int, Path(ge=1)]


@router.post("/{session_id}/questions/{question_id}/attempts", response_model=AnswerAttemptResponse)
async def submit_answer_attempt(
    session_id: SessionPath,
    question_id: QuestionPath,
    request: AnswerAttemptRequest,
    db: Session = Depends(get_db),
) -> AnswerAttemptResponse:
    result = learning.submit_attempt(
        db,
        session_id,
        question_id,
        request.answer,
        request.hint_count,
        request.idempotency_key,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="练习题不存在或不属于该会话")
    attempt, question, point, duplicate = result
    return AnswerAttemptResponse(
        attempt_id=attempt.id,
        question_id=question.id,
        duplicate=duplicate,
        correct=attempt.is_correct,
        score=attempt.score,
        submitted_answer=attempt.submitted_answer,
        expected_answer=question.answer,
        explanation=question.explanation,
        feedback=attempt.feedback,
        error_type=attempt.error_type,
        mastery_score=attempt.mastery_after,
        mastery_label=learning.mastery_label(attempt.mastery_after),
        next_review_at=attempt.next_review_at,
    )


@router.get("/{session_id}/progress", response_model=ProgressResponse)
async def get_learning_progress(session_id: SessionPath, db: Session = Depends(get_db)) -> ProgressResponse:
    snapshot = learning.progress_snapshot(db, session_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return ProgressResponse.model_validate(snapshot)


@router.get("/{session_id}/next-action", response_model=NextActionResponse)
async def get_next_learning_action(session_id: SessionPath, db: Session = Depends(get_db)) -> NextActionResponse:
    action = learning.next_action(db, session_id)
    if action is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return NextActionResponse.model_validate(action)


@router.get("/{session_id}/reviews", response_model=list[ReviewTaskResponse])
async def get_review_tasks(
    session_id: SessionPath,
    due_only: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[ReviewTaskResponse]:
    if repo.get_session(db, session_id) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return [ReviewTaskResponse.model_validate(item) for item in learning.pending_reviews(db, session_id, due_only)]


@router.get("/{session_id}/mistakes", response_model=list[MistakeItemResponse])
async def get_mistakes(
    session_id: SessionPath,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[MistakeItemResponse]:
    if repo.get_session(db, session_id) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return [MistakeItemResponse.model_validate(item) for item in learning.mistake_items(db, session_id, limit)]
