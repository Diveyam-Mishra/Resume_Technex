from typing import List, Literal, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator
from datetime import datetime
import re
import uuid


class UserSecrets(BaseModel):
    id: uuid.UUID
    userId: uuid.UUID
    password: Optional[str] = None
    resetToken: Optional[str] = None
    verificationToken: Optional[str] = None
    twoFactorSecret: Optional[str] = None
    twoFactorBackupCodes: List[str] = []
    refreshToken: Optional[str] = None
    lastSignedIn: Optional[datetime] = None
    createdAt: datetime
    updatedAt: datetime

    class Config:
        orm_mode = True


class User(BaseModel):
    id: uuid.UUID
    name: str
    email: EmailStr
    username: str
    locale: str = "en-US"
    picture: Optional[str] = None
    provider: Literal["email", "github", "google", "openid"] = "email"
    emailVerified: bool = False
    twoFactorEnabled: bool = False
    createdAt: datetime
    updatedAt: datetime

    class Config:
        orm_mode = True


class UserWithSecrets(User):
    secrets: Optional[UserSecrets] = None

    class Config:
        orm_mode = True


class UpdateUserRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    picture: Optional[str] = None
    locale: Optional[str] = None
    
    @field_validator('username')
    def username_alphanumeric(cls, v):
        if v is not None and not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Username must be alphanumeric with only underscores and hyphens allowed')
        return v