import hashlib
import secrets
import string
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Union

import jwt
from fastapi import HTTPException, status
from pydantic import UUID4

from app.config.settings import settings

# JWT settings
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15  # 15 minutes
REFRESH_TOKEN_EXPIRE_DAYS = 2     # 2 days


def get_password_hash(password: str) -> str:
    """ Hash a password using SHA-256 """
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """ Verify if the hashed password matches the stored hash """
    return get_password_hash(plain_password) == hashed_password


def create_token(data: Dict[str, Any], token_type: str, expires_delta: Optional[timedelta] = None) -> str:
    """ Create a JWT token """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    elif token_type == "access":
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    elif token_type == "refresh":
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    else:
        raise ValueError(f"Invalid token type: {token_type}")
    
    to_encode.update({"exp": expire})
    
    secret = (
        settings.ACCESS_TOKEN_SECRET if token_type == "access"
        else settings.REFRESH_TOKEN_SECRET
    )
    
    encoded_jwt = jwt.encode(to_encode, secret, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str, token_type: str) -> Dict[str, Any]:
    """ Decode a JWT token """
    secret = (
        settings.ACCESS_TOKEN_SECRET if token_type == "access"
        else settings.REFRESH_TOKEN_SECRET
    )
    
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def create_access_token(user_id: Union[str, UUID4], is_two_factor_auth: bool = False) -> str:
    """ Create an access token """
    return create_token(
        data={"sub": str(user_id), "is_two_factor_auth": is_two_factor_auth}, 
        token_type="access"
    )


def create_refresh_token(user_id: Union[str, UUID4], is_two_factor_auth: bool = False) -> str:
    """ Create a refresh token """
    return create_token(
        data={"sub": str(user_id), "is_two_factor_auth": is_two_factor_auth}, 
        token_type="refresh"
    )


def generate_random_token() -> str:
    """ Generate a secure random token for password reset, verification, etc. """
    return secrets.token_urlsafe(32)


def generate_random_backup_codes(length: int = 8) -> list:
    """ Generate random backup codes for two-factor authentication """
    return [generate_random_code() for _ in range(length)]


def generate_random_code(length: int = 10) -> str:
    """ Generate a random alphanumeric code """
    alphabet = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))
