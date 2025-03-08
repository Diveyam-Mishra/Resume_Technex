import logging
import uuid
from typing import Dict, List, Optional, Union
from datetime import datetime
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import re
import json
import copy

from app.models.models import Resume, Statistics, User, Visibility
from app.schemas.resume import (
    CreateResumeRequest,
    ImportResumeRequest,
    Resume as ResumeSchema,
    ResumeData,
    UpdateResumeRequest,
    StatisticsResponse
)
from app.utils.constants import ErrorMessage
from app.services.printer import printer_service
from app.services.storage import storage_service


logger = logging.getLogger(__name__)


# Default resume data - minimal implementation (expand as needed)
DEFAULT_RESUME_DATA = {
    "metadata": {
        "template": "standard",
        "layout": [["header"], ["core"], ["skills"], ["experience"], ["education"]],
        "css": {
            "visible": False,
            "value": ""
        }
    },
    "basics": {
        "name": "",
        "email": "",
        "phone": "",
        "website": "",
        "headline": "",
        "summary": "",
        "photo": {}
    },
    "sections": {
        "skills": {
            "id": "skills",
            "name": "Skills",
            "items": []
        },
        "experience": {
            "id": "experience",
            "name": "Work Experience",
            "items": []
        },
        "education": {
            "id": "education", 
            "name": "Education",
            "items": []
        }
    }
}


def normalize_slug(slug: str) -> str:
    """
    Normalize a slug to be URL-friendly.
    """
    if not slug:
        return str(uuid.uuid4())
    
    # Convert to lowercase and replace non-alphanumeric characters with hyphens
    normalized = re.sub(r'[^a-z0-9]+', '-', slug.lower()).strip('-')
    
    if not normalized:
        return str(uuid.uuid4())
    
    return normalized


def get_resume_by_id(db: Session, resume_id: uuid.UUID, user_id: Optional[uuid.UUID] = None) -> Resume:
    """
    Get a resume by ID, optionally checking user ownership.
    """
    query = db.query(Resume).filter(Resume.id == resume_id)
    
    if user_id:
        query = query.filter(Resume.userId == user_id)
    
    resume = query.first()
    
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorMessage.RESUME_NOT_FOUND
        )
    
    return resume


def create_resume(db: Session, user_id: uuid.UUID, create_data: CreateResumeRequest) -> Resume:
    """
    Create a new resume.
    """
    # Get user info to prefill basic resume data
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorMessage.USER_NOT_FOUND
        )
    
    # Initialize with default resume data
    data = copy.deepcopy(DEFAULT_RESUME_DATA)
    
    # Prefill user info
    data["basics"]["name"] = user.name
    data["basics"]["email"] = user.email
    if user.picture:
        data["basics"]["photo"] = {"url": user.picture}
    
    # Generate slug if not provided
    slug = create_data.slug
    if not slug:
        slug = normalize_slug(create_data.title)
    else:
        slug = normalize_slug(slug)
    
    # Create resume
    try:
        resume = Resume(
            userId=user_id,
            title=create_data.title,
            slug=slug,
            visibility=create_data.visibility,
            data=data
        )
        
        db.add(resume)
        db.commit()
        db.refresh(resume)
        
        return resume
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.RESUME_SLUG_ALREADY_EXISTS
        )


def import_resume(db: Session, user_id: uuid.UUID, import_data: ImportResumeRequest) -> Resume:
    """
    Import a resume.
    """
    # Generate title if not provided
    title = import_data.title
    if not title:
        title = f"Imported Resume {datetime.now().strftime('%Y-%m-%d')}"
    
    # Generate slug if not provided
    slug = import_data.slug
    if not slug:
        slug = normalize_slug(title)
    else:
        slug = normalize_slug(slug)
    
    # Create resume
    try:
        resume = Resume(
            userId=user_id,
            title=title,
            slug=slug,
            visibility="private",
            data=import_data.data.dict()
        )
        
        db.add(resume)
        db.commit()
        db.refresh(resume)
        
        return resume
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.RESUME_SLUG_ALREADY_EXISTS
        )


def get_all_resumes(db: Session, user_id: uuid.UUID) -> List[Resume]:
    """
    Get all resumes for a user.
    """
    resumes = db.query(Resume).filter(Resume.userId == user_id).order_by(Resume.updatedAt.desc()).all()
    return resumes


