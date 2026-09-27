"""
Exception handlers for FastAPI application.

CORS headers are intentionally NOT added here. CORSMiddleware is wired as the
outermost middleware in `app/core/middleware.py`, so every response — including
the ones produced by these handlers — already receives the right
Access-Control-Allow-* headers. Don't duplicate that logic here; the two
implementations will drift.
"""
import logging
import re
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from postgrest.exceptions import APIError
from pydantic import ValidationError

from app.core.exceptions import AppException
from app.core.request_context import REQUEST_ID_HEADER, get_request_id
from app.schemas.response import ErrorResponse, ValidationErrorResponse, ErrorDetail

logger = logging.getLogger(__name__)

# SQLSTATE 22P02, invalid_text_representation: what Postgres answers when a
# value cannot be parsed as the column's type -- e.g. "not-a-uuid" compared
# against a uuid column.
PG_INVALID_TEXT_REPRESENTATION = "22P02"

# SQLSTATE 23502, not_null_violation: a partial update asked to clear a column
# the schema requires. Reachable since update bodies send `null` to mean
# "clear this" (see app/schemas/request/base.py), so it is a client mistake --
# a 400 -- not a server fault.
PG_NOT_NULL_VIOLATION = "23502"

# Postgres phrases it as: null value in column "full_name" of relation
# "profiles" violates not-null constraint.
_NOT_NULL_COLUMN = re.compile(r'null value in column "([^"]+)"', re.IGNORECASE)

# Wrapper segments in a Pydantic error location; the field name is what's left.
_LOC_WRAPPERS = {"body", "query", "path", "header", "cookie"}

# Enough field names in the summary to be actionable without an unreadable toast.
_MAX_FIELDS_IN_MESSAGE = 3


def _leaf_field(loc) -> str:
    """
    "body.items.0.price" -> "price".

    The wrapper segment and list indices are plumbing; the frontends show this
    string next to an input, so it has to be the name the user can recognise.
    """
    parts = [
        str(part)
        for part in loc
        if str(part) not in _LOC_WRAPPERS and not str(part).isdigit()
    ]
    return ".".join(parts)


def _validation_message(errors: list) -> str:
    """
    A summary naming the fields that failed.

    The old flat "Validation failed" was technically accurate and completely
    useless: every client showed it as a toast with no indication of which
    input to look at. Putting the fields in `message` means even a client that
    only reads `message` -- the legacy SPA, the mobile app -- shows something
    actionable, without needing to learn the `errors[]` shape.
    """
    named = [e for e in errors if e.field]
    if not named:
        return "Validation failed"

    shown = named[:_MAX_FIELDS_IN_MESSAGE]
    summary = "; ".join(f"{e.field}: {e.message}" for e in shown)
    remaining = len(named) - len(shown)
    if remaining:
        summary += f" (and {remaining} more field{'s' if remaining > 1 else ''})"
    return summary


def _context(request: Request) -> dict:
    """Structured fields identifying the request that produced an error."""
    return {
        "request_id": getattr(request.state, "request_id", None) or get_request_id(),
        "method": request.method,
        "path": request.url.path,
    }


def _level_for(status_code: int) -> int:
    """
    Map a status code to a log level.

    404s are excluded from WARNING because crawlers and stale frontend links
    generate a constant background of them; they stay at INFO so a genuine
    spike is still visible without drowning the warning stream.
    """
    if status_code >= 500:
        return logging.ERROR
    if status_code == 404:
        return logging.INFO
    return logging.WARNING


def _error_response(status_code: int, content: dict, request: Request) -> JSONResponse:
    """Build the JSON response, echoing the correlation ID for support."""
    request_id = getattr(request.state, "request_id", None) or get_request_id()
    headers = {REQUEST_ID_HEADER: request_id} if request_id else None
    return JSONResponse(status_code=status_code, content=content, headers=headers)


async def app_exception_handler(request: Request, exc: AppException):
    """Handle custom application exceptions."""
    status_code = exc.status_code
    logger.log(
        _level_for(status_code),
        f"AppException {status_code} {exc.error_code}: {exc.detail}",
        extra={
            **_context(request),
            "status_code": status_code,
            "error_code": exc.error_code,
            "error_kind": "app_exception",
        },
        # A 5xx we raised deliberately still needs a traceback to be actionable.
        exc_info=status_code >= 500,
    )
    return _error_response(
        status_code,
        ErrorResponse(message=exc.detail, error_code=exc.error_code).dict(),
        request,
    )


