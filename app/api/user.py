from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
import logging

from app.database.db import get_db
from app.middlewares.auth import validate_two_factor_auth
from app.models.models import User
from app.schemas.auth import MessageResponse
from app.schemas.user import User as UserSchema, UpdateUserRequest
from app.services.auth import send_verification_email, set_refresh_token
from app.services.user import delete_user, update_user, update_user_email

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/me", response_model=UserSchema)
async def get_current_user(
    user: User = Depends(validate_two_factor_auth)
):
    """
    Get the current user.
    """
    return UserSchema.from_orm(user)


@router.patch("/me", response_model=UserSchema)
async def update_current_user(
    update_data: UpdateUserRequest,
    user: User = Depends(validate_two_factor_auth),
    db: Session = Depends(get_db)
):
    """
    Update the current user.
    """
    try:
        # If user is updating their email, send a verification email
        if update_data.email and update_data.email != user.email:
            # Update email
            update_user_email(db, user.id, update_data.email)
            
            # Send verification email
            send_verification_email(db, update_data.email)
            
            # Update other fields if necessary
            update_data_without_email = UpdateUserRequest(
                name=update_data.name,
                username=update_data.username,
                picture=update_data.picture,
                locale=update_data.locale
            )
            
            updated_user = update_user(db, user.id, update_data_without_email)
        else:
            # Update user without changing email
            updated_user = update_user(db, user.id, update_data)
        
        return UserSchema.from_orm(updated_user)
    except Exception as e:
        logger.error(f"Error updating user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the user."
        )


@router.delete("/me", response_model=MessageResponse)
async def delete_current_user(
    response: Response,
    user: User = Depends(validate_two_factor_auth),
    db: Session = Depends(get_db)
):
    """
    Delete the current user.
    """
    try:
        # Delete the user
        delete_user(db, user.id)
        
        # Clear cookies
        response.delete_cookie("Authentication")
        response.delete_cookie("Refresh")
        
        return {"message": "Sorry to see you go, goodbye!"}
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting the user."
        )