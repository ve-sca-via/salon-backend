from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, model_validator
from typing import List, Optional
import os
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    """
    Application configuration settings
    Loads from environment variables and .env file
    """
    
    # =====================================================
    # APPLICATION SETTINGS
    # =====================================================
    APP_NAME: str = Field(default="Salon Management Platform")
    APP_VERSION: str = Field(default="2.0.0")
    ENVIRONMENT: str = Field(default="development")
    DEBUG: bool = Field(default=True)
    API_PREFIX: str = Field(default="/api/v1")
    
    # Server
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    WORKERS: int = Field(default=4)
    ALLOWED_HOSTS: str = Field(default="localhost,127.0.0.1")
    
    @property
    def allowed_hosts_list(self) -> List[str]:
        """Convert comma-separated ALLOWED_HOSTS string to list"""
        if isinstance(self.ALLOWED_HOSTS, str):
            return [host.strip() for host in self.ALLOWED_HOSTS.split(",")]
        return self.ALLOWED_HOSTS
    
    # =====================================================
    # SUPABASE CONFIGURATION
    # =====================================================
    SUPABASE_URL: str = Field(default="")
    SUPABASE_ANON_KEY: str = Field(default="")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(default="")
    
    # Database
    DATABASE_URL: str
    
    # =====================================================
    # JWT & AUTHENTICATION
    # =====================================================
    JWT_SECRET_KEY: str  # No default - MUST be set in environment
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7)
    
    @field_validator('JWT_SECRET_KEY')
    @classmethod
    def validate_jwt_secret(cls, v):
        if not v or v == "your-super-secret-jwt-key-change-this":
            raise ValueError("JWT_SECRET_KEY must be set to a secure random value (min 32 characters)")
        if len(v) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters long")
        return v
    
    # =====================================================
    # PAYMENT GATEWAY (RAZORPAY)
    # =====================================================
    RAZORPAY_KEY_ID: str = Field(default="")
    RAZORPAY_KEY_SECRET: str = Field(default="")
    RAZORPAY_WEBHOOK_SECRET: str = Field(default="")
    
    # Legacy Stripe (can be removed)
    STRIPE_SECRET_KEY: str = Field(default="")
    STRIPE_WEBHOOK_SECRET: str = Field(default="")
    
    # =====================================================
    # EMAIL CONFIGURATION
    # =====================================================
    EMAIL_FROM: str = Field(default="lubist910@gmail.com")
    EMAIL_FROM_NAME: str = Field(default="Salon Management Platform")
    ADMIN_EMAIL: str = Field(default="admin@salonplatform.com")  # Admin notification email
    
    # Resend API (legacy)
    RESEND_API_KEY: str = Field(default="")
    
    # SMTP Settings
    SMTP_HOST: str = Field(default="smtp.gmail.com")
    SMTP_PORT: int = Field(default=587)
    SMTP_USER: str = Field(default="")
    SMTP_PASSWORD: str = Field(default="")
    SMTP_TLS: bool = Field(default=True)
    SMTP_SSL: bool = Field(default=False)
    
    # =====================================================
    # FRONTEND URLS
    # =====================================================
    FRONTEND_URL: str = Field(default="http://localhost:3000")
    ADMIN_PANEL_URL: str = Field(default="http://localhost:5174")
    VENDOR_PORTAL_URL: str = Field(default="http://localhost:3000/vendor")
    RM_PORTAL_URL: str = Field(default="http://localhost:3000/rm")
    
    # =====================================================
    # CORS SETTINGS
    # =====================================================
    ALLOWED_ORIGINS: str = Field(
        default="http://localhost:5173,http://localhost:3000,http://localhost:5174"
    )
    
    @property
    def allowed_origins_list(self) -> List[str]:
        if isinstance(self.ALLOWED_ORIGINS, str):
            return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]
        return self.ALLOWED_ORIGINS
    
    # =====================================================
    # GEOCODING
    # =====================================================
    GOOGLE_MAPS_API_KEY: str = Field(default="")
    OPENCAGE_API_KEY: str = Field(default="")
    
    # =====================================================
    # LOGGING
    # =====================================================
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FILE: str = Field(default="logs/app.log")

    # =====================================================
    # OTP SERVICE (MESSAGECENTRAL)
    # =====================================================
    MESSAGECENTRAL_CUSTOMER_ID: str = Field(default="")
    MESSAGECENTRAL_KEY: str = Field(default="")
    MESSAGECENTRAL_EMAIL: str = Field(default="")
    MESSAGECENTRAL_BASE_URL: str = Field(default="https://cpaas.messagecentral.com")
    MESSAGECENTRAL_DEFAULT_COUNTRY_CODE: str = Field(default="91")
    MESSAGECENTRAL_OTP_LENGTH: int = Field(default=6)
    MESSAGECENTRAL_OTP_EXPIRY_SECONDS: int = Field(default=300)  # 5 minutes

    # =====================================================
    # CLOUDINARY SETTINGS
    # =====================================================
    CLOUDINARY_CLOUD_NAME: str = Field(default="")
    CLOUDINARY_API_KEY: str = Field(default="")
    CLOUDINARY_API_SECRET: str = Field(default="")
    CAREER_CLOUDINARY_UPLOAD_TYPE: str = Field(default="private")
    CAREER_CLOUDINARY_SIGNED_URL_TTL: int = Field(default=3600)

    @field_validator("CAREER_CLOUDINARY_UPLOAD_TYPE")
    @classmethod
    def validate_career_cloudinary_upload_type(cls, value: str) -> str:
        upload_type = (value or "private").strip().lower()
        if upload_type not in {"private", "public"}:
            raise ValueError("CAREER_CLOUDINARY_UPLOAD_TYPE must be either 'private' or 'public'")
        return upload_type

    @field_validator("CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET", "CLOUDINARY_CLOUD_NAME")
    @classmethod
    def validate_cloudinary_credential_set(cls, value: str, info):
        # Normalize to avoid mixed whitespace-only values.
        return (value or "").strip()

    @model_validator(mode="after")
    def validate_cloudinary_credentials_consistency(self):
        creds = [
            bool(self.CLOUDINARY_CLOUD_NAME),
            bool(self.CLOUDINARY_API_KEY),
            bool(self.CLOUDINARY_API_SECRET),
        ]
        if any(creds) and not all(creds):
            raise ValueError(
                "Cloudinary configuration is partial. Set CLOUDINARY_CLOUD_NAME, "
                "CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET together."
            )
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow"
    )
    
    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() == "development"
    
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def cloudinary_is_configured(self) -> bool:
        return all([
            bool(self.CLOUDINARY_CLOUD_NAME),
            bool(self.CLOUDINARY_API_KEY),
            bool(self.CLOUDINARY_API_SECRET),
        ])

# Create settings instance
settings = Settings()
