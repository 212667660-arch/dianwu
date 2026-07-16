from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.errors import ResourceNotFoundError
from backend.models.schemas import BundleResponse, ChatRequest, ChatResponse
from backend.services.orchestrator import cancel_generation, handle_message, stream_message
from backend.services.content_safety.service import content_safety_service

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    if req.resource_mode:
        result = await handle_message(
            db,
            req.session_id,
            req.message,
            resource_mode=req.resource_mode,
            resource_type=req.resource_type,
            safety_service=content_safety_service,
        )
    else:
        result = await handle_message(
            db,
            req.session_id,
            req.message,
            safety_service=content_safety_service,
        )
    return ChatResponse(
        reply=result.reply,
        phase=result.phase,
        state=result.state,
        profile_version=result.profile_version,
        cached=result.cached,
        sources=result.sources,
        knowledge_sources=result.knowledge_sources,
        bundle=(
            BundleResponse.model_validate(result.bundle.model_dump(mode="json"))
            if result.bundle is not None
            else None
        ),
    )


@router.post("/chat/stream")
async def chat_stream_endpoint(req: ChatRequest, request: Request, db: Session = Depends(get_db)) -> StreamingResponse:
    async def events():
        async for event in stream_message(db, req.session_id, req.message, request.is_disconnected,
                                  resource_mode=req.resource_mode,
                                  resource_type=req.resource_type,
                                  safety_service=content_safety_service):
            name = str(event.pop("event"))
            payload = json.dumps(event, ensure_ascii=False)
            yield f"event: {name}\ndata: {payload}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.delete("/generations/{generation_id}")
async def cancel_generation_endpoint(
    generation_id: str,
    session_id: Annotated[str, Query(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")],
) -> dict[str, object]:
    if not cancel_generation(generation_id, session_id):
        raise ResourceNotFoundError("GENERATION_NOT_FOUND", "生成任务不存在、已结束或不属于该会话。")
    return {"generation_id": generation_id, "cancelled": True}