async def http_exception_handler(request: Request, exc):
    """Handle FastAPI HTTP exceptions."""
    status_code = exc.status_code
    logger.log(
        _level_for(status_code),
        f"HTTPException {status_code}: {exc.detail}",
        extra={
            **_context(request),
            "status_code": status_code,
            "error_code": f"HTTP_{status_code}",
            "error_kind": "http_exception",
        },
        exc_info=status_code >= 500,
    )
    return _error_response(
        status_code,
        ErrorResponse(message=exc.detail, error_code=f"HTTP_{status_code}").dict(),
        request,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors from request parsing."""
    errors = [
        ErrorDetail(field=_leaf_field(error["loc"]), message=error["msg"])
        for error in exc.errors()
    ]
    # 422s are how a client/server contract mismatch shows up. Logging the
    # offending fields turns "the form stopped working" into a one-line answer.
    logger.warning(
        f"Request validation failed on {request.method} {request.url.path}",
        extra={
            **_context(request),
            "status_code": 422,
            "error_kind": "request_validation",
            "invalid_fields": [e.field for e in errors],
        },
    )
    return _error_response(
        422,
        ValidationErrorResponse(
            message=_validation_message(errors), errors=errors
        ).dict(),
        request,
    )


async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    """Handle Pydantic validation errors from internal operations."""
    errors = [
        ErrorDetail(field=_leaf_field(error["loc"]), message=error["msg"])
        for error in exc.errors()
    ]
    # Unlike the request-parsing case above, this means our own code built an
    # invalid model -- a backend bug, so it is logged at ERROR with a traceback.
    logger.error(
        f"Internal validation error on {request.method} {request.url.path}",
        extra={
            **_context(request),
            "status_code": 422,
            "error_kind": "internal_validation",
            "invalid_fields": [e.field for e in errors],
        },
        exc_info=True,
    )
    return _error_response(
        422, ValidationErrorResponse(errors=errors).dict(), request
    )


async def invalid_identifier_response(request: Request, exc) -> JSONResponse:
    """
    Turn Postgres 22P02 ("invalid input syntax for type uuid") into a 400.

    This is a backstop, not the fix. Malformed ids are rejected declaratively at
    the routing layer by the types in `app.core.validators`, before any query
    runs. But an id can still reach Postgres from somewhere with no such
    declaration -- a webhook payload, a stored reference, a route added later
    without `UUIDPath`. Without this, any of those is a 500 on a public
    endpoint, which is what docs/INCIDENT_salon_id_500.md was about.

    It only catches what reaches here uncaught. A service that wraps the call in
    `except Exception` and raises its own HTTPException(500) still returns 500 --
    this does not reach inside those. The routing-layer types are what actually
    close the hole; `test_uuid_validation.py::test_every_id_path_param_is_uuid_validated`
    is what keeps them in place as routes are added.

    It answers 400 rather than the 422 the routing layer returns, deliberately:
    the two are not the same event. A 422 is the contract working. An
    INVALID_IDENTIFIER 400 means a value got past every declared check, so it
    marks a validation gap worth finding -- hence the distinct error_code and
    error_kind to alert on.
    """
    logger.warning(
        f"Malformed identifier reached the database on {request.method} {request.url.path}: {exc}",
        extra={
            **_context(request),
            "status_code": 400,
            "error_code": "INVALID_IDENTIFIER",
            "error_kind": "invalid_identifier",
            "pg_code": getattr(exc, "code", None),
        },
    )
    return _error_response(
        400,
        ErrorResponse(
            message="One of the identifiers in this request is not a valid ID.",
            error_code="INVALID_IDENTIFIER",
        ).dict(),
        request,
    )


async def required_field_cleared_response(request: Request, exc) -> JSONResponse:
    """
    Turn Postgres 23502 into a 400 that names the column.

    An update body sends `null` to clear a field. For a column the schema
    requires that is a client mistake, and the useful answer says which field
    it was -- not "An unexpected error occurred".
    """
    match = _NOT_NULL_COLUMN.search(str(getattr(exc, "message", "") or exc))
    column = match.group(1) if match else None
    message = (
        f"'{column}' is required and cannot be cleared."
        if column
        else "A required field was left empty."
    )
    logger.warning(
        f"Not-null violation on {request.method} {request.url.path}: {exc}",
        extra={
            **_context(request),
            "status_code": 400,
            "error_code": "REQUIRED_FIELD",
            "error_kind": "required_field_cleared",
            "pg_code": getattr(exc, "code", None),
            "invalid_fields": [column] if column else [],
        },
    )
    return _error_response(
        400,
        ErrorResponse(
            message=message,
            errors=[message],
            error_code="REQUIRED_FIELD",
        ).dict(),
        request,
    )


async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    if isinstance(exc, APIError):
        pg_code = getattr(exc, "code", None)
        if pg_code == PG_INVALID_TEXT_REPRESENTATION:
            return await invalid_identifier_response(request, exc)
        if pg_code == PG_NOT_NULL_VIOLATION:
            return await required_field_cleared_response(request, exc)

    logger.error(
        f"Unhandled {type(exc).__name__} on {request.method} {request.url.path}: {exc}",
        extra={
            **_context(request),
            "status_code": 500,
            "error_kind": "unhandled",
            "exception_type": type(exc).__name__,
        },
        exc_info=True,
    )
    return _error_response(
        500,
        ErrorResponse(
            message="An unexpected error occurred", error_code="INTERNAL_ERROR"
        ).dict(),
        request,
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
