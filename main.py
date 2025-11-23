import logging
import sys
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, status, Depends
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from dotenv import load_dotenv

# Load environment variables from .env file BEFORE importing settings
load_dotenv(encoding='utf-8')

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.database import get_db, get_db_client, get_auth_client, MockSupabaseClient
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from supabase import Client
from app.schemas.response import ErrorResponse, ValidationErrorResponse, ErrorDetail
from app.api import location, auth, salons, bookings, realtime, admin, rm, vendors, payments, customers, careers, upload

# Import test email router (only for dev/staging)
if settings.ENVIRONMENT.lower() != "production":
    from app.api import test_email

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Get logger for this module
logger = logging.getLogger(__name__)

# Request/Response logging middleware
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Log incoming request
        logger.info(f"→ {request.method} {request.url.path} - {request.client.host if request.client else 'unknown'}")
        
        # Log request headers (sensitive headers excluded)
        safe_headers = {k: v for k, v in request.headers.items() 
                       if k.lower() not in ['authorization', 'cookie', 'x-api-key']}
        if safe_headers:
            logger.debug(f"Request headers: {safe_headers}")
        
        start_time = datetime.utcnow()
        
        try:
            # Process the request
            response = await call_next(request)
            
            # Calculate processing time
            process_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            # Log response
            logger.info(f"← {request.method} {request.url.path} - {response.status_code} - {process_time:.2f}ms")
            
            return response
            
        except Exception as e:
            # Log errors
            process_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            logger.error(f"✗ {request.method} {request.url.path} - ERROR - {process_time:.2f}ms - {str(e)}")
            raise

# Log configuration on startup (avoid printing secrets)
logger.info("="*60)
logger.info("Starting Salon Management API")
logger.info(f"Environment: {settings.ENVIRONMENT}")
try:
    # Mask Supabase URL in logs to avoid leaking secrets
    supabase_host = settings.SUPABASE_URL.split("//")[-1].split("@")[-1] if settings.SUPABASE_URL else "(not configured)"
except Exception:
    supabase_host = "(redacted)"
logger.info(f"Supabase configured: {bool(settings.SUPABASE_URL)} (host={supabase_host})")
logger.info("="*60)

# Create FastAPI app
if settings.is_production:
    app = FastAPI(
        title="Salon Management API - Complete Restructure",
        description="Multi-role salon management with RM scoring, dynamic fees, and Razorpay integration",
        version="3.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
else:
    app = FastAPI(
        title="Salon Management API - Complete Restructure",
        description="Multi-role salon management with RM scoring, dynamic fees, and Razorpay integration",
        version="3.0.0"
    )

logger.info("🚀 Salon Management API starting up...")
logger.info(f"📧 Email sending: {'ENABLED' if settings.EMAIL_ENABLED else 'DISABLED (Dev Mode)'}")

# Configure rate limiting (using centralized rate_limit module)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

logger.info(f"🛡️ Rate limiting enabled: {settings.RATE_LIMIT_PER_MINUTE}/minute per IP (global default)")
logger.info("🛡️ Auth endpoints have stricter limits (5 login, 3 signup, 3 password reset)")


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

# Configure HTTPS enforcement for production
if settings.ENVIRONMENT.lower() == "production":
    logger.info("🔒 Production mode: Enabling HTTPS enforcement")
    app.add_middleware(HTTPSRedirectMiddleware)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.ALLOWED_HOSTS
    )
else:
    logger.info("🔓 Development mode: HTTPS enforcement disabled")


# =====================================================
# BACKGROUND TASKS
# =====================================================

async def cleanup_expired_tokens_task():
    """Background task to cleanup expired tokens periodically"""
    from app.core.auth import cleanup_expired_tokens
    from app.core.database import get_db
    import asyncio
    
    db = get_db()
    while True:
        try:
            logger.info("🧹 Running scheduled token cleanup...")
            cleaned_count = cleanup_expired_tokens(db)
            if cleaned_count > 0:
                logger.info(f"🗑️ Cleaned up {cleaned_count} expired tokens")
            else:
                logger.debug("No expired tokens to clean up")
        except Exception as e:
            logger.error(f"Token cleanup task error: {str(e)}")
        
        # Run every 6 hours
        await asyncio.sleep(6 * 60 * 60)

