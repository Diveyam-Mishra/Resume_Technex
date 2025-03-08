from typing import List, Literal, Optional, Union
from pydantic import BaseModel, EmailStr, Field, validator
from datetime import datetime
import re

from app.schemas.user import User, UserWithSecrets


class TokenPayload(BaseModel):
    sub: str
    is_two_factor_auth: bool = False


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    username: str
    password: str
    locale: str = "en-US"
    
    @validator('username')
    def username_alphanumeric(cls, v):
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Username must be alphanumeric with only underscores and hyphens allowed')
        return v
    
    @validator('password')
    def password_min_length(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v


class LoginRequest(BaseModel):
    identifier: str  # Can be email or username
    password: str


class UpdatePasswordRequest(BaseModel):
    currentPassword: str
    newPassword: str
    
    @validator('newPassword')
    def password_min_length(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str
    
    @validator('password')
    def password_min_length(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v


class TwoFactorRequest(BaseModel):
    code: str


class TwoFactorBackupRequest(BaseModel):
    code: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str


class AuthResponse(BaseModel):
    status: Literal["authenticated", "2fa_required"]
    user: User


class MessageResponse(BaseModel):
    message: str


class BackupCodesResponse(BaseModel):
    backup_codes: List[str]


class TwoFactorSetupResponse(BaseModel):
    message: str  # Contains the URI for the QR code


class AuthProviderResponse(BaseModel):
    providers: List[Literal["email", "github", "google", "openid"]]