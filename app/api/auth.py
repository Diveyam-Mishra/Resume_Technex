from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
import logging

from app.database.db import get_db
from app.middlewares.auth import validate_two_factor_auth
from app.models.models import User
from app.schemas.auth import (
    AuthResponse, 
    BackupCodesResponse, 
    ForgotPasswordRequest, 
    LoginRequest, 
    MessageResponse,
    RegisterRequest, 
    ResetPasswordRequest, 
    TokenResponse, 
    TwoFactorBackupRequest, 
    TwoFactorRequest, 
    TwoFactorSetupResponse,
    UpdatePasswordRequest
)
from app.schemas.user import User as UserSchema
from app.services.auth import (
    authenticate_user,
    create_auth_tokens,
    disable_two_factor,
    enable_two_factor,
    forgot_password,
    get_auth_providers,
    register_user,
    reset_password,
    send_verification_email,
    set_refresh_token,
    setup_two_factor,
    update_password,
    use_two_factor_backup_code,
    validate_refresh_token,
    verify_email,
    verify_two_factor_code
)
from app.utils.constants import ErrorMessage
from app.config.settings import settings


router = APIRouter()
logger = logging.getLogger(__name__)


def get_cookie_settings(token_type: str) -> Dict[str, str]:
    """
    Get cookie settings based on token type.
    """
    is_secure = str(settings.PUBLIC_URL).startswith("https://")
    
    if token_type == "access":
        # 15 minutes
        max_age = 15 * 60
    else:
        # 2 days
        max_age = 2 * 24 * 60 * 60
    
    return {
        "key": "Authentication" if token_type == "access" else "Refresh",
        "httponly": True,
        "samesite": "strict",
        "secure": is_secure,
        "max_age": max_age
    }


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest, 
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Register a new user.
    """
    # Check if signups are disabled
    if settings.DISABLE_SIGNUPS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Signups are currently disabled."
        )
    
    # Register the user
    user = register_user(db, request)
    
    # Generate tokens
    tokens = create_auth_tokens(user.id)
    print(0)
    # Set tokens in cookies
    
    response.set_cookie(**get_cookie_settings("access"), value=tokens["access_token"])
    print(0)
    response.set_cookie(**get_cookie_settings("refresh"), value=tokens["refresh_token"])
    print(0)
    # Save refresh token in database
    set_refresh_token(db, user.email, tokens["refresh_token"])
    print(0)
    # Return user with authentication status
    return {
        "status": "authenticated" 
    }


@router.post("/login", response_model=AuthResponse)
async def login(
    login_data: LoginRequest, 
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Authenticate a user and return a token.
    """
    # Check if email auth is disabled
    if settings.DISABLE_EMAIL_AUTH:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email authentication is disabled."
        )
    
    # Authenticate the user
    user = authenticate_user(db, login_data)
    
    # Generate tokens
    tokens = create_auth_tokens(user.id)
    
    # Set tokens in cookies
    response.set_cookie(**get_cookie_settings("access"), value=tokens["access_token"])
    response.set_cookie(**get_cookie_settings("refresh"), value=tokens["refresh_token"])
    
    # Save refresh token in database
    set_refresh_token(db, user.email, tokens["refresh_token"])
    
    # If the user has 2FA enabled, return 2FA required status
    if user.twoFactorEnabled:
        return {
            "status": "2fa_required",
            "user": UserSchema.from_orm(user)
        }
    
    # Otherwise, return authenticated status
    return {
        "status": "authenticated",
        "user": UserSchema.from_orm(user)
    }


@router.get("/providers", response_model=List[str])
async def auth_providers():
    """
    Get available authentication providers.
    """
    return get_auth_providers()


