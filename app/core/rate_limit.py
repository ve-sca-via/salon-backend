"""
Rate Limiting Configuration

Provides rate limiting for API endpoints to prevent brute-force attacks
and abuse. Uses SlowAPI (a rate-limiting library for FastAPI).

Usage:
    from app.core.rate_limit import limiter
    
    @router.post("/login")
    @limiter.limit("5/minute")  # Max 5 requests per minute
    async def login(...):
        pass
"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request, Response
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)

# Initialize limiter
# Uses client IP address as the key for rate limiting
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],  # Global default: 100 requests/minute
    storage_uri="memory://",  # In-memory storage (use Redis in production for distributed systems)
    strategy="fixed-window"  # Fixed time window strategy
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Custom handler for rate limit exceeded errors
    
    Returns a JSON response with 429 status code
    """
    logger.warning(
        f"Rate limit exceeded for {get_remote_address(request)} "
        f"on {request.method} {request.url.path}"
    )
    
    return JSONResponse(
        status_code=429,
        content={
            "success": False,
            "error": "rate_limit_exceeded",
            "message": "Too many requests. Please try again later.",
            "detail": str(exc.detail)
        }
    )


# Rate limit configurations for different endpoint types
class RateLimits:
    """Predefined rate limits for common endpoint types"""
    
    # Authentication endpoints (prevent brute-force)
    AUTH_LOGIN = "5/minute"           # Max 5 login attempts per minute
    AUTH_SIGNUP = "3/minute"          # Max 3 signups per minute
    AUTH_PASSWORD_RESET = "3/hour"    # Max 3 password resets per hour
    AUTH_REFRESH = "10/minute"        # Max 10 token refreshes per minute
    
    # Sensitive operations
    PAYMENT_CREATE = "10/minute"      # Max 10 payment creations per minute
    BOOKING_CREATE = "20/minute"      # Max 20 bookings per minute
    FILE_UPLOAD = "10/minute"         # Max 10 file uploads per minute
    
    # Read operations (more lenient)
    READ_HEAVY = "60/minute"          # For list/search endpoints
    READ_LIGHT = "100/minute"         # For single item fetches
    
    # Public endpoints
    PUBLIC_API = "30/minute"          # For unauthenticated public access


# Example usage decorators
"""
# In your route file:
from app.core.rate_limit import limiter, RateLimits

@router.post("/auth/login")
@limiter.limit(RateLimits.AUTH_LOGIN)
async def login(credentials: LoginRequest):
    # Login logic here
    pass

@router.post("/bookings")
@limiter.limit(RateLimits.BOOKING_CREATE)
async def create_booking(booking: BookingCreate):
    # Booking logic here
    pass

# Or use custom limits:
@router.get("/expensive-operation")
@limiter.limit("5/hour")  # Very restrictive
async def expensive_operation():
    pass
"""
