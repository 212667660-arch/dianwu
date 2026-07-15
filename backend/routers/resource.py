from fastapi import APIRouter

from backend.models.schemas import ResourceRequest, ResourceResponse
from backend.services.resource_agent import generate_resources
from backend.services.web_search import search_web_optional

router = APIRouter(prefix="/api", tags=["resource"])


@router.post("/resource", response_model=ResourceResponse)
async def resource_endpoint(req: ResourceRequest) -> ResourceResponse:
    sources = await search_web_optional(req.message) if req.use_web_search else []
    return ResourceResponse(
        resource_text=await generate_resources(
            req.profile_text,
            req.message,
            [item.model_dump() for item in sources],
        ),
        sources=sources,
        knowledge_sources=[],
    )