@router.post("/refresh", response_model=AuthResponse)
async def refresh_token(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Refresh access token using refresh token.
    """
    refresh_token_cookie = request.cookies.get("Refresh")
    
    if not refresh_token_cookie:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Validate refresh token
    try:
        # Decode token to get user ID
        from app.utils.security import decode_token
        payload = decode_token(refresh_token_cookie, "refresh")
        user_id = payload.get("sub")
        is_two_factor_auth = payload.get("is_two_factor_auth", False)
        
        # Validate refresh token
        user = validate_refresh_token(db, user_id, refresh_token_cookie)
        
        # Generate new tokens
        tokens = create_auth_tokens(user.id, is_two_factor_auth)
        
        # Set tokens in cookies
        response.set_cookie(**get_cookie_settings("access"), value=tokens["access_token"])
        response.set_cookie(**get_cookie_settings("refresh"), value=tokens["refresh_token"])
        
        # Save refresh token in database
        set_refresh_token(db, user.email, tokens["refresh_token"])
        
        # Return authenticated status
        return {
            "status": "authenticated",
            "user": UserSchema.from_orm(user)
        }
    except Exception as e:
        logger.error(f"Error refreshing token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    user: User = Depends(validate_two_factor_auth),
    db: Session = Depends(get_db)
):
    """
    Logout the current user.
    """
    # Clear refresh token in database
    set_refresh_token(db, user.email, None)
    
    # Clear cookies
    response.delete_cookie("Authentication")
    response.delete_cookie("Refresh")
    
    return {"message": "You have been logged out, tschüss!"}


@router.patch("/password", response_model=MessageResponse)
async def update_user_password(
    password_data: UpdatePasswordRequest,
    user: User = Depends(validate_two_factor_auth),
    db: Session = Depends(get_db)
):
    """
    Update user password.
    """
    update_password(db, user.email, password_data.currentPassword, password_data.newPassword)
    
    return {"message": "Your password has been successfully updated."}


# Password Recovery Flows
@router.post("/forgot-password", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def forgot_password_endpoint(
    forgot_password_data: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Request a password reset link.
    """
    try:
        forgot_password(db, forgot_password_data.email)
    except:
        # Ignore errors to prevent email enumeration
        pass
    
    return {
        "message": "A password reset link should have been sent to your inbox, if an account existed with the email you provided."
    }


@router.post("/reset-password", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def reset_password_endpoint(
    reset_data: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Reset password using reset token.
    """
    try:
        reset_password(db, reset_data.token, reset_data.password)
        return {"message": "Your password has been successfully reset."}
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.INVALID_RESET_TOKEN
        )


# Email Verification Flows
@router.post("/verify-email", response_model=MessageResponse)
async def verify_email_endpoint(
    token: str = Query(...),
    user: User = Depends(validate_two_factor_auth),
    db: Session = Depends(get_db)
):
    """
    Verify email using verification token.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.INVALID_VERIFICATION_TOKEN
        )
    
    if user.emailVerified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.EMAIL_ALREADY_VERIFIED
        )
    
    verify_email(db, user.id, token)
    
    return {"message": "Your email has been successfully verified."}


@router.post("/verify-email/resend", response_model=MessageResponse)
async def resend_verification_email_endpoint(
    user: User = Depends(validate_two_factor_auth),
    db: Session = Depends(get_db)
):
    """
    Resend verification email.
    """
    if user.emailVerified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.EMAIL_ALREADY_VERIFIED
        )
    
    send_verification_email(db, user.email)
    
    return {
        "message": "You should have received a new email with a link to verify your email address."
    }


# Two-Factor Authentication Flows
@router.post("/2fa/setup", response_model=TwoFactorSetupResponse)
async def setup_two_factor_endpoint(
    user: User = Depends(validate_two_factor_auth),
    db: Session = Depends(get_db)
):
    """
    Setup two-factor authentication.
    """
    uri = setup_two_factor(db, user.email)
    return {"message": uri}


@router.post("/2fa/enable", response_model=BackupCodesResponse, status_code=status.HTTP_200_OK)
async def enable_two_factor_endpoint(
    two_factor_data: TwoFactorRequest,
    response: Response,
    user: User = Depends(validate_two_factor_auth),
    db: Session = Depends(get_db)
):
    """
    Enable two-factor authentication.
    """
    backup_codes = enable_two_factor(db, user.email, two_factor_data.code)
    
    # Generate new tokens with 2FA enabled
    tokens = create_auth_tokens(user.id, is_two_factor_auth=True)
    
    # Set tokens in cookies
    response.set_cookie(**get_cookie_settings("access"), value=tokens["access_token"])
    response.set_cookie(**get_cookie_settings("refresh"), value=tokens["refresh_token"])
    
    # Save refresh token in database
    set_refresh_token(db, user.email, tokens["refresh_token"])
    
    return {"backup_codes": backup_codes}


@router.post("/2fa/disable", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def disable_two_factor_endpoint(
    user: User = Depends(validate_two_factor_auth),
    db: Session = Depends(get_db)
):
    """
    Disable two-factor authentication.
    """
    disable_two_factor(db, user.email)
    
    return {
        "message": "Two-factor authentication has been successfully disabled on your account."
    }


@router.post("/2fa/verify", response_model=UserSchema, status_code=status.HTTP_200_OK)
async def verify_two_factor_endpoint(
    two_factor_data: TwoFactorRequest,
    response: Response,
    user: User = Depends(validate_two_factor_auth),
    db: Session = Depends(get_db)
):
    """
    Verify two-factor authentication code.
    """
    verify_two_factor_code(db, user.email, two_factor_data.code)
    
    # Generate new tokens with 2FA verified
    tokens = create_auth_tokens(user.id, is_two_factor_auth=True)
    
    # Set tokens in cookies
    response.set_cookie(**get_cookie_settings("access"), value=tokens["access_token"])
    response.set_cookie(**get_cookie_settings("refresh"), value=tokens["refresh_token"])
    
    # Save refresh token in database
    set_refresh_token(db, user.email, tokens["refresh_token"])
    
    return UserSchema.from_orm(user)


@router.post("/2fa/backup", response_model=AuthResponse, status_code=status.HTTP_200_OK)
async def use_backup_two_factor_endpoint(
    backup_data: TwoFactorBackupRequest,
    response: Response,
    user: User = Depends(validate_two_factor_auth),
    db: Session = Depends(get_db)
):
    """
    Use backup code for two-factor authentication.
    """
    user = use_two_factor_backup_code(db, user.email, backup_data.code)
    
    # Generate new tokens with 2FA verified
    tokens = create_auth_tokens(user.id, is_two_factor_auth=True)
    
    # Set tokens in cookies
    response.set_cookie(**get_cookie_settings("access"), value=tokens["access_token"])
    response.set_cookie(**get_cookie_settings("refresh"), value=tokens["refresh_token"])
    
    # Save refresh token in database
    set_refresh_token(db, user.email, tokens["refresh_token"])
    
    return {
        "status": "authenticated",
        "user": UserSchema.from_orm(user)
    }