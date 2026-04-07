"""
Exception handlers for FastAPI application.
Centralized error handling with consistent response format and CORS headers.
"""
import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.core.config import settings
from app.core.exceptions import AppException
from app.schemas.response import ErrorResponse, ValidationErrorResponse, ErrorDetail

logger = logging.getLogger(__name__)


def add_cors_headers(response: JSONResponse, request: Request) -> None:
    """Add CORS headers to response if origin is allowed."""
    origin = request.headers.get("origin")
    if origin and origin in settings.allowed_origins_list:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"


async def app_exception_handler(request: Request, exc: AppException):
    """Handle custom application exceptions."""
    response = JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            message=exc.detail,
            error_code=exc.error_code
        ).dict()
    )
    add_cors_headers(response, request)
    return response


async def http_exception_handler(request: Request, exc):
    """Handle FastAPI HTTP exceptions."""
    response = JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            message=exc.detail,
            error_code=f"HTTP_{exc.status_code}"
        ).dict()
    )
    add_cors_headers(response, request)
    return response


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors from request parsing."""
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"])
        message = error["msg"]
        errors.append(ErrorDetail(field=field, message=message))

    response = JSONResponse(
        status_code=422,
        content=ValidationErrorResponse(errors=errors).dict()
    )
    add_cors_headers(response, request)
    return response


async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    """Handle Pydantic validation errors from internal operations."""
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"])
        message = error["msg"]
        errors.append(ErrorDetail(field=field, message=message))

    response = JSONResponse(
        status_code=422,
        content=ValidationErrorResponse(errors=errors).dict()
    )
    add_cors_headers(response, request)
    return response


async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(f"Unexpected error: {str(exc)}", exc_info=True)
    response = JSONResponse(
        status_code=500,
        content=ErrorResponse(
            message="An unexpected error occurred",
            error_code="INTERNAL_ERROR"
        ).dict()
    )
    add_cors_headers(response, request)
    return response


def register_exception_handlers(app):
    """Register all exception handlers with the FastAPI app."""
    from fastapi import HTTPException
    from fastapi.exceptions import RequestValidationError
    from pydantic import ValidationError
    from slowapi.errors import RateLimitExceeded
    
    from app.core.rate_limit import rate_limit_exceeded_handler

    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, pydantic_validation_exception_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_exception_handler(Exception, general_exception_handler)
