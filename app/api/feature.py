from fastapi import APIRouter, status
from pydantic import BaseModel

from app.config.settings import settings


router = APIRouter()


class FeatureFlags(BaseModel):
    """
    Feature flags response schema.
    """
    isSignupsDisabled: bool
    isEmailAuthDisabled: bool


@router.get("/flags", response_model=FeatureFlags)
async def get_feature_flags():
    """
    Get feature flags.
    """
    return {
        "isSignupsDisabled": settings.DISABLE_SIGNUPS,
        "isEmailAuthDisabled": settings.DISABLE_EMAIL_AUTH,
    }