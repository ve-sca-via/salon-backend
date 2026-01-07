"""
Admin Dashboard API Endpoints
Handles admin dashboard statistics and analytics
"""
from fastapi import APIRouter, HTTPException, Depends, status
from app.core.auth import require_admin, TokenData
from app.core.database import get_db_client
from app.services.admin_service import AdminService
from app.services.activity_log_service import ActivityLogService
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


@router.get("/recent-activity")
async def get_recent_activity(
    limit: int = 10,
    current_user: TokenData = Depends(require_admin)
):
    """
    Get recent activity logs for dashboard
    - Admin only
    - Returns last N activity logs with user details
    """
    activities = await ActivityLogService.get_recent(limit=limit)
    
    return {
        "success": True,
        "data": activities,
        "count": len(activities)
    }