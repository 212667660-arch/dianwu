from fastapi import APIRouter

from backend.models.schemas import ProfileRequest, ProfileResponse
from backend.services.profile_agent import generate_profile

router = APIRouter(prefix="/api", tags=["profile"])


@router.post("/profile", response_model=ProfileResponse)
async def profile_endpoint(req: ProfileRequest) -> ProfileResponse:
    return ProfileResponse(profile_text=await generate_profile(req.messages))
