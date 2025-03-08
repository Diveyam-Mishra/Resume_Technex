from typing import Any, Dict, List, Optional, Union
from pydantic import PostgresDsn, AnyHttpUrl,AnyUrl
from pydantic_settings import BaseSettings
import os
class settings(BaseSettings):
    # Environment
    NODE_ENV: str = "production"
    
    # Server
    PORT: int = 3000
    
    # URLs
    PUBLIC_URL: AnyHttpUrl
    STORAGE_URL: Optional[AnyHttpUrl] = None
    
    DATABASE_URL: PostgresDsn
    
    # Authentication Secrets
    ACCESS_TOKEN_SECRET: str
    REFRESH_TOKEN_SECRET: str
    
    CHROME_TOKEN: str
    CHROME_URL: AnyHttpUrl
    CHROME_IGNORE_HTTPS_ERRORS: bool = False
    
    # Mail Server
    MAIL_FROM: str = "noreply@localhost"
    SMTP_URL: Optional[AnyUrl] = None
    
    LOCAL_STORAGE_PATH: str = os.path.join(os.getcwd(), "storage")
    
    
    # Feature Flags
    DISABLE_SIGNUPS: bool = False
    DISABLE_EMAIL_AUTH: bool = False
    
    # GitHub OAuth
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None
    GITHUB_CALLBACK_URL: Optional[AnyHttpUrl] = None
    
    # Google OAuth
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_CALLBACK_URL: Optional[AnyHttpUrl] = None
    
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = settings()