"""
Logging configuration and setup for FastAPI application.
Configures rotating, file, and console logging with environment-aware formatting.
"""
import logging
import sys
import os

from app.core.config import settings


def setup_logging():
    """
    Configure logging for the application.
    Sets up handlers based on environment (development uses Rich logging, production uses standard).
    """
    # Get configured log level from settings (default INFO)
    try:
        log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    except (AttributeError, ValueError):
        log_level = logging.INFO

    # Use Rich logger only in development, standard logger in production
    if settings.is_development:
        try:
            from rich.logging import RichHandler
            handlers = [RichHandler(rich_tracebacks=True, show_time=True, show_path=True)]
        except ImportError:
            # Fallback if Rich is not available
            handlers = [logging.StreamHandler(sys.stdout)]
    else:
        handlers = [logging.StreamHandler(sys.stdout)]

    # Add file handler if LOG_FILE is specified
    if settings.LOG_FILE:
        try:
            log_dir = os.path.dirname(settings.LOG_FILE)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            handlers.append(logging.FileHandler(settings.LOG_FILE))
        except OSError as e:
            # Log error but don't fail startup
            logging.warning(f"Could not create log file directory: {e}")

    # Configure basicConfig
    logging.basicConfig(
        level=log_level,
        format=(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            if not settings.is_development
            else "%(name)s - %(message)s"
        ),
        handlers=handlers
    )

    # Configure uvicorn loggers for better visibility
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)

    return logging.getLogger(__name__)


def log_startup_info():
    """Log application startup information (avoiding secrets)."""
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 60)
    logger.info("Starting Salon Management API")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    
    try:
        # Mask Supabase URL in logs to avoid leaking secrets
        supabase_host = (
            settings.SUPABASE_URL.split("//")[-1].split("@")[-1]
            if settings.SUPABASE_URL
            else "(not configured)"
        )
    except Exception:
        supabase_host = "(redacted)"
    
    logger.info(f"Supabase configured: {bool(settings.SUPABASE_URL)} (host={supabase_host})")
    logger.info(f"Email SMTP: {settings.SMTP_HOST}:{settings.SMTP_PORT}")
    logger.info("Auth endpoints have stricter limits (5 login, 3 signup, 3 password reset)")
    logger.info("=" * 60)
