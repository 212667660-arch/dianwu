from fastapi import APIRouter, Depends, HTTPException
import uuid

from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.schemas import BundleResponse, ChatRequest, ResourceRequest, ResourceResponse
from backend.protocols.v2.models import ArtifactType
from backend.services.model_runtime import RuntimeSelection, model_runtime_router
from backend.services.resource_agent import generate_resources
from backend.services.resource_bundle.pipeline import BundlePipeline
from backend.services.resource_db import save_bundle
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

    bundle_id = f"bundle-{uuid.uuid4().hex[:12]}"

    async def _gateway_complete(messages, temperature=0.3):
        result = await model_runtime_router.complete(RuntimeSelection(), messages, temperature)
        return result.text

    class Gateway:
        async def complete(self, messages, temperature=0.3):
            return await _gateway_complete(messages, temperature)

    pipeline = BundlePipeline(Gateway())
    result = await pipeline.run(
        bundle_id=bundle_id, mode=req.resource_mode, single_type=single_type,
        profile_text="", learning_context="", knowledge_context="",
        user_request=req.message, source_allowlist=[],
        subject_category_hint="other", profile_version=1, learning_state_version="v1",
    )

    save_bundle(db, req.session_id, result.bundle)
    db.commit()

    return BundleResponse(
        bundle_id=result.bundle.bundle_id,
        protocol_version=result.bundle.protocol_version,
        topic=result.bundle.topic,
        status=result.bundle.status.value,
        artifacts=[a.model_dump() for a in result.bundle.artifacts],
        aggregate_quality=result.bundle.aggregate_quality,
    )
