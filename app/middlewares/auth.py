from typing import Optional, Union
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from fastapi.security.utils import get_authorization_scheme_param
from sqlalchemy.orm import Session
import jwt

from app.database.db import get_db
from app.models.models import User
from app.schemas.auth import TokenPayload
from app.utils.constants import ErrorMessage
from app.utils.security import decode_token
from app.services.user import get_user_by_id


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    Get current user if authenticated, otherwise return None.
    This is for endpoints that work both with and without authentication.
    """
    token = request.cookies.get("Authentication")
    
    if not token:
        return None
    
    try:
        payload = decode_token(token, "access")
        user_id = payload.get("sub")
        if not user_id:
            return None
        
        user = get_user_by_id(db, user_id)
        if not user:
            return None
            
        return user
    except jwt.PyJWTError:
        return None


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """
    Get current user if authenticated, otherwise raise an exception.
    This is for endpoints that require authentication.
    """
    user = get_current_user_optional(request, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Get current active user.
    """
    if not current_user.emailVerified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified"
        )
    return current_user


def validate_two_factor_auth(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """
    Validate two-factor authentication.
    """
    token = request.cookies.get("Authentication")
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        payload = decode_token(token, "access")
        user_id = payload.get("sub")
        is_two_factor_auth = payload.get("is_two_factor_auth", False)
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user = get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # If user has 2FA enabled, we need to check if the token has been verified
        if user.twoFactorEnabled and not is_two_factor_auth:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Two-factor authentication required",
            )
            
        return user
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )