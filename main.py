"""
FastAPI application factory and orchestrator.
Imports modular concerns (logging, middleware, exception handlers, background tasks, endpoints)
and registers them with the FastAPI app instance.
"""
import logging

from fastapi import FastAPI
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.logging import setup_logging, log_startup_info
from app.core.middleware import setup_middleware
from app.core.handlers import register_exception_handlers
from app.core.tasks import lifespan
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from app.api import location, auth, salons, bookings, admin, rm, vendors, payments, customers, careers, upload
from app.api.health import router as health_router

# Setup logging
logger = setup_logging()

# Create FastAPI app instance with lifespan support
if settings.is_production:
    app = FastAPI(
        title=f"{settings.APP_NAME} (Production)",
        description=settings.APP_DESCRIPTION,
        version=settings.APP_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
else:
    app = FastAPI(
        title=f"{settings.APP_NAME} (Development)",
        description=settings.APP_DESCRIPTION,
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )

# Setup logging startup info
log_startup_info()

# Configure rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Setup middleware (CORS, logging, HTTPS, etc.)
setup_middleware(app)

# Register exception handlers (AppException, HTTPException, ValidationError, etc.)
register_exception_handlers(app)

# Include routers
app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(location.router, prefix=settings.API_PREFIX)
app.include_router(salons.router, prefix=settings.API_PREFIX)
app.include_router(bookings.router, prefix=settings.API_PREFIX)
app.include_router(admin.router, prefix=settings.API_PREFIX)
app.include_router(rm.router, prefix=settings.API_PREFIX)
app.include_router(vendors.router, prefix=settings.API_PREFIX)
app.include_router(payments.router, prefix=settings.API_PREFIX)
app.include_router(customers.router, prefix=settings.API_PREFIX)  # Customer portal endpoints
app.include_router(careers.router, prefix=f"{settings.API_PREFIX}/careers", tags=["Careers"])  # Career applications
app.include_router(upload.router, prefix=settings.API_PREFIX)  # File upload endpoints

# Include health check and status endpoints
app.include_router(health_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True if settings.ENVIRONMENT == "development" else False
    )
