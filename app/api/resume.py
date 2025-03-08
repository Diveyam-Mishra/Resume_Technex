from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.orm import Session
import logging
import uuid
from typing import Any, Dict, List

from app.database.db import get_db
from app.middlewares.auth import get_current_user_optional, validate_two_factor_auth
from app.models.models import Resume, User
from app.schemas.resume import (
    CreateResumeRequest,
    ImportResumeRequest,
    Resume as ResumeSchema,
    UpdateResumeRequest,
    StatisticsResponse,
    PrintResponse
)
from app.services.resume import (
    create_resume,
    delete_resume,
    get_all_resumes,
    get_resume_by_id,
    get_resume_by_username_slug,
    get_resume_statistics,
    import_resume,
    lock_resume,
    print_preview,
    print_resume,
    update_resume
)
from app.utils.constants import ErrorMessage


router = APIRouter()
logger = logging.getLogger(__name__)


# Resume schema endpoint
@router.get("/schema")
async def get_schema():
    """
    Get the JSON schema for resume data structure.
    """
    from app.schemas.resume import ResumeData
    return ResumeData.model_json_schema()

# Create a new resume
@router.post("", response_model=ResumeSchema, status_code=status.HTTP_201_CREATED)
async def create_new_resume(
    create_data: CreateResumeRequest,
    user: User = Depends(validate_two_factor_auth),
    db: Session = Depends(get_db)
):
    """
    Create a new resume.
    """
    try:
        resume = create_resume(db, user.id, create_data)
        return resume
    except Exception as e:
        logger.error(f"Error creating resume: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create resume."
        )


# Import a resume
@router.post("/import", response_model=ResumeSchema, status_code=status.HTTP_201_CREATED)
async def import_new_resume(
    import_data: ImportResumeRequest,
    user: User = Depends(validate_two_factor_auth),
    db: Session = Depends(get_db)
):
    """
    Import a resume.
    """
    try:
        resume = import_resume(db, user.id, import_data)
        return resume
    except Exception as e:
        logger.error(f"Error importing resume: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to import resume."
        )


# Get all resumes for current user
@router.get("", response_model=List[ResumeSchema])
async def get_user_resumes(
    user: User = Depends(validate_two_factor_auth),
    db: Session = Depends(get_db)
):
    """
    Get all resumes for the current user.
    """
    resumes = get_all_resumes(db, user.id)
    return [resume for resume in resumes]


# Get a specific resume by ID
@router.get("/{resume_id}", response_model=ResumeSchema)
async def get_resume(
    resume_id: uuid.UUID = Path(...),
    user: User = Depends(validate_two_factor_auth),
    db: Session = Depends(get_db)
):
    """
    Get a specific resume by ID.
    Only returns resumes owned by the current user.
    """
    resume = get_resume_by_id(db, resume_id, user.id)
    return resume


# Get resume statistics
@router.get("/{resume_id}/statistics", response_model=StatisticsResponse)
async def get_resume_stats(
    resume_id: uuid.UUID = Path(...),
    user: User = Depends(validate_two_factor_auth),
    db: Session = Depends(get_db)
):
    """
    Get statistics for a specific resume.
    """
    # Verify the user owns this resume
    get_resume_by_id(db, resume_id, user.id)
    
    return get_resume_statistics(db, resume_id)


# Get a public resume by username and slug
@router.get("/public/{username}/{slug}", response_model=ResumeSchema)
async def get_public_resume(
    username: str = Path(...),
    slug: str = Path(...),
    user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    Get a public resume by username and slug.
    """
    user_id = user.id if user else None
    resume = get_resume_by_username_slug(db, username, slug, user_id)
    return resume


# Update a resume
@router.patch("/{resume_id}", response_model=ResumeSchema)
async def update_user_resume(
    update_data: UpdateResumeRequest,
    resume_id: uuid.UUID = Path(...),
    user: User = Depends(validate_two_factor_auth),
    db: Session = Depends(get_db)
):
    """
    Update a specific resume.
    """
    try:
        updated_resume = update_resume(db, user.id, resume_id, update_data)
        return updated_resume
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating resume: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update resume."
        )


# Lock a resume
@router.patch("/{resume_id}/lock", response_model=ResumeSchema)
async def lock_user_resume(
    resume_id: uuid.UUID = Path(...),
    set: bool = Body(True, embed=True),
    user: User = Depends(validate_two_factor_auth),
    db: Session = Depends(get_db)
):
    """
    Lock or unlock a resume.
    """
    try:
        updated_resume = lock_resume(db, user.id, resume_id, set)
        return updated_resume
    except Exception as e:
        logger.error(f"Error locking resume: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to lock/unlock resume."
        )


# Delete a resume
@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_resume(
    resume_id: uuid.UUID = Path(...),
    user: User = Depends(validate_two_factor_auth),
    db: Session = Depends(get_db)
):
    """
    Delete a resume.
    """
    try:
        delete_resume(db, user.id, resume_id)
    except Exception as e:
        logger.error(f"Error deleting resume: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete resume."
        )
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Print a resume (generate PDF)
@router.get("/print/{resume_id}", response_model=PrintResponse)
async def print_resume_endpoint(
    resume_id: uuid.UUID = Path(...),
    user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    Generate a PDF for a resume.
    """
    try:
        # Get the resume - this will also handle access control
        if user:
            # Try to get as the authenticated user
            try:
                resume = get_resume_by_id(db, resume_id, user.id)
            except HTTPException:
                # If the user doesn't own this resume, try to get it as a public resume
                resume = get_resume_by_id(db, resume_id)
                
                # If it's not public, raise an exception
                if resume.visibility != "public":
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=ErrorMessage.RESUME_NOT_FOUND
                    )
        else:
            # Get as public resume
            resume = get_resume_by_id(db, resume_id)
            
            # If it's not public, raise an exception
            if resume.visibility != "public":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=ErrorMessage.RESUME_NOT_FOUND
                )
        
        # Generate PDF
        user_id = user.id if user else None
        url = await print_resume(db, resume, user_id)
        
        return {"url": url}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error printing resume: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorMessage.RESUME_PRINTER_ERROR
        )


# Generate a preview image for a resume
@router.get("/print/{resume_id}/preview", response_model=PrintResponse)
async def print_resume_preview(
    resume_id: uuid.UUID = Path(...),
    user: User = Depends(validate_two_factor_auth),
    db: Session = Depends(get_db)
):
    """
    Generate a preview image for a resume.
    """
    try:
        # Get the resume - this will handle access control
        resume = get_resume_by_id(db, resume_id, user.id)
        
        # Generate preview
        url = await print_preview(resume)
        
        return {"url": url}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating preview: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorMessage.RESUME_PRINTER_ERROR
        )