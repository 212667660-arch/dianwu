from fastapi import APIRouter

from backend.models.schemas import WebSearchRequest, WebSearchResponse
from backend.services.web_search import search_web

router = APIRouter(prefix="/api/web", tags=["web-search"])


@router.post("/search", response_model=WebSearchResponse)
async def web_search_endpoint(request: WebSearchRequest) -> WebSearchResponse:
    return WebSearchResponse(query=request.query, results=await search_web(request.query))
