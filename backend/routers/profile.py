from fastapi import APIRouter

from backend.models.schemas import ProfileRequest, ProfileResponse
from backend.services.profile_agent import generate_profile
from backend.services.model_runtime import RuntimeSelection, model_runtime_router

router = APIRouter(prefix="/api", tags=["profile"])


@router.post("/profile", response_model=ProfileResponse)
async def profile_endpoint(req: ProfileRequest) -> ProfileResponse:
    async def complete(messages, temperature=0.2):
        return (await model_runtime_router.complete(RuntimeSelection(), messages, temperature)).text
    return ProfileResponse(profile_text=await generate_profile(req.messages, complete=complete))
