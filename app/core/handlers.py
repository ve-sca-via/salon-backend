"""
Exception handlers for FastAPI application.

CORS headers are intentionally NOT added here. CORSMiddleware is wired as the
outermost middleware in `app/core/middleware.py`, so every response — including
the ones produced by these handlers — already receives the right
Access-Control-Allow-* headers. Don't duplicate that logic here; the two
implementations will drift.
"""
import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.core.exceptions import AppException
from app.schemas.response import ErrorResponse, ValidationErrorResponse, ErrorDetail

logger = logging.getLogger(__name__)


async def app_exception_handler(request: Request, exc: AppException):
    """Handle custom application exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            message=exc.detail,
            error_code=exc.error_code
        ).dict()
    )


async def http_exception_handler(request: Request, exc):
    """Handle FastAPI HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            message=exc.detail,
            error_code=f"HTTP_{exc.status_code}"
        ).dict()
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors from request parsing."""
    errors = [
        ErrorDetail(field=".".join(str(loc) for loc in error["loc"]), message=error["msg"])
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=ValidationErrorResponse(errors=errors).dict()
    )


async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    """Handle Pydantic validation errors from internal operations."""
    errors = [
        ErrorDetail(field=".".join(str(loc) for loc in error["loc"]), message=error["msg"])
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=ValidationErrorResponse(errors=errors).dict()
    )


async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(f"Unexpected error: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            message="An unexpected error occurred",
            error_code="INTERNAL_ERROR"
        ).dict()
    )


def register_exception_handlers(app):
    """Register all exception handlers with the FastAPI app."""
    from fastapi import HTTPException
    from slowapi.errors import RateLimitExceeded

    from app.core.rate_limit import rate_limit_exceeded_handler

    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, pydantic_validation_exception_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_exception_handler(Exception, general_exception_handler)
