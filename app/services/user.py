from typing import Optional, List, Dict, Any, Union
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
import logging
from uuid import UUID

from app.models.models import User, Secrets
from app.schemas.user import UpdateUserRequest
from app.utils.constants import ErrorMessage
from app.utils.security import get_password_hash


logger = logging.getLogger(__name__)


def get_user_by_id(db: Session, user_id: Union[str, UUID]) -> Optional[User]:
    """
    Get user by ID.
    """
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """
    Get user by email.
    """
    return db.query(User).filter(User.email == email).first()


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """
    Get user by username.
    """
    return db.query(User).filter(User.username == username).first()


def get_user_by_identifier(db: Session, identifier: str) -> Optional[User]:
    """
    Get user by email or username.
    """
    user = get_user_by_email(db, identifier)
    if not user:
        user = get_user_by_username(db, identifier)
    return user


def get_user_with_secrets(db: Session, user_id: Union[str, UUID]) -> tuple[User, Optional[Secrets]]:
    """
    Get user with secrets by ID.
    """
    user = get_user_by_id(db, user_id)
    if not user:
        return None, None
    
    secrets = db.query(Secrets).filter(Secrets.userId == user_id).first()
    return user, secrets


def create_user(
    db: Session, 
    name: str, 
    email: str, 
    username: str, 
    password: Optional[str] = None,
    locale: str = "en-US", 
    provider: str = "email",
    email_verified: bool = False,
    picture: Optional[str] = None
) -> User:
    """
    Create a new user.
    """
    # Check if user already exists
    if get_user_by_email(db, email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.USER_ALREADY_EXISTS
        )
    
    if get_user_by_username(db, username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.USER_ALREADY_EXISTS
        )
    
    # Create new user
    db_user = User(
        name=name,
        email=email,
        username=username,
        locale=locale,
        provider=provider,
        emailVerified=email_verified,
        picture=picture
    )
    
    db.add(db_user)
    db.flush()  # Flush to get the user ID
    
    # Create user secrets
    db_secrets = Secrets(
        userId=db_user.id,
        password=get_password_hash(password) if password else None
    )
    
    db.add(db_secrets)
    db.commit()
    db.refresh(db_user)
    
    return db_user


def update_user(
    db: Session, 
    user_id: Union[str, UUID], 
    update_data: UpdateUserRequest
) -> User:
    """
    Update existing user.
    """
    db_user = get_user_by_id(db, user_id)
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorMessage.USER_NOT_FOUND
        )
    
    # Check username uniqueness if changing
    if update_data.username and update_data.username != db_user.username:
        if get_user_by_username(db, update_data.username):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorMessage.USER_ALREADY_EXISTS
            )
    
    # Check email uniqueness if changing
    if update_data.email and update_data.email != db_user.email:
        if get_user_by_email(db, update_data.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorMessage.USER_ALREADY_EXISTS
            )
    
    # Update fields if provided
    if update_data.name:
        db_user.name = update_data.name
    if update_data.username:
        db_user.username = update_data.username
    if update_data.locale:
        db_user.locale = update_data.locale
    if update_data.picture:
        db_user.picture = update_data.picture
    
    db.commit()
    db.refresh(db_user)
    
    return db_user


def update_user_email(db: Session, user_id: Union[str, UUID], email: str) -> User:
    """
    Update user email and set emailVerified to False.
    """
    db_user = get_user_by_id(db, user_id)
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorMessage.USER_NOT_FOUND
        )
    
    # Check email uniqueness
    if get_user_by_email(db, email) and email != db_user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.USER_ALREADY_EXISTS
        )
    
    db_user.email = email
    db_user.emailVerified = False
    
    db.commit()
    db.refresh(db_user)
    
    return db_user


def update_user_secrets(
    db: Session, 
    user_id: Union[str, UUID], 
    update_data: Dict[str, Any]
) -> Secrets:
    """
    Update user secrets.
    """
    db_secrets = db.query(Secrets).filter(Secrets.userId == user_id).first()
    if not db_secrets:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorMessage.SECRETS_NOT_FOUND
        )
    
    # Update fields if provided
    if "password" in update_data:
        db_secrets.password = get_password_hash(update_data["password"])
    if "resetToken" in update_data:
        db_secrets.resetToken = update_data["resetToken"]
    if "verificationToken" in update_data:
        db_secrets.verificationToken = update_data["verificationToken"]
    if "twoFactorSecret" in update_data:
        db_secrets.twoFactorSecret = update_data["twoFactorSecret"]
    if "twoFactorBackupCodes" in update_data:
        db_secrets.twoFactorBackupCodes = update_data["twoFactorBackupCodes"]
    if "refreshToken" in update_data:
        db_secrets.refreshToken = update_data["refreshToken"]
    if "lastSignedIn" in update_data:
        db_secrets.lastSignedIn = update_data["lastSignedIn"]
    
    db.commit()
    db.refresh(db_secrets)
    
    return db_secrets


def delete_user(db: Session, user_id: Union[str, UUID]) -> bool:
    """
    Delete a user.
    """
    db_user = get_user_by_id(db, user_id)
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorMessage.USER_NOT_FOUND
        )
    
    db.delete(db_user)
    db.commit()
    
    return True