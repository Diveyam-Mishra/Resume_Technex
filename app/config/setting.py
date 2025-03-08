from typing import Any, Dict, List, Optional, Union
from pydantic import BaseSettings, PostgresDsn, validator, AnyHttpUrl, Field


class Settings(BaseSettings):
    # Environment
    NODE_ENV: str = "production"
    
    # Server
    PORT: int = 3000
    
    # URLs
    PUBLIC_URL: AnyHttpUrl
    STORAGE_URL: AnyHttpUrl
    
    # Database
    DATABASE_URL: PostgresDsn
    
    # Authentication Secrets
    ACCESS_TOKEN_SECRET: str
    REFRESH_TOKEN_SECRET: str
    
    # Browser for PDF generation
    CHROME_TOKEN: str
    CHROME_URL: AnyHttpUrl
    CHROME_IGNORE_HTTPS_ERRORS: bool = False
    
    # Mail Server
    MAIL_FROM: str = "noreply@localhost"
    SMTP_URL: Optional[AnyHttpUrl] = None
    
    # Storage (MinIO/S3)
    STORAGE_ENDPOINT: str
    STORAGE_PORT: int
    STORAGE_REGION: str = "us-east-1"
    STORAGE_BUCKET: str
    STORAGE_ACCESS_KEY: str
    STORAGE_SECRET_KEY: str
    STORAGE_USE_SSL: bool = False
    STORAGE_SKIP_BUCKET_CHECK: bool = False
    
    # Crowdin (Optional)
    CROWDIN_PROJECT_ID: Optional[int] = None
    CROWDIN_PERSONAL_TOKEN: Optional[str] = None
    
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
    
    # OpenID
    VITE_OPENID_NAME: Optional[str] = None
    OPENID_AUTHORIZATION_URL: Optional[AnyHttpUrl] = None
    OPENID_CALLBACK_URL: Optional[AnyHttpUrl] = None
    OPENID_CLIENT_ID: Optional[str] = None
    OPENID_CLIENT_SECRET: Optional[str] = None
    OPENID_ISSUER: Optional[str] = None
    OPENID_SCOPE: Optional[str] = None
    OPENID_TOKEN_URL: Optional[AnyHttpUrl] = None
    OPENID_USER_INFO_URL: Optional[AnyHttpUrl] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()