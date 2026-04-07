"""
Middleware setup and configuration for FastAPI application.
Includes CORS, HTTPS enforcement, request logging, and rate limiting.
"""
import logging
from datetime import datetime
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import settings

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for request/response logging with performance timing."""
    
    async def dispatch(self, request: Request, call_next):
        """Log incoming request, process it, and log response with timing."""
        # Log incoming request
        logger.info(
            f"-> {request.method} {request.url.path} - "
            f"{request.client.host if request.client else 'unknown'}"
        )
        
        # Log request headers (sensitive headers excluded)
        safe_headers = {
            k: v for k, v in request.headers.items() 
            if k.lower() not in ['authorization', 'cookie', 'x-api-key']
        }
        if safe_headers:
            logger.debug(f"Request headers: {safe_headers}")
        
        start_time = datetime.utcnow()
        
        try:
            # Process the request
            response = await call_next(request)
            
            # Calculate processing time
            process_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            # Log response
            logger.info(
                f"<- {request.method} {request.url.path} - "
                f"{response.status_code} - {process_time:.2f}ms"
            )
            
            return response
            
        except Exception as e:
            # Log errors
            process_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            logger.error(
                f":( {request.method} {request.url.path} - ERROR - "
                f"{process_time:.2f}ms - {str(e)}"
            )
            raise


def setup_middleware(app):
    """Configure all middleware for the FastAPI app."""
    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add request/response logging middleware
    app.add_middleware(LoggingMiddleware)

    # Configure rate limiting
    app.add_middleware(SlowAPIMiddleware)

    # Configure HTTPS enforcement for production
    if settings.ENVIRONMENT.lower() == "production":
        logger.info("Production mode: HTTPS enforcement enabled")
        app.add_middleware(HTTPSRedirectMiddleware)
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.allowed_hosts_list
        )
    else:
        logger.info("Development mode: HTTPS enforcement disabled")
