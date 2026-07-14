from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services import db as repo

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
SessionPath = Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]
ResourcePath = Annotated[int, Path(ge=1)]


def _resource_export_content(resource: repo.Resource) -> str:
    sources = repo.resource_sources(resource)
    if not sources:
        return resource.content
    citations = ["【参考来源】"]
    for index, source in enumerate(sources, start=1):
        citations.append(f"{index}. {source['title']}\n   {source['url']}")
        if source["snippet"]:
            citations.append(f"   {source['snippet']}")
    return f"{resource.content.rstrip()}\n\n" + "\n".join(citations)


@router.get("/{session_id}")
async def get_session_history(session_id: SessionPath, db: Session = Depends(get_db)) -> dict[str, object]:
    session = repo.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {
        "session_id": session.session_id,
        "state": session.state,
        "profile_version": session.profile_version,
        "learning_state_version": session.learning_state_version,
        "profile_text": session.profile_text,
        "messages": [{"seq": item.seq, "role": item.role, "content": item.content} for item in session.messages],
        "resources": [
            {
                "id": item.id,
                "topic": item.topic,
                "content": item.content,
                "profile_version": item.profile_version,
                "learning_state_version": item.learning_state_version,
                "sources": repo.resource_sources(item),
                "quality_score": item.quality_score,
                "quality_issues": repo.resource_quality_issues(item),
                "questions": [
                    {
                        "id": question.id,
                        "ordinal": question.ordinal,
                        "difficulty": question.difficulty,
                        "prompt": question.prompt,
                    }
                    for question in item.questions
                ],
            }
            for item in session.resources
        ],
    }


@router.post("/{session_id}/rediagnose")
async def rediagnose(session_id: SessionPath, db: Session = Depends(get_db)) -> dict[str, str]:
    session = repo.get_or_create_session(db, session_id)
    repo.restart_diagnosis(db, session)
    return {"session_id": session_id, "state": session.state}


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: SessionPath, db: Session = Depends(get_db)) -> None:
    if not repo.delete_session(db, session_id):
        raise HTTPException(status_code=404, detail="会话不存在")


@router.get("/{session_id}/resources/{resource_id}/export")
async def export_resource(
    session_id: SessionPath,
    resource_id: ResourcePath,
    format: Literal["markdown", "txt"] = Query(default="markdown"),
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    resource = repo.get_resource(db, session_id, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="学习资源不存在")
    if format not in {"markdown", "txt"}:
        raise HTTPException(status_code=422, detail="format 仅支持 markdown 或 txt")
    extension = "md" if format == "markdown" else "txt"
    filename = f"learning-resource-{resource.id}.{extension}"
    return PlainTextResponse(
        _resource_export_content(resource),
        media_type="text/markdown" if format == "markdown" else "text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
