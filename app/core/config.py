from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
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
    ALLOWED_HOSTS: List[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])
    
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
    EMAIL_ENABLED: bool = Field(default=False)  # Toggle email sending (False = log only)
    EMAIL_FROM: str = Field(default="noreply@salonplatform.com")
    EMAIL_FROM_NAME: str = Field(default="Salon Management Platform")
    
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
    # FILE STORAGE
    # =====================================================
    STORAGE_BUCKET_PROFILES: str = Field(default="profiles")
    STORAGE_BUCKET_SALONS: str = Field(default="salons")
    STORAGE_BUCKET_SERVICES: str = Field(default="services")
    STORAGE_BUCKET_DOCUMENTS: str = Field(default="documents")
    MAX_FILE_SIZE_MB: int = Field(default=10)
    
    # =====================================================
    # BUSINESS CONFIGURATION
    # =====================================================
    DEFAULT_REGISTRATION_FEE: float = Field(default=5000.0)
    DEFAULT_CONVENIENCE_FEE_PERCENTAGE: float = Field(default=5.0)
    DEFAULT_RM_SCORE_PER_APPROVAL: int = Field(default=10)
    DEFAULT_PLATFORM_COMMISSION: float = Field(default=10.0)
    MAX_BOOKING_ADVANCE_DAYS: int = Field(default=30)
    CANCELLATION_WINDOW_HOURS: int = Field(default=24)
    
    # =====================================================
    # REDIS (OPTIONAL)
    # =====================================================
    REDIS_URL: Optional[str] = Field(default=None)
    CACHE_TTL_SECONDS: int = Field(default=3600)
    
    # =====================================================
    # LOGGING
    # =====================================================
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FILE: str = Field(default="logs/app.log")
    
    # =====================================================
    # RATE LIMITING
    # =====================================================
    RATE_LIMIT_PER_MINUTE: int = Field(default=60)
    RATE_LIMIT_PER_HOUR: int = Field(default=1000)
    
    # =====================================================
    # SENTRY (ERROR TRACKING)
    # =====================================================
    SENTRY_DSN: Optional[str] = Field(default=None)
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow"
    )
    
    @property
    def max_file_size_bytes(self) -> int:
        """Convert MB to bytes"""
        return self.MAX_FILE_SIZE_MB * 1024 * 1024
    
    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() == "development"
    
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

# Create settings instance
settings = Settings()
