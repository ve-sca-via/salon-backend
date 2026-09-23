"""
Logging configuration and setup for FastAPI application.
Configures rotating, file, and console logging with environment-aware formatting.

Outside development the formatter emits one JSON object per line. Our platform
(DigitalOcean) forwards stdout to Better Stack, whose source is configured to
parse each line as JSON into `message_json.*`. Plain prose lines would arrive as
an opaque blob you cannot filter, group or alert on, so keep this structured.
"""
import json
import logging
import sys
import os
from datetime import datetime, timezone

from app.core.config import settings
from app.core.request_context import get_request_id


class JsonFormatter(logging.Formatter):
    """
    Render each record as a single-line JSON object.

    Anything passed via `extra={...}` at the call site is merged into the
    payload as a top-level field, which is what makes Better Stack queries like
    `status_code:500` or "group by path" possible.
    """

    # Attributes present on a bare LogRecord are framework internals, not the
    # custom fields we want to forward. Derived rather than hand-listed so new
    # attributes in future Python versions don't leak into the payload.
    _RESERVED = frozenset(
        logging.LogRecord("", 0, "", 0, "", None, None).__dict__
    ) | {"asctime", "message", "taskName"}

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Fall back to the ContextVar so service-layer logs are correlated too,
        # even when the call site passed no explicit request_id.
        request_id = getattr(record, "request_id", None) or get_request_id()
        if request_id:
            payload["request_id"] = request_id

        for key, value in record.__dict__.items():
            if key not in self._RESERVED and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        # default=str so an unexpected non-serialisable extra degrades to its
        # repr instead of throwing inside the logging call.
        return json.dumps(payload, default=str, ensure_ascii=False)


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

    # Development keeps human-readable output; everywhere else emits JSON so the
    # log pipeline (DigitalOcean -> Better Stack) can index individual fields.
    if settings.is_development:
        logging.basicConfig(
            level=log_level,
            format="%(name)s - %(message)s",
            handlers=handlers,
        )
    else:
        json_formatter = JsonFormatter()
        for handler in handlers:
            handler.setFormatter(json_formatter)
        logging.basicConfig(level=log_level, handlers=handlers)

    # Configure uvicorn loggers for better visibility
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)

    # Quiet noisy third-party loggers (one line per Supabase REST call otherwise).
    for noisy in ("httpx", "httpcore", "hpack", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

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
    logger.info(
        f"Email (Resend): key={'configured' if settings.RESEND_API_KEY else 'MISSING - sends disabled'}, "
        f"from={settings.EMAIL_FROM}, admin={settings.ADMIN_EMAIL}"
    )
    logger.info("Auth endpoints have stricter limits (5 login, 3 signup, 3 password reset)")
    logger.info("=" * 60)
