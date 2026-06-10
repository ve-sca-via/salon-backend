import logging
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, model_validator
from typing import List
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _split_csv(value: str) -> List[str]:
    """Split a comma-separated string, trimming whitespace and surrounding quotes."""
    if not value:
        return []
    return [item.strip().strip("\"'") for item in value.split(",") if item.strip()]


def _normalize_origin(raw: str) -> str:
    """
    Normalize a CORS origin: strip trailing slash, validate scheme + host.
    Raises ValueError if the value isn't a valid origin (scheme://host[:port]).
    """
    candidate = raw.rstrip("/")
    parsed = urlparse(candidate)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"Invalid CORS origin '{raw}': must start with 'http://' or 'https://'"
        )
    if not parsed.netloc:
        raise ValueError(f"Invalid CORS origin '{raw}': missing host")
    if parsed.path or parsed.query or parsed.fragment:
        raise ValueError(
            f"Invalid CORS origin '{raw}': must be scheme://host[:port] only, no path"
        )
    return candidate


def _normalize_host(raw: str) -> str:
    """
    Normalize a trusted host entry: accept hostname, hostname:port, or a full URL.
    If a scheme is present (common copy-paste mistake) it is stripped with a warning.
    Wildcards like '*' or '*.railway.app' are passed through unchanged.
    """
    candidate = raw.strip()
    if candidate.startswith("*"):
        return candidate
    if "://" in candidate:
        logger.warning(
            "ALLOWED_HOSTS entry '%s' includes a scheme; stripping. "
            "TrustedHostMiddleware expects hostnames only (e.g., 'example.com').",
            candidate,
        )
        parsed = urlparse(candidate)
        candidate = parsed.netloc or parsed.path
    # Drop any path component if pasted in
    candidate = candidate.split("/", 1)[0]
    if not candidate:
        raise ValueError(f"Invalid host '{raw}': empty after normalization")
    return candidate

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
    # Preferred: the long-lived Auth Token shown in the MessageCentral dashboard
    # (used directly as the `authToken` header). When set, the app skips the
    # legacy password/key token-generation call.
    MESSAGECENTRAL_AUTH_TOKEN: str = ""
    # Legacy token-generation flow (Base64-encoded password + email). Only used as
    # a fallback when MESSAGECENTRAL_AUTH_TOKEN is not set.
    MESSAGECENTRAL_KEY: str = ""
    MESSAGECENTRAL_EMAIL: str = ""
    MESSAGECENTRAL_BASE_URL: str = ""
    MESSAGECENTRAL_DEFAULT_COUNTRY_CODE: str
    MESSAGECENTRAL_OTP_LENGTH: int
    MESSAGECENTRAL_OTP_EXPIRY_SECONDS: int

    # When true (and not in production), OTPs are generated + verified locally
    # and printed to the server log instead of being sent via MessageCentral.
    # Lets you test phone login/signup without spending SMS credits.
    OTP_DEV_MODE: bool = False

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
    
    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def validate_allowed_origins(cls, value: str) -> str:
        """Normalize and validate every CORS origin at load time."""
        normalized = [_normalize_origin(item) for item in _split_csv(value)]
        return ",".join(normalized)

    @field_validator("ALLOWED_HOSTS")
    @classmethod
    def validate_allowed_hosts(cls, value: str) -> str:
        """Normalize trusted hosts at load time (strip schemes, paths, quotes)."""
        normalized = [_normalize_host(item) for item in _split_csv(value)]
        return ",".join(normalized)

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
        """
        Trusted hosts for TrustedHostMiddleware (hostnames only, no scheme).
        In development, an empty list falls back to '*' so local tooling works.
        """
        hosts = _split_csv(self.ALLOWED_HOSTS) if isinstance(self.ALLOWED_HOSTS, str) else list(self.ALLOWED_HOSTS)
        if not hosts and self.is_development:
            return ["*"]
        return hosts

    @property
    def allowed_origins_list(self) -> List[str]:
        """
        CORS origins for CORSMiddleware (full URLs with scheme).
        In development, common localhost origins are always included so local
        frontends work without env tweaks.
        """
        origins = _split_csv(self.ALLOWED_ORIGINS) if isinstance(self.ALLOWED_ORIGINS, str) else list(self.ALLOWED_ORIGINS)
        if self.is_development:
            dev_defaults = [
                "http://localhost:3000",
                "http://localhost:5173",
                "http://localhost:8080",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:5173",
            ]
            for origin in dev_defaults:
                if origin not in origins:
                    origins.append(origin)
        return origins
    
    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() == "development"
    
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def otp_dev_enabled(self) -> bool:
        """Local OTP mode is only honored outside production, as a safety net."""
        return self.OTP_DEV_MODE and not self.is_production

    @property
    def cloudinary_is_configured(self) -> bool:
        return all([
            bool(self.CLOUDINARY_CLOUD_NAME),
            bool(self.CLOUDINARY_API_KEY),
            bool(self.CLOUDINARY_API_SECRET),
        ])

# Create settings instance
settings = Settings()
