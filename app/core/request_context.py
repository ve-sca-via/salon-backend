"""
Request-scoped context shared by middleware, logging and exception handlers.

A correlation ID is attached to every request so that all log lines produced
while serving it can be tied back together in Better Stack. The ID lives in a
ContextVar rather than on `request.state` alone, so code deep in the service
layer can log with the right ID without having the Request threaded through it.
"""
from contextvars import ContextVar, Token

REQUEST_ID_HEADER = "X-Request-ID"

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def set_request_id(value: str) -> Token:
    """Bind a request ID to the current context. Returns a token for reset()."""
    return _request_id.set(value)


def get_request_id() -> str | None:
    """Current request's correlation ID, or None outside a request."""
    return _request_id.get()


def reset_request_id(token: Token) -> None:
    """Restore the previous context value. Always call this in a `finally`."""
    _request_id.reset(token)
