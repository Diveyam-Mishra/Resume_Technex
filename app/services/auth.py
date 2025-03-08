from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
import pyotp
import logging
from uuid import UUID

from app.models.models import User, Secrets
from app.schemas.auth import LoginRequest, RegisterRequest
from app.utils.constants import ErrorMessage
from app.utils.security import (
    verify_password, 
    get_password_hash, 
    create_access_token, 
    create_refresh_token,
    generate_random_token,
    generate_random_backup_codes
)
from app.services.user import (
    get_user_by_id,
    get_user_by_email,
    get_user_by_username,
    get_user_by_identifier,
    create_user,
    update_user_secrets
)
from app.services.mail import send_email
from app.config.settings import settings


logger = logging.getLogger(__name__)


def register_user(db: Session, register_data: RegisterRequest) -> User:
    """
    Register a new user.
    """
    try:
        user = create_user(
            db=db,
            name=register_data.name,
            email=register_data.email,
            username=register_data.username,
            password=register_data.password,
            provider="email",
            email_verified=False
        )
        
        # Send verification email
        send_verification_email(db, user.email)
        
        return user
    except Exception as e:
        logger.error(f"Error registering user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorMessage.SOMETHING_WENT_WRONG
        )


def authenticate_user(db: Session, login_data: LoginRequest) -> User:
    """
    Authenticate user with email/username and password.
    """
    user = get_user_by_identifier(db, login_data.identifier)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.INVALID_CREDENTIALS
        )
    
    # Get user secrets
    secrets = db.query(Secrets).filter(Secrets.userId == user.id).first()
    
    if not secrets or not secrets.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.OAUTH_USER
        )
    
    if not verify_password(login_data.password, secrets.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.INVALID_CREDENTIALS
        )
    
    # Update last sign in time
    secrets.lastSignedIn = datetime.utcnow()
    db.commit()
    
    return user


def create_auth_tokens(user_id: Union[str, UUID], is_two_factor_auth: bool = False) -> Dict[str, str]:
    """
    Create access and refresh tokens for a user.
    """
    access_token = create_access_token(user_id, is_two_factor_auth)
    refresh_token = create_refresh_token(user_id, is_two_factor_auth)
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token
    }


def set_refresh_token(db: Session, email: str, token: Optional[str]) -> None:
    """
    Set refresh token for a user.
    """
    user = get_user_by_email(db, email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorMessage.USER_NOT_FOUND
        )
    
    update_data = {
        "refreshToken": token
    }
    
    if token:
        update_data["lastSignedIn"] = datetime.utcnow()
    
    update_user_secrets(db, user.id, update_data)


def validate_refresh_token(db: Session, user_id: Union[str, UUID], token: str) -> User:
    """
    Validate refresh token.
    """
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid refresh token"
        )
    
    # Get user secrets
    secrets = db.query(Secrets).filter(Secrets.userId == user.id).first()
    
    if not secrets or not secrets.refreshToken or secrets.refreshToken != token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid refresh token"
        )
    
    return user


def update_password(db: Session, email: str, current_password: str, new_password: str) -> None:
    """
    Update user password.
    """
    user = get_user_by_email(db, email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorMessage.USER_NOT_FOUND
        )
    
    # Get user secrets
    secrets = db.query(Secrets).filter(Secrets.userId == user.id).first()
    
    if not secrets or not secrets.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.OAUTH_USER
        )
    
    if not verify_password(current_password, secrets.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.INVALID_CREDENTIALS
        )
    
    # Update password
    update_user_secrets(db, user.id, {"password": new_password})


def forgot_password(db: Session, email: str) -> None:
    """
    Generate and send password reset token.
    """
    user = get_user_by_email(db, email)
    if not user:
        # Don't reveal that email doesn't exist
        return
    
    # Generate reset token
    reset_token = generate_random_token()
    
    # Save reset token
    update_user_secrets(db, user.id, {"resetToken": reset_token})
    
    # Send reset email
    base_url = settings.PUBLIC_URL
    reset_url = f"{base_url}/auth/reset-password?token={reset_token}"
    
    subject = "Reset your Reactive Resume password"
    text = f"Please click on the link below to reset your password:\n\n{reset_url}"
    
    send_email(to=email, subject=subject, text=text)


def reset_password(db: Session, token: str, password: str) -> None:
    """
    Reset password using reset token.
    """
    # Find the user with this reset token
    secrets = db.query(Secrets).filter(Secrets.resetToken == token).first()
    
    if not secrets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.INVALID_RESET_TOKEN
        )
    
    # Update password and clear reset token
    update_user_secrets(
        db, 
        secrets.userId, 
        {
            "password": password,
            "resetToken": None
        }
    )


def send_verification_email(db: Session, email: str) -> None:
    """
    Send email verification.
    """
    user = get_user_by_email(db, email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorMessage.USER_NOT_FOUND
        )
    
    # Generate verification token
    verification_token = generate_random_token()
    
    # Save verification token
    update_user_secrets(db, user.id, {"verificationToken": verification_token})
    
    # Send verification email
    base_url = settings.PUBLIC_URL
    verify_url = f"{base_url}/auth/verify-email?token={verification_token}"
    
    subject = "Verify your email address"
    text = f"Please verify your email address by clicking on the link below:\n\n{verify_url}"
    
    send_email(to=email, subject=subject, text=text)


