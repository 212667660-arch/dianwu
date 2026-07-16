from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
import uuid

from sqlalchemy.orm import Session

from backend.database import get_db
from backend.errors import ContentCitationNotAllowedError
from backend.models.schemas import (
    BundleResponse,
    ChatRequest,
    ResourceRequest,
    ResourceResponse,
    RetryArtifactRequest,
    RetryArtifactResponse,
)
from backend.protocols.v2.models import ArtifactType
from backend.services.model_runtime import RuntimeSelection, model_runtime_router
from backend.services.content_safety.citations import validate_citations
from backend.services.content_safety.models import SafetyAction, SafetyStage
from backend.services.content_safety.service import content_safety_service
from backend.services.resource_agent import generate_resources
from backend.services.resource_bundle.service import (
    ResourceSelection,
    resource_bundle_service,
)
from backend.services.web_search import search_web_optional

router = APIRouter(prefix="/api", tags=["resource"])
BundleIdPath = Annotated[
    str,
    Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"),
]


def _safe_web_sources(sources):
    safe_sources = []
    for source in sources:
        title = content_safety_service.filter_context(source.title)
        snippet = content_safety_service.filter_context(source.snippet)
        url = content_safety_service.filter_context(source.url)
        if (
            not title.safe_text
            or (source.snippet and not snippet.safe_text)
            or url.metadata.decision != SafetyAction.ALLOW
            or url.safe_text != source.url
        ):
            continue
        safe_sources.append(source.model_copy(update={
            "title": title.safe_text,
            "snippet": snippet.safe_text,
            "url": url.safe_text,
        }))
    return safe_sources


@router.post("/resource", response_model=ResourceResponse)
async def resource_endpoint(req: ResourceRequest) -> ResourceResponse:
    request_id = uuid.uuid4().hex
    selection = RuntimeSelection()
    expected_generation_profile_id = model_runtime_router.generation_candidate_id(selection)
    safe_profile = await content_safety_service.gate_request(
        req.profile_text,
        intent="读取学习者画像",
        subject_category="other",
        generation_profile_id=expected_generation_profile_id,
        request_id=request_id,
        session_tag="standalone-resource",
    )
    safe_request = await content_safety_service.gate_request(
        req.message,
        intent=req.message,
        subject_category="other",
        generation_profile_id=expected_generation_profile_id,
        request_id=request_id,
        session_tag="standalone-resource",
    )
    sources = (
        _safe_web_sources(await search_web_optional(safe_request.safe_text))
        if req.use_web_search
        else []
    )
    source_payload = [
        {
            **source.model_dump(),
            "reference_id": f"资料{index}",
        }
        for index, source in enumerate(sources, 1)
    ]
    generation_profile_id = None

    async def complete(messages, temperature=0.2):
        nonlocal generation_profile_id
        completion = await model_runtime_router.complete(selection, messages, temperature)
        generation_profile_id = completion.profile_id
        return completion.text

    resource_text = await generate_resources(
        safe_profile.safe_text,
        safe_request.safe_text,
        source_payload,
        complete=complete,
    )
    citation_decision = validate_citations(
        resource_text,
        allowed={str(item["reference_id"]) for item in source_payload},
    )
    if not citation_decision.allowed:
        raise ContentCitationNotAllowedError()
    reviewed = await content_safety_service.review_text(
        resource_text,
        stage=SafetyStage.ARTIFACT,
        intent=safe_request.safe_text,
        subject_category="other",
        artifact_type="learning-resource/v1",
        generation_profile_id=generation_profile_id,
        request_id=request_id,
        session_tag="standalone-resource",
    )
    return ResourceResponse(
        resource_text=reviewed.safe_text,
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

    return BundleResponse.model_validate(bundle.model_dump(mode="json"))


@router.post(
    "/resource-bundles/{bundle_id}/artifacts/{artifact_type}/retry",
    response_model=RetryArtifactResponse,
)
async def retry_resource_artifact(
    bundle_id: BundleIdPath,
    artifact_type: ArtifactType,
    req: RetryArtifactRequest,
    db: Session = Depends(get_db),
) -> RetryArtifactResponse:
    bundle = await resource_bundle_service.retry_artifact(
        db,
        req.session_id,
        bundle_id,
        artifact_type,
        generation_id=uuid.uuid4().hex,
    )
    return RetryArtifactResponse(
        bundle=BundleResponse.model_validate(bundle.model_dump(mode="json"))
    )