@app.on_event("startup")
async def startup_event():
    """Application startup tasks"""
    logger.info("🚀 Starting background tasks...")
    
    # Start token cleanup task
    import asyncio
    # Keep a reference to the task so it can be cancelled on shutdown
    app.state.cleanup_task = asyncio.create_task(cleanup_expired_tokens_task())
    
    logger.info("✅ Background tasks started")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown tasks - cancel background tasks gracefully"""
    import asyncio
    logger.info("🛑 Shutting down background tasks...")
    task = getattr(app.state, "cleanup_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            logger.info("Cleanup task cancelled")
        except Exception as e:
            logger.error(f"Error while cancelling cleanup task: {e}")


# =====================================================
# GLOBAL EXCEPTION HANDLERS
# =====================================================

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """Handle custom application exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            message=exc.detail,
            error_code=exc.error_code
        ).dict()
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle FastAPI HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            message=exc.detail,
            error_code=f"HTTP_{exc.status_code}"
        ).dict()
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors"""
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"])
        message = error["msg"]
        errors.append(ErrorDetail(field=field, message=message))

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ValidationErrorResponse(errors=errors).dict()
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    """Handle Pydantic validation errors from internal operations"""
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"])
        message = error["msg"]
        errors.append(ErrorDetail(field=field, message=message))

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ValidationErrorResponse(errors=errors).dict()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions"""
    logger.error(f"Unexpected error: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            message="An unexpected error occurred",
            error_code="INTERNAL_ERROR"
        ).dict()
    )


# Include routers
app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(location.router, prefix=settings.API_PREFIX)
app.include_router(salons.router, prefix=settings.API_PREFIX)
app.include_router(bookings.router, prefix=settings.API_PREFIX)
app.include_router(realtime.router, prefix=settings.API_PREFIX)

# New routers for restructured system
app.include_router(admin.router, prefix=settings.API_PREFIX)
app.include_router(rm.router, prefix=settings.API_PREFIX)
app.include_router(vendors.router, prefix=settings.API_PREFIX)
app.include_router(payments.router, prefix=settings.API_PREFIX)
app.include_router(customers.router, prefix=settings.API_PREFIX)  # Customer portal endpoints
app.include_router(careers.router, prefix=f"{settings.API_PREFIX}/careers", tags=["Careers"])  # Career applications
app.include_router(upload.router, prefix=settings.API_PREFIX)  # File upload endpoints

# Include test email router (only for dev/staging)
if settings.ENVIRONMENT.lower() != "production":
    app.include_router(test_email.router, prefix=settings.API_PREFIX)
    logger.info("🧪 Test email endpoint enabled (dev/staging mode)")



@app.get("/")
async def root():
    base = {
        "message": "Salon Management API - Complete Restructure",
        "version": "3.0.0",
        "api_version": "v1",
        "base_url": settings.API_PREFIX,
        "status": "running",
        "roles": ["admin", "relationship_manager", "vendor", "customer"],
    }

    # Do not advertise docs or health endpoints in production
    if not settings.is_production:
        base.update({
            "docs": "/docs",
            "health": "/health"
        })

    return base


@app.get("/health")
async def health_check(db_client: Client = Depends(get_db_client), auth_client: Client = Depends(get_auth_client)):
    """
    Comprehensive health check for all dependencies
    """
    # In production return minimal public health info to avoid leaking configuration
    minimal_status = {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

    try:
        if settings.is_production:
            # Perform lightweight checks but do NOT expose details

            # If DB or Auth clients are mocked or missing, mark unhealthy
            if isinstance(db_client, MockSupabaseClient) or isinstance(auth_client, MockSupabaseClient):
                minimal_status["status"] = "unhealthy"

            return minimal_status

        # Non-production: return detailed checks for debugging
        health_status = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {}
        }

        # Check Supabase Database connection
        health_status["checks"]["database"] = {
            "status": "warning" if isinstance(db_client, MockSupabaseClient) else "healthy"
        }

        # Check Supabase Auth connection
        health_status["checks"]["auth"] = {
            "status": "warning" if isinstance(auth_client, MockSupabaseClient) else "healthy"
        }

        # Check Email configuration
        if settings.EMAIL_ENABLED:
            health_status["checks"]["email"] = {
                "status": "healthy" if (settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD) else "warning"
            }
        else:
            health_status["checks"]["email"] = {"status": "info"}

        # Check Payment gateway configuration
        health_status["checks"]["payment"] = {
            "status": "healthy" if (settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET) else "warning"
        }

        return health_status

    except Exception:
        # On unexpected errors, avoid returning internals
        return {"status": "unhealthy", "timestamp": datetime.utcnow().isoformat()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True if settings.ENVIRONMENT == "development" else False
    )