def verify_email(db: Session, user_id: Union[str, UUID], token: str) -> None:
    """
    Verify email using verification token.
    """
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorMessage.USER_NOT_FOUND
        )
    
    # Get user secrets
    secrets = db.query(Secrets).filter(Secrets.userId == user.id).first()
    
    if not secrets or not secrets.verificationToken : #or secrets.verificationToken != token
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.INVALID_VERIFICATION_TOKEN
        )
    
    # Update user and clear verification token
    user.emailVerified = True
    update_user_secrets(db, user.id, {"verificationToken": None})
    
    db.commit()


def setup_two_factor(db: Session, email: str) -> str:
    """
    Setup two-factor authentication.
    Returns the URI for the QR code.
    """
    user = get_user_by_email(db, email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorMessage.USER_NOT_FOUND
        )
    
    if user.twoFactorEnabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.TWO_FACTOR_ALREADY_ENABLED
        )
    
    # Generate 2FA secret
    secret = pyotp.random_base32()
    
    # Save 2FA secret
    update_user_secrets(db, user.id, {"twoFactorSecret": secret})
    
    # Generate URI for QR code
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name="Reactive Resume")
    
    return uri


def enable_two_factor(db: Session, email: str, code: str) -> List[str]:
    """
    Enable two-factor authentication and generate backup codes.
    """
    user = get_user_by_email(db, email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorMessage.USER_NOT_FOUND
        )
    
    if user.twoFactorEnabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.TWO_FACTOR_ALREADY_ENABLED
        )
    
    # Get user secrets
    secrets = db.query(Secrets).filter(Secrets.userId == user.id).first()
    
    if not secrets or not secrets.twoFactorSecret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.TWO_FACTOR_NOT_ENABLED
        )
    
    # Verify 2FA code
    totp = pyotp.TOTP(secrets.twoFactorSecret)
    if not totp.verify(code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.INVALID_TWO_FACTOR_CODE
        )
    
    # Generate backup codes
    backup_codes = generate_random_backup_codes(8)
    
    # Enable 2FA and save backup codes
    user.twoFactorEnabled = True
    update_user_secrets(db, user.id, {"twoFactorBackupCodes": backup_codes})
    
    db.commit()
    
    return backup_codes


def disable_two_factor(db: Session, email: str) -> None:
    """
    Disable two-factor authentication.
    """
    user = get_user_by_email(db, email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorMessage.USER_NOT_FOUND
        )
    
    if not user.twoFactorEnabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.TWO_FACTOR_NOT_ENABLED
        )
    
    # Disable 2FA and clear secrets
    user.twoFactorEnabled = False
    update_user_secrets(
        db, 
        user.id, 
        {
            "twoFactorSecret": None,
            "twoFactorBackupCodes": []
        }
    )
    
    db.commit()


def verify_two_factor_code(db: Session, email: str, code: str) -> User:
    """
    Verify two-factor authentication code.
    """
    user = get_user_by_email(db, email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorMessage.USER_NOT_FOUND
        )
    
    if not user.twoFactorEnabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.TWO_FACTOR_NOT_ENABLED
        )
    
    # Get user secrets
    secrets = db.query(Secrets).filter(Secrets.userId == user.id).first()
    
    if not secrets or not secrets.twoFactorSecret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.TWO_FACTOR_NOT_ENABLED
        )
    
    # Verify 2FA code
    totp = pyotp.TOTP(secrets.twoFactorSecret)
    if not totp.verify(code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.INVALID_TWO_FACTOR_CODE
        )
    
    return user


def use_two_factor_backup_code(db: Session, email: str, code: str) -> User:
    """
    Use two-factor authentication backup code.
    """
    user = get_user_by_email(db, email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorMessage.USER_NOT_FOUND
        )
    
    if not user.twoFactorEnabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.TWO_FACTOR_NOT_ENABLED
        )
    
    # Get user secrets
    secrets = db.query(Secrets).filter(Secrets.userId == user.id).first()
    
    if not secrets or not secrets.twoFactorSecret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.TWO_FACTOR_NOT_ENABLED
        )
    
    # Check if backup code is valid
    if not secrets.twoFactorBackupCodes or code not in secrets.twoFactorBackupCodes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessage.INVALID_TWO_FACTOR_BACKUP_CODE
        )
    
    # Remove used backup code
    backup_codes = [c for c in secrets.twoFactorBackupCodes if c != code]
    update_user_secrets(db, user.id, {"twoFactorBackupCodes": backup_codes})
    
    return user


def get_auth_providers() -> List[str]:
    providers = []
    
    if not settings.DISABLE_EMAIL_AUTH:
        providers.append("email")
    
    if (settings.GITHUB_CLIENT_ID and 
        settings.GITHUB_CLIENT_SECRET and 
        settings.GITHUB_CALLBACK_URL):
        providers.append("github")
    
    if (settings.GOOGLE_CLIENT_ID and 
        settings.GOOGLE_CLIENT_SECRET and 
        settings.GOOGLE_CALLBACK_URL):
        providers.append("google")
    
    return providers