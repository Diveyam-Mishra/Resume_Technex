from fastapi import APIRouter, HTTPException, status
import httpx
import logging
from typing import List
from pydantic import BaseModel

from app.config.settings import settings


router = APIRouter()
logger = logging.getLogger(__name__)


class Contributor(BaseModel):
    """
    Contributor model.
    """
    id: int
    name: str
    url: str
    avatar: str


@router.get("/github", response_model=List[Contributor])
async def get_github_contributors():
    """
    Get GitHub contributors.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.github.com/repos/AmruthPillai/Reactive-Resume/contributors", 
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"GitHub API error: {response.status_code} {response.text}")
                return []
            
            data = response.json()
            
            # Limit to first 20 contributors
            contributors = data[:20]
            
            return [
                {
                    "id": user["id"],
                    "name": user["login"],
                    "url": user["html_url"],
                    "avatar": user["avatar_url"]
                }
                for user in contributors
            ]
    except Exception as e:
        logger.error(f"Error fetching GitHub contributors: {e}")
        return []


@router.get("/crowdin", response_model=List[Contributor])
async def get_crowdin_contributors():
    """
    Get Crowdin contributors.
    """
    try:
        # Check if Crowdin credentials are set
        if not settings.CROWDIN_PROJECT_ID or not settings.CROWDIN_PERSONAL_TOKEN:
            return []
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.crowdin.com/api/v2/projects/{settings.CROWDIN_PROJECT_ID}/members",
                headers={"Authorization": f"Bearer {settings.CROWDIN_PERSONAL_TOKEN}"},
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"Crowdin API error: {response.status_code} {response.text}")
                return []
            
            data = response.json()
            
            # Limit to first 20 contributors
            contributors = data.get("data", [])[:20]
            
            return [
                {
                    "id": item["data"]["id"],
                    "name": item["data"]["username"],
                    "url": f"https://crowdin.com/profile/{item['data']['username']}",
                    "avatar": item["data"]["avatarUrl"]
                }
                for item in contributors
            ]
    except Exception as e:
        logger.error(f"Error fetching Crowdin contributors: {e}")
        return []