"""
Admin API Router - Modular Sub-Routers
Combines all admin sub-routers into a single admin router
"""
from fastapi import APIRouter, Depends
from app.core.auth import require_admin
from .dashboard import router as dashboard_router
from .vendor_requests import router as vendor_requests_router
from .config import router as config_router
from .rms import router as rms_router
from .users import router as users_router
from .salons import router as salons_router
from .bookings import router as bookings_router
from .services import router as services_router
from .staff import router as staff_router

# Create the main admin router
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

# Include all sub-routers with their prefixes
router.include_router(dashboard_router, prefix="", tags=["admin-dashboard"])
router.include_router(vendor_requests_router, prefix="/vendor-requests", tags=["admin-vendor-requests"])
router.include_router(config_router, prefix="/config", tags=["admin-config"])
router.include_router(rms_router, prefix="/rms", tags=["admin-rms"])
router.include_router(users_router, prefix="/users", tags=["admin-users"])
router.include_router(salons_router, prefix="/salons", tags=["admin-salons"])
router.include_router(bookings_router, prefix="/bookings", tags=["admin-bookings"])
# Mount services and staff under explicit salon resource paths to avoid
# ambiguous mounts like multiple routers sharing the same prefix.
router.include_router(services_router, prefix="/salons/{salon_id}/services", tags=["admin-services"])
router.include_router(staff_router, prefix="/salons/{salon_id}/staff", tags=["admin-staff"])