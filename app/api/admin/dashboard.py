"""
Admin Dashboard API Endpoints
Handles admin dashboard statistics and analytics
"""
from fastapi import APIRouter, HTTPException, Depends, status
from app.core.auth import require_admin, TokenData
from app.core.database import get_db_client
from app.services.admin_service import AdminService
from supabase import Client
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def get_admin_service(db: Client = Depends(get_db_client)) -> AdminService:
    """Dependency injection for AdminService"""
    return AdminService(db_client=db)


# =====================================================
# DASHBOARD STATISTICS
# =====================================================

@router.get("/stats")
async def get_dashboard_stats(
    current_user: TokenData = Depends(require_admin),
    admin_service: AdminService = Depends(get_admin_service)
):
    """
    Get admin dashboard statistics
    - Admin only
    - Returns comprehensive system statistics
    """
    stats = await admin_service.get_dashboard_stats()

    return stats.to_dict()