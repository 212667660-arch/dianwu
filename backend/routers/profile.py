import uuid

from fastapi import APIRouter

from backend.models.schemas import ProfileRequest, ProfileResponse
from backend.services.profile_agent import generate_profile
from backend.services.model_runtime import RuntimeSelection, model_runtime_router
from backend.services.content_safety.models import SafetyStage
from backend.services.content_safety.service import content_safety_service

router = APIRouter(prefix="/api", tags=["profile"])


@router.post("/profile", response_model=ProfileResponse)
async def profile_endpoint(req: ProfileRequest) -> ProfileResponse:
    request_id = uuid.uuid4().hex
    selection = RuntimeSelection()
    generation_profile_id = model_runtime_router.generation_candidate_id(selection)
    safe_messages = []
    for message in req.messages:
        result = await content_safety_service.gate_request(
            message,
            intent="生成学习者画像",
            subject_category="other",
            generation_profile_id=generation_profile_id,
            request_id=request_id,
            session_tag="standalone-profile",
        )
        safe_messages.append(result.safe_text)
    completed_profile_id = None

    async def complete(messages, temperature=0.2):
        nonlocal completed_profile_id
        completion = await model_runtime_router.complete(selection, messages, temperature)
        completed_profile_id = completion.profile_id
        return completion.text

    profile_text = await generate_profile(safe_messages, complete=complete)
    reviewed = await content_safety_service.review_text(
        profile_text,
        stage=SafetyStage.ARTIFACT,
        intent="生成学习者画像",
        subject_category="other",
        artifact_type="learner-profile/v1",
        generation_profile_id=completed_profile_id,
        request_id=request_id,
        session_tag="standalone-profile",
    )
    return ProfileResponse(profile_text=reviewed.safe_text)
