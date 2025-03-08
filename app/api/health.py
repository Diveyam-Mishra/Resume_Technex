from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
import logging
import boto3
from botocore.exceptions import ClientError
import subprocess
import sys

from app.database.db import get_db
from app.config.settings import settings


router = APIRouter()
logger = logging.getLogger(__name__)


async def check_database(db: Session) -> Dict[str, Any]:
    """
    Check database connection.
    """
    try:
        db.execute("SELECT 1")
        return {"status": "healthy"}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {"status": "unhealthy", "message": str(e)}


async def check_storage() -> Dict[str, Any]:
    """
    Check storage connection.
    """
    try:
        # Configure S3/Minio client
        s3_client = boto3.client(
            's3',
            endpoint_url=f"{'https' if settings.STORAGE_USE_SSL else 'http'}://{settings.STORAGE_ENDPOINT}:{settings.STORAGE_PORT}",
            aws_access_key_id=settings.STORAGE_ACCESS_KEY,
            aws_secret_access_key=settings.STORAGE_SECRET_KEY,
            region_name=settings.STORAGE_REGION,
        )
        
        # Check if bucket exists
        s3_client.head_bucket(Bucket=settings.STORAGE_BUCKET)
        
        return {"status": "healthy"}
    except ClientError as e:
        logger.error(f"Storage health check failed: {e}")
        return {"status": "unhealthy", "message": str(e)}


async def check_browser() -> Dict[str, Any]:
    """
    Check Chrome browser connection.
    """
    try:
        # Try to connect to the browser
        import requests
        response = requests.get(
            f"{settings.CHROME_URL}/json/version", 
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "healthy",
                "version": data.get("Browser", "Unknown")
            }
        else:
            return {
                "status": "unhealthy",
                "message": f"Browser returned status code {response.status_code}"
            }
    except Exception as e:
        logger.error(f"Browser health check failed: {e}")
        return {"status": "unhealthy", "message": str(e)}


@router.get("")
async def health_check(db: Session = Depends(get_db)):
    """
    Perform health check on all services.
    """
    database_health = await check_database(db)
    storage_health = await check_storage()
    browser_health = await check_browser()
    
    is_healthy = (
        database_health["status"] == "healthy" and
        storage_health["status"] == "healthy" and
        browser_health["status"] == "healthy"
    )
    
    health_status = {
        "status": "healthy" if is_healthy else "unhealthy",
        "database": database_health,
        "storage": storage_health,
        "browser": browser_health,
    }
    
    return health_status


@router.get("/environment")
async def environment():
    """
    Get environment variables (only in development mode).
    """
    if settings.NODE_ENV == "production":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    
    # Return all settings, excluding sensitive ones
    settings_dict = settings.dict()
    
    # Hide sensitive values
    for key in [
        "ACCESS_TOKEN_SECRET", 
        "REFRESH_TOKEN_SECRET", 
        "STORAGE_ACCESS_KEY", 
        "STORAGE_SECRET_KEY",
        "GITHUB_CLIENT_SECRET",
        "GOOGLE_CLIENT_SECRET",
        "OPENID_CLIENT_SECRET",
        "CROWDIN_PERSONAL_TOKEN"
    ]:
        if key in settings_dict and settings_dict[key]:
            settings_dict[key] = "******"
    
    return settings_dict