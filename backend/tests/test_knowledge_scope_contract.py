from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.models.schemas import ChatRequest


def test_chat_request_accepts_bounded_page_scope_and_search_mode() -> None:
    request = ChatRequest.model_validate({
        "session_id": "student_1",
        "message": "总结这一章",
        "resource_mode": "bundle",
        "knowledge_scope": {
            "document_id": 7,
            "page_start": 12,
            "page_end": 36,
            "search_mode": "expanded",
        },
    })

    assert request.knowledge_scope is not None
    assert request.knowledge_scope.page_start == 12
    assert request.knowledge_scope.page_end == 36
    assert request.knowledge_scope.search_mode == "expanded"


@pytest.mark.parametrize(
    "scope",
    [
        {"page_start": 2},
        {"page_start": 8, "page_end": 7},
        {"page_start": 1, "page_end": 501},
        {"page_start": 1, "page_end": 2, "search_mode": "all"},
        {"document_id": 0},
    ],
)
def test_chat_request_rejects_invalid_knowledge_scope(scope: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({
            "session_id": "student_1",
            "message": "总结",
            "knowledge_scope": scope,
        })
