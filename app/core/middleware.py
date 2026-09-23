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

Note: we deliberately do NOT use HTTPSRedirectMiddleware. Our platforms
(DigitalOcean in production, Railway in staging) terminate TLS at the edge and
forward HTTP internally; that middleware would cause a redirect loop. Configure
HTTPS enforcement at the platform edge instead.
"""
import logging
import time
from uuid import uuid4

from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.config import settings
from app.core.request_context import (
    REQUEST_ID_HEADER,
    reset_request_id,
    set_request_id,
)

logger = logging.getLogger(__name__)

# Requests slower than this are logged at WARNING so they surface without
# having to query for percentiles.
SLOW_REQUEST_MS = 2000


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Assigns a correlation ID to every request and logs its outcome.

    Only one line per request is emitted at INFO: the completion line, which
    already carries the method, path and client that an inbound line would.
    Logging both doubled ingest volume for no extra signal.
    """

    async def dispatch(self, request: Request, call_next):
        # Honour an upstream ID if the caller already set one, so a request can
        # be followed across services; otherwise mint one.
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid4().hex
        request.state.request_id = request_id
        token = set_request_id(request_id)

        client_ip = request.client.host if request.client else "unknown"
        context = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "client_ip": client_ip,
        }

        logger.debug(f"-> {request.method} {request.url.path}", extra=context)

        start_time = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            # No exc_info here. Starlette's ServerErrorMiddleware wraps this one,
            # so `general_exception_handler` sees the same exception and logs the
            # traceback; emitting it here too would duplicate every stack trace.
            # This line contributes the timing, joined to that one by request_id.
            logger.error(
                f"{request.method} {request.url.path} raised {type(exc).__name__}",
                extra={
                    **context,
                    "duration_ms": round(duration_ms, 2),
                    "exception_type": type(exc).__name__,
                },
            )
            raise
        else:
            duration_ms = (time.perf_counter() - start_time) * 1000
            level = logging.INFO
            if response.status_code >= 500 or duration_ms >= SLOW_REQUEST_MS:
                level = logging.WARNING
            logger.log(
                level,
                f"{request.method} {request.url.path} "
                f"{response.status_code} {duration_ms:.2f}ms",
                extra={
                    **context,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            # Echo the ID so clients and support can quote it in bug reports.
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            reset_request_id(token)


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

    # Trust X-Forwarded-* headers from the platform edge (DigitalOcean/Railway).
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
