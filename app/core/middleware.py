"""
Middleware setup for the FastAPI application.

Order matters. `add_middleware` adds to the front of the stack, so the LAST
call becomes the OUTERMOST wrapper. We want CORS to be outermost so that
even error responses get the right Access-Control-Allow-* headers.

Final request flow (outer -> inner):
    CORSMiddleware
      -> ProxyHeadersMiddleware     (trust X-Forwarded-* from platform edge)
      -> TrustedHostMiddleware      (production only)
      -> SlowAPIMiddleware          (rate limiting)
      -> LoggingMiddleware          (per-request timing logs)
      -> application

Note: we deliberately do NOT use HTTPSRedirectMiddleware. Platforms like
Railway and Render terminate TLS at the edge and forward HTTP internally;
that middleware would cause a redirect loop. Configure HTTPS enforcement
at the platform edge instead.
"""
import logging
from datetime import datetime

from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.config import settings

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Per-request timing and method/path logging."""

    async def dispatch(self, request: Request, call_next):
        logger.info(
            f"-> {request.method} {request.url.path} - "
            f"{request.client.host if request.client else 'unknown'}"
        )

        safe_headers = {
            k: v for k, v in request.headers.items()
            if k.lower() not in ("authorization", "cookie", "x-api-key")
        }
        if safe_headers:
            logger.debug(f"Request headers: {safe_headers}")

        start_time = datetime.utcnow()
        try:
            response = await call_next(request)
            process_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            logger.info(
                f"<- {request.method} {request.url.path} - "
                f"{response.status_code} - {process_time:.2f}ms"
            )
            return response
        except Exception as e:
            process_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            logger.error(
                f":( {request.method} {request.url.path} - ERROR - "
                f"{process_time:.2f}ms - {str(e)}"
            )
            raise


def _resolve_cors_origins() -> list[str]:
    """Resolve CORS origins and fail fast on missing production config."""
    origins = settings.allowed_origins_list
    if not origins:
        if settings.is_production:
            raise RuntimeError(
                "ALLOWED_ORIGINS is empty in production. "
                "Set it to a comma-separated list of full URLs "
                "(e.g., 'https://app.example.com,https://admin.example.com')."
            )
        logger.warning("ALLOWED_ORIGINS is empty; CORS will reject every cross-origin request.")
    return origins


def _resolve_trusted_hosts() -> list[str]:
    """Resolve trusted hosts for production. Empty list -> allow all (with warning)."""
    hosts = settings.allowed_hosts_list
    if not hosts:
        logger.warning(
            "ALLOWED_HOSTS is empty in production. Falling back to '*' (any host). "
            "Set it to your public hostname(s) for stronger Host-header validation."
        )
        return ["*"]
    return hosts


def setup_middleware(app):
    """
    Wire up middleware in the correct order.

    Remember: last `add_middleware` call = outermost wrapper. CORS must be last
    so it can attach headers to every response, including those produced by
    exception handlers.
    """
    # Innermost: per-request logging
    app.add_middleware(LoggingMiddleware)

    # Rate limiting
    app.add_middleware(SlowAPIMiddleware)

    # Production-only Host header validation
    if settings.is_production:
        trusted_hosts = _resolve_trusted_hosts()
        logger.info(f"TrustedHostMiddleware enabled with hosts: {trusted_hosts}")
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts)
    else:
        logger.info("Development mode: TrustedHostMiddleware disabled")

    # Trust X-Forwarded-* headers from the platform edge (Railway/Render/etc).
    # This makes request.url.scheme and request.client.host reflect the real
    # client, regardless of how uvicorn was started. Works for both prod and dev.
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

    # Outermost: CORS. Must be added last so it wraps every response,
    # including responses produced by exception handlers.
    cors_origins = _resolve_cors_origins()
    logger.info(f"CORSMiddleware enabled with origins: {cors_origins}")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
