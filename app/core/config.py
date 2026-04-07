from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, model_validator
from typing import List
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
    APP_NAME: str
    APP_VERSION: str
    APP_DESCRIPTION: str
    ENVIRONMENT: str
    DEBUG: bool
    API_PREFIX: str
    
    # Server
    HOST: str
    PORT: int
    WORKERS: int
    TOKEN_CLEANUP_INTERVAL_SECONDS: int
    BACKGROUND_SHUTDOWN_TIMEOUT_SECONDS: float
    ALLOWED_HOSTS: str
    
    # =====================================================
    # SUPABASE CONFIGURATION
    # =====================================================
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    
    # Database
    DATABASE_URL: str
    
    # =====================================================
    # JWT & AUTHENTICATION
    # =====================================================
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int
    
    # =====================================================
    # PAYMENT GATEWAY (RAZORPAY)
    # =====================================================
    RAZORPAY_KEY_ID: str
    RAZORPAY_KEY_SECRET: str
    RAZORPAY_WEBHOOK_SECRET: str
    
    # =====================================================
    # EMAIL CONFIGURATION
    # =====================================================
    EMAIL_FROM: str
    EMAIL_FROM_NAME: str
    ADMIN_EMAIL: str
    
    # SMTP Settings
    SMTP_HOST: str
    SMTP_PORT: int
    SMTP_USER: str
    SMTP_PASSWORD: str
    SMTP_TLS: bool
    SMTP_SSL: bool
    
    # =====================================================
    # FRONTEND URLS
    # =====================================================
    FRONTEND_URL: str
    ADMIN_PANEL_URL: str
    VENDOR_PORTAL_URL: str
    RM_PORTAL_URL: str
    
    # =====================================================
    # CORS SETTINGS
    # =====================================================
    ALLOWED_ORIGINS: str
    
    # =====================================================
    # LOGGING
    # =====================================================
    LOG_LEVEL: str
    LOG_FILE: str

    # =====================================================
    # OTP SERVICE (MESSAGECENTRAL)
    # =====================================================
    MESSAGECENTRAL_CUSTOMER_ID: str
    MESSAGECENTRAL_KEY: str
    MESSAGECENTRAL_EMAIL: str
    MESSAGECENTRAL_BASE_URL: str
    MESSAGECENTRAL_DEFAULT_COUNTRY_CODE: str
    MESSAGECENTRAL_OTP_LENGTH: int
    MESSAGECENTRAL_OTP_EXPIRY_SECONDS: int

    # =====================================================
    # CLOUDINARY SETTINGS
    # =====================================================
    CLOUDINARY_CLOUD_NAME: str
    CLOUDINARY_API_KEY: str
    CLOUDINARY_API_SECRET: str
    CAREER_CLOUDINARY_UPLOAD_TYPE: str
    CAREER_CLOUDINARY_SIGNED_URL_TTL: int

    # =====================================================
    # FIELD VALIDATORS
    # =====================================================
    
    @field_validator('JWT_SECRET_KEY')
    @classmethod
    def validate_jwt_secret(cls, v):
        if not v:
            raise ValueError("JWT_SECRET_KEY must be set to a secure random value (min 32 characters)")
        if len(v) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters long")
        return v

    @field_validator("CAREER_CLOUDINARY_UPLOAD_TYPE")
    @classmethod
    def validate_career_cloudinary_upload_type(cls, value: str) -> str:
        upload_type = value.strip().lower()
        if upload_type not in {"private", "public"}:
            raise ValueError("CAREER_CLOUDINARY_UPLOAD_TYPE must be either 'private' or 'public'")
        return upload_type

    @field_validator("CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET", "CLOUDINARY_CLOUD_NAME")
    @classmethod
    def validate_cloudinary_credential_set(cls, value: str):
        # Normalize whitespace
        return value.strip()

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
    def allowed_hosts_list(self) -> List[str]:
        """Convert comma-separated ALLOWED_HOSTS string to list"""
        if isinstance(self.ALLOWED_HOSTS, str):
            return [host.strip() for host in self.ALLOWED_HOSTS.split(",")]
        return self.ALLOWED_HOSTS
    
    @property
    def allowed_origins_list(self) -> List[str]:
        if isinstance(self.ALLOWED_ORIGINS, str):
            return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]
        return self.ALLOWED_ORIGINS
    
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
