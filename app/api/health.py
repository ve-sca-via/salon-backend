"""
Health check and root endpoints for the API.
Provides diagnostic information about service health and status.
"""
import logging
from datetime import datetime

from fastapi import APIRouter, status

from app.core.config import settings


logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health & Status"])


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """
    Health check endpoint. Returns detailed diagnostics in development,
    minimal response in production to avoid information disclosure.
    """
    health_data = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
    }

    if settings.is_development:
        # Detailed diagnostics in development
        health_data.update({
            "environment": settings.ENVIRONMENT,
            "version": settings.APP_VERSION,
            "debug": True,
        })
    else:
        # Minimal response in production
        health_data["debug"] = False

    return health_data


@router.get("/", status_code=status.HTTP_200_OK)
async def root():
    """
    Root endpoint. Returns basic API information.
    """
    return {
        "message": "Welcome to Salon Management API",
        "version": settings.APP_VERSION,
        "docs": "/docs",
    }