def get_resume_by_username_slug(db: Session, username: str, slug: str, user_id: Optional[uuid.UUID] = None) -> Resume:
    """
    Get a public resume by username and slug.
    """
    resume = (
        db.query(Resume)
        .join(User)
        .filter(User.username == username)
        .filter(Resume.slug == slug)
        .filter(Resume.visibility == "public")
        .first()
    )
    
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorMessage.RESUME_NOT_FOUND
        )
    
    # Update statistics if the viewer is not the owner
    if not user_id or user_id != resume.userId:
        try:
            # Check if statistics exist
            stats = db.query(Statistics).filter(Statistics.resumeId == resume.id).first()
            
            if stats:
                stats.views += 1
            else:
                stats = Statistics(resumeId=resume.id, views=1, downloads=0)
                db.add(stats)
            
            db.commit()
        except Exception as e:
            logger.error(f"Error updating statistics: {e}")
            # Don't fail the request if statistics update fails
            db.rollback()
    
    return resume


def get_resume_statistics(db: Session, resume_id: uuid.UUID) -> StatisticsResponse:
    """
    Get resume statistics.
    """
    stats = db.query(Statistics).filter(Statistics.resumeId == resume_id).first()
    
    if not stats:
        return StatisticsResponse(views=0, downloads=0)
    
    return StatisticsResponse(views=stats.views, downloads=stats.downloads)


def update_resume(
    db: Session, 
    user_id: uuid.UUID, 
    resume_id: uuid.UUID, 
    update_data: UpdateResumeRequest
) -> Resume:
    """
    Update a resume.
    """
    resume = get_resume_by_id(db, resume_id, user_id)
    
    if resume.locked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.RESUME_LOCKED
        )
    
    try:
        # Update fields if provided
        if update_data.title is not None:
            resume.title = update_data.title
        
        if update_data.visibility is not None:
            resume.visibility = update_data.visibility
        
        if update_data.slug is not None:
            resume.slug = normalize_slug(update_data.slug)
        
        if update_data.data is not None:
            resume.data = update_data.data.dict()
        
        resume.updatedAt = datetime.utcnow()
        
        db.commit()
        db.refresh(resume)
        
        return resume
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.RESUME_SLUG_ALREADY_EXISTS
        )


def lock_resume(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID, locked: bool) -> Resume:
    """
    Lock or unlock a resume.
    """
    resume = get_resume_by_id(db, resume_id, user_id)
    
    resume.locked = locked
    resume.updatedAt = datetime.utcnow()
    
    db.commit()
    db.refresh(resume)
    
    return resume


def delete_resume(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> None:
    """
    Delete a resume.
    """
    resume = get_resume_by_id(db, resume_id, user_id)
    
    # Delete storage files for this resume
    try:
        storage_service.delete_object(user_id, "resumes", str(resume_id))
        storage_service.delete_object(user_id, "previews", str(resume_id))
    except Exception as e:
        logger.error(f"Error deleting resume files from storage: {e}")
        # Continue with deletion even if storage deletion fails
    
    # Delete the resume from the database
    db.delete(resume)
    db.commit()


async def print_resume(db: Session, resume: Resume, user_id: Optional[uuid.UUID] = None) -> str:
    """
    Generate a PDF for a resume.
    
    Args:
        db: Database session
        resume: Resume object
        user_id: User ID (if not provided, increments download count)
        
    Returns:
        URL of the generated PDF
    """
    # Generate PDF
    url = await printer_service.print_resume(resume)
    
    # Update statistics if the downloader is not the owner
    if not user_id or user_id != resume.userId:
        try:
            # Check if statistics exist
            stats = db.query(Statistics).filter(Statistics.resumeId == resume.id).first()
            
            if stats:
                stats.downloads += 1
            else:
                stats = Statistics(resumeId=resume.id, views=0, downloads=1)
                db.add(stats)
            
            db.commit()
        except Exception as e:
            logger.error(f"Error updating statistics: {e}")
            # Don't fail the request if statistics update fails
            db.rollback()
    
    return url


async def print_preview(resume: Resume) -> str:
    """
    Generate a preview image for a resume.
    
    Args:
        resume: Resume object
        
    Returns:
        URL of the generated preview image
    """
    return await printer_service.print_preview(resume)