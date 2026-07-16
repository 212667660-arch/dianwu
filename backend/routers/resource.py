from fastapi import APIRouter, Depends, HTTPException
import uuid

from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.schemas import BundleResponse, ChatRequest, ResourceRequest, ResourceResponse
from backend.protocols.v2.models import ArtifactType
from backend.services.model_runtime import RuntimeSelection, model_runtime_router
from backend.services.resource_agent import generate_resources
from backend.services.resource_bundle.service import (
    ResourceSelection,
    resource_bundle_service,
)
from backend.services.web_search import search_web_optional

router = APIRouter(prefix="/api", tags=["resource"])


@router.post("/resource", response_model=ResourceResponse)
async def resource_endpoint(req: ResourceRequest) -> ResourceResponse:
    sources = await search_web_optional(req.message) if req.use_web_search else []
    async def complete(messages, temperature=0.2):
        return (await model_runtime_router.complete(RuntimeSelection(), messages, temperature)).text
    return ResourceResponse(
        resource_text=await generate_resources(
            req.profile_text,
            req.message,
            [item.model_dump() for item in sources],
            complete=complete,
        ),
        sources=sources,
        knowledge_sources=[],
    )


@router.post("/resource-bundle", response_model=BundleResponse)
async def resource_bundle_endpoint(req: ChatRequest, db: Session = Depends(get_db)) -> BundleResponse:
    if not req.resource_mode:
        raise HTTPException(status_code=400, detail="resource_mode is required")

    single_type = None
    if req.resource_mode == "single":
        if not req.resource_type:
            raise HTTPException(status_code=400, detail="resource_type required for single mode")
        single_type = ArtifactType(req.resource_type)

    selection = (
        ResourceSelection.single(single_type)
        if single_type is not None
        else ResourceSelection.bundle()
    )
    bundle = await resource_bundle_service.generate(
        db,
        req.session_id,
        req.message,
        selection,
        generation_id=uuid.uuid4().hex,
    )

    return BundleResponse(
        bundle_id=bundle.bundle_id,
        protocol_version=bundle.protocol_version,
        topic=bundle.topic,
        status=bundle.status.value,
        artifacts=[a.model_dump() for a in bundle.artifacts],
        aggregate_quality=bundle.aggregate_quality,
    )
