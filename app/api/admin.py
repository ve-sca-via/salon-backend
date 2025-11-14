"""
Admin API Endpoints
Handles vendor request approvals, system configuration, and RM management
"""
from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional
from app.core.config import settings
from app.core.database import get_db
from app.core.auth import require_admin, TokenData, create_registration_token

# Get database client using factory function
db = get_db()
from app.schemas import (
    VendorJoinRequestResponse,
    VendorJoinRequestUpdate,
    VendorApprovalRequest,
    VendorRejectionRequest,
    SystemConfigResponse,
    SystemConfigUpdate,
    RMProfileResponse,
    RMScoreHistoryResponse,
    SuccessResponse
)
from app.services.email import email_service
from app.services.geocoding import geocoding_service
# Import service layer
from app.services.user_service import UserService, CreateUserRequest
from app.services.vendor_approval_service import VendorApprovalService
from app.services.rm_service import RMService
from app.services.salon_service import SalonService, SalonSearchParams, NearbySearchParams
from app.services.admin_service import AdminService
from app.services.config_service import ConfigService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


# =====================================================
# DASHBOARD STATISTICS
# =====================================================

@router.get("/dashboard/stats")
async def get_dashboard_stats(
    current_user: TokenData = Depends(require_admin)
):
    """
    Get admin dashboard statistics
    - Admin only
    - Returns comprehensive system statistics
    """
    try:
        admin_service = AdminService()
        stats = await admin_service.get_dashboard_stats()
        
        return stats.to_dict()
    
    except Exception as e:
        logger.error(f"Failed to fetch dashboard stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch dashboard stats: {str(e)}"
        )


# =====================================================
# VENDOR REQUEST MANAGEMENT
# =====================================================

@router.get("/vendor-requests", response_model=List[VendorJoinRequestResponse])
async def get_vendor_requests(
    status_filter: Optional[str] = "pending",
    limit: int = 50,
    offset: int = 0,
    current_user: TokenData = Depends(require_admin)
):
    """
    Get vendor join requests
    - Admin only
    - Filter by status: pending, approved, rejected
    """
    try:
        admin_service = AdminService()
        requests = await admin_service.get_vendor_requests(
            status_filter=status_filter,
            limit=limit,
            offset=offset
        )
        
        return requests
    
    except Exception as e:
        logger.error(f"Failed to fetch vendor requests: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch vendor requests: {str(e)}"
        )


@router.get("/vendor-requests/{request_id}", response_model=VendorJoinRequestResponse)
async def get_vendor_request(
    request_id: str,
    current_user: TokenData = Depends(require_admin)
):
    """Get specific vendor request details"""
    try:
        admin_service = AdminService()
        request = await admin_service.get_vendor_request(request_id)
        
        return request
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch vendor request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch vendor request"
        )


@router.post("/vendor-requests/{request_id}/approve")
async def approve_vendor_request(
    request_id: str,
    request_body: VendorApprovalRequest,
    current_user: TokenData = Depends(require_admin)
):
    """
    Approve vendor join request
    - Creates salon entry
    - Updates RM score
    - Sends email to vendor with registration link
    """
    try:
        logger.info(f"🔍 Admin {current_user.user_id} approving vendor request: {request_id}")
        logger.info(f"📝 Admin notes: {request_body.admin_notes}")
        
        # Use service layer for approval
        approval_service = VendorApprovalService()
        result = await approval_service.approve_vendor_request(
            request_id=request_id,
            admin_notes=request_body.admin_notes,
            admin_id=current_user.user_id
        )
        
        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.error
            )
        
        # Log warnings if any
        if result.warnings:
            for warning in result.warnings:
                logger.warning(f"⚠️ {warning}")
        
        return {
            "success": True,
            "message": "Vendor request approved successfully",
            "data": {
                "salon_id": result.salon_id,
                "rm_score_awarded": result.rm_score_awarded,
                "warnings": result.warnings
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to approve vendor request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to approve vendor request"
        )


@router.post("/vendor-requests/{request_id}/reject")
async def reject_vendor_request(
    request_id: str,
    request_body: VendorRejectionRequest,
    current_user: TokenData = Depends(require_admin)
):
    """
    Reject vendor join request
    - Updates status
    - Sends rejection email
    """
    try:
        logger.info(f"🚫 Admin {current_user.user_id} rejecting vendor request: {request_id}")
        logger.info(f"📝 Rejection reason: {request_body.admin_notes}")
        
        # Use service layer for rejection
        approval_service = VendorApprovalService()
        result = await approval_service.reject_vendor_request(
            request_id=request_id,
            admin_notes=request_body.admin_notes,
            admin_id=current_user.user_id
        )
        
        return result
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reject vendor request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reject vendor request"
        )


# =====================================================
# SYSTEM CONFIGURATION MANAGEMENT
# =====================================================

@router.get("/config", response_model=List[SystemConfigResponse])
async def get_all_configs(current_user: TokenData = Depends(require_admin)):
    """Get all system configurations"""
    try:
        config_service = ConfigService()
        configs = await config_service.get_all_configs()
        
        return configs
    
    except Exception as e:
        logger.error(f"Failed to fetch configs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch configurations"
        )


@router.get("/config/{config_key}", response_model=SystemConfigResponse)
async def get_config(
    config_key: str,
    current_user: TokenData = Depends(require_admin)
):
    """Get specific configuration"""
    try:
        config_service = ConfigService()
        config = await config_service.get_config(config_key)
        
        return config
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch config: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch configuration"
        )


@router.put("/config/{config_key}")
async def update_config(
    config_key: str,
    update: SystemConfigUpdate,
    current_user: TokenData = Depends(require_admin)
):
    """Update system configuration"""
    try:
        config_service = ConfigService()
        
        # Prepare update data
        update_data = update.model_dump(exclude_unset=True)
        
        # Update config
        updated_config = await config_service.update_config(config_key, update_data)
        
        logger.info(f"System config updated: {config_key} = {update.config_value}")
        
        return {
            "success": True,
            "message": "Configuration updated successfully",
            "data": updated_config
        }
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update config: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update configuration"
        )


# =====================================================
# RM MANAGEMENT
# =====================================================

@router.get("/rms", response_model=List[RMProfileResponse])
async def get_all_rms(
    is_active: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
    order_by: str = "total_score",
    order_desc: bool = True,
    current_user: TokenData = Depends(require_admin)
):
    """Get all Relationship Managers"""
    try:
        # Use service layer for RM listing
        rm_service = RMService()
        
        rms = await rm_service.list_rm_profiles(
            limit=limit,
            offset=offset,
            order_by=order_by,
            order_desc=order_desc
        )
        
        # Apply active filter if specified
        if is_active is not None:
            rms = [rm for rm in rms if rm.get("profiles", {}).get("is_active") == is_active]
        
        return rms
    
    except Exception as e:
        logger.error(f"Failed to fetch RMs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch RM profiles"
        )


@router.get("/rms/{rm_id}", response_model=RMProfileResponse)
async def get_rm_profile(
    rm_id: str,
    current_user: TokenData = Depends(require_admin)
):
    """Get specific RM profile"""
    try:
        # Use service layer
        rm_service = RMService()
        rm_profile = await rm_service.get_rm_profile(rm_id)
        
        return rm_profile
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch RM profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch RM profile"
        )


@router.get("/rms/{rm_id}/score-history", response_model=List[RMScoreHistoryResponse])
async def get_rm_score_history(
    rm_id: str,
    limit: int = 50,
    current_user: TokenData = Depends(require_admin)
):
    """Get RM score history"""
    try:
        # Use service layer
        rm_service = RMService()
        history = await rm_service.get_rm_score_history(rm_id, limit=limit)
        
        return history
    
    except Exception as e:
        logger.error(f"Failed to fetch score history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch score history"
        )


# =====================================================
# USER MANAGEMENT
# =====================================================

@router.get("/users")
async def get_all_users(
    page: int = 1,
    limit: int = 20,
    search: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    current_user: TokenData = Depends(require_admin)
):
    """Get all users with pagination and filters"""
    try:
        user_service = UserService()
        result = await user_service.list_users(
            page=page,
            limit=limit,
            search=search,
            role=role,
            is_active=is_active
        )
        
        return result
    
    except Exception as e:
        logger.error(f"Failed to fetch users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch users"
        )


@router.post("/users")
async def create_user(
    user_data: dict,
    current_user: TokenData = Depends(require_admin)
):
    """Create a new user (Relationship Manager or Customer only)"""
    try:
        # Validate required fields
        email = user_data.get("email")
        password = user_data.get("password")
        full_name = user_data.get("full_name")
        phone = user_data.get("phone", "")
        role = user_data.get("role", "customer")
        
        if not email or not full_name or not password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email, full name, and password are required"
            )
        
        # Prevent creating admin users
        if role not in ["relationship_manager", "customer"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only create Relationship Manager or Customer accounts"
            )
        
        # Use service layer for user creation
        user_service = UserService()
        
        request = CreateUserRequest(
            email=email,
            full_name=full_name,
            role=role,
            password=password,
            phone=phone
        )
        
        result = await user_service.create_user(request)
        
        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.error
            )
        
        logger.info(f"User created by admin {current_user.user_id}: {email} ({role})")
        
        return {
            "success": True,
            "message": f"{role.replace('_', ' ').title()} created successfully!",
            "data": {
                "user_id": result.user_id,
                "employee_id": result.employee_id,
                "email": email,
                "role": role
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create user: {str(e)}"
        )


@router.put("/users/{user_id}")
async def update_user(
    user_id: str,
    updates: dict,
    current_user: TokenData = Depends(require_admin)
):
    """Update user profile"""
    try:
        user_service = UserService()
        result = await user_service.update_user(user_id, updates)
        
        return result
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user"
        )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: TokenData = Depends(require_admin)
):
    """Delete user (soft delete by setting is_active=false)"""
    try:
        # Use service layer for user deletion
        user_service = UserService()
        
        result = await user_service.delete_user(user_id)
        
        return {
            "success": True,
            "message": "User deleted successfully",
            "data": result
        }
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user"
        )


# =====================================================
# SALON MANAGEMENT
# =====================================================

@router.get("/salons")
async def get_all_salons_admin(
    current_user: TokenData = Depends(require_admin),
    city: Optional[str] = None,
    state: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_verified: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0
):
    """Get all salons with optional filtering"""
    try:
        # Use service layer for salon listing
        salon_service = SalonService()
        
        params = SalonSearchParams(
            city=city,
            state=state,
            is_active=is_active,
            is_verified=is_verified,
            limit=limit,
            offset=offset
        )
        
        salons = await salon_service.list_salons(params)
        
        return {
            "success": True,
            "data": salons,
            "count": len(salons)
        }
    
    except Exception as e:
        logger.error(f"Failed to fetch salons: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch salons"
        )


@router.put("/salons/{salon_id}")
async def update_salon(
    salon_id: str,
    updates: dict,
    current_user: TokenData = Depends(require_admin)
):
    """Update salon (protected fields excluded)"""
    try:
        # Use service layer for safe updates
        salon_service = SalonService()
        
        updated_salon = await salon_service.update_salon(
            salon_id=salon_id,
            updates=updates,
            admin_id=current_user.user_id
        )
        
        return {
            "success": True,
            "message": "Salon updated successfully",
            "data": updated_salon
        }
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update salon: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update salon"
        )


@router.delete("/salons/{salon_id}")
async def delete_salon(
    salon_id: str,
    hard_delete: bool = False,
    current_user: TokenData = Depends(require_admin)
):
    """Delete salon (soft delete by default, hard delete if specified)"""
    try:
        # Use service layer for deletion
        salon_service = SalonService()
        
        result = await salon_service.delete_salon(
            salon_id=salon_id,
            hard_delete=hard_delete
        )
        
        return {
            "success": True,
            "message": result.get("message", "Salon deleted successfully"),
            "data": result
        }
    
    except Exception as e:
        logger.error(f"Failed to delete salon: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete salon"
        )


@router.put("/salons/{salon_id}/status")
async def toggle_salon_status(
    salon_id: str,
    request_body: dict,
    current_user: TokenData = Depends(require_admin)
):
    """Toggle salon active/inactive status"""
    try:
        is_active = request_body.get("is_active")
        if is_active is None:
            raise ValueError("is_active field is required")
        
        salon_service = SalonService()
        
        updated_salon = await salon_service.update_salon(
            salon_id=salon_id,
            updates={"is_active": is_active},
            admin_id=current_user.user_id
        )
        
        return {
            "success": True,
            "message": f"Salon {'activated' if is_active else 'deactivated'} successfully",
            "data": updated_salon
        }
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to toggle salon status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to toggle salon status"
        )


# =====================================================
# BOOKINGS/APPOINTMENTS MANAGEMENT
# =====================================================

@router.get("/bookings")
async def get_all_bookings_admin(
    page: int = 1,
    limit: int = 20,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: TokenData = Depends(require_admin)
):
    """Get all bookings with filters"""
    try:
        from app.services.booking_service import BookingService
        
        booking_service = BookingService()
        result = await booking_service.get_admin_bookings(
            page=page,
            limit=limit,
            status_filter=status,
            date_from=date_from,
            date_to=date_to
        )
        
        return result
    
    except Exception as e:
        logger.error(f"Failed to fetch bookings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch bookings"
        )


@router.put("/bookings/{booking_id}/status")
async def update_booking_status(
    booking_id: str,
    status: str,
    current_user: TokenData = Depends(require_admin)
):
    """Update booking status"""
    try:
        from app.services.booking_service import BookingService
        
        booking_service = BookingService()
        result = await booking_service.update_booking_status_admin(
            booking_id=booking_id,
            new_status=status
        )
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update booking: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update booking"
        )


# =====================================================
# SERVICES MANAGEMENT
# =====================================================

@router.get("/services")
async def get_all_services_admin(
    current_user: TokenData = Depends(require_admin)
):
    """Get all services"""
    try:
        admin_service = AdminService()
        services = await admin_service.get_all_services()
        
        return {
            "success": True,
            "data": services
        }
    
    except Exception as e:
        logger.error(f"Failed to fetch services: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch services"
        )


@router.post("/services")
async def create_service(
    service_data: dict,
    current_user: TokenData = Depends(require_admin)
):
    """Create new service"""
    try:
        admin_service = AdminService()
        service = await admin_service.create_service(service_data)
        
        return {
            "success": True,
            "message": "Service created successfully",
            "data": service
        }
    
    except Exception as e:
        logger.error(f"Failed to create service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create service"
        )


@router.put("/services/{service_id}")
async def update_service(
    service_id: str,
    updates: dict,
    current_user: TokenData = Depends(require_admin)
):
    """Update service"""
    try:
        admin_service = AdminService()
        service = await admin_service.update_service(service_id, updates)
        
        return {
            "success": True,
            "message": "Service updated successfully",
            "data": service
        }
    
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found"
            )
        logger.error(f"Failed to update service: {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update service"
        )


@router.delete("/services/{service_id}")
async def delete_service(
    service_id: str,
    current_user: TokenData = Depends(require_admin)
):
    """Delete service"""
    try:
        admin_service = AdminService()
        await admin_service.delete_service(service_id)
        
        return {
            "success": True,
            "message": "Service deleted successfully"
        }
    
    except Exception as e:
        logger.error(f"Failed to delete service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete service"
        )


# =====================================================
# STAFF MANAGEMENT
# =====================================================

@router.get("/staff")
async def get_all_staff(
    current_user: TokenData = Depends(require_admin)
):
    """Get all staff members"""
    try:
        admin_service = AdminService()
        staff = await admin_service.get_all_staff()
        
        return {
            "success": True,
            "data": staff
        }
    
    except Exception as e:
        logger.error(f"Failed to fetch staff: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch staff"
        )


@router.put("/staff/{staff_id}")
async def update_staff(
    staff_id: str,
    updates: dict,
    current_user: TokenData = Depends(require_admin)
):
    """Update staff member"""
    try:
        admin_service = AdminService()
        staff = await admin_service.update_staff(staff_id, updates)
        
        return {
            "success": True,
            "message": "Staff updated successfully",
            "data": staff
        }
    
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Staff member not found"
            )
        logger.error(f"Failed to update staff: {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update staff"
        )


@router.delete("/staff/{staff_id}")
async def delete_staff(
    staff_id: str,
    current_user: TokenData = Depends(require_admin)
):
    """Delete staff member (soft delete)"""
    try:
        admin_service = AdminService()
        staff = await admin_service.delete_staff(staff_id)
        
        return {
            "success": True,
            "message": "Staff deleted successfully",
            "data": staff
        }
    
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Staff member not found"
            )
        logger.error(f"Failed to delete staff: {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete staff"
        )
        
        return {
            "success": True,
            "message": "Staff deleted successfully"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete staff: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete staff"
        )


# =====================================================
# ADDITIONAL SERVICE-POWERED ENDPOINTS
# =====================================================

@router.get("/rms/{rm_id}/stats")
async def get_rm_stats(
    rm_id: str,
    current_user: TokenData = Depends(require_admin)
):
    """Get comprehensive statistics for an RM"""
    try:
        rm_service = RMService()
        stats = await rm_service.get_rm_stats(rm_id)
        
        return {
            "success": True,
            "data": {
                "total_requests": stats.total_requests,
                "pending_requests": stats.pending_requests,
                "approved_requests": stats.approved_requests,
                "rejected_requests": stats.rejected_requests,
                "total_score": stats.total_score
            }
        }
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to fetch RM stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch RM stats"
        )


@router.get("/rms/leaderboard")
async def get_rm_leaderboard(
    limit: int = 10,
    current_user: TokenData = Depends(require_admin)
):
    """Get RM leaderboard by total score"""
    try:
        rm_service = RMService()
        leaderboard = await rm_service.get_leaderboard(limit=limit)
        
        return {
            "success": True,
            "data": leaderboard
        }
    
    except Exception as e:
        logger.error(f"Failed to fetch RM leaderboard: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch RM leaderboard"
        )


@router.patch("/rms/{rm_id}/score")
async def update_rm_score(
    rm_id: str,
    score_change: int,
    reason: str,
    salon_id: Optional[str] = None,
    current_user: TokenData = Depends(require_admin)
):
    """Update RM score (add or subtract points)"""
    try:
        rm_service = RMService()
        result = await rm_service.update_rm_score(
            rm_id=rm_id,
            score_change=score_change,
            reason=reason,
            salon_id=salon_id,
            admin_id=current_user.user_id
        )
        
        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.error
            )
        
        return {
            "success": True,
            "message": "RM score updated successfully",
            "data": {
                "new_total_score": result.new_total_score,
                "score_change": result.score_change
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update RM score: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update RM score"
        )


@router.get("/salons/{salon_id}/stats")
async def get_salon_stats(
    salon_id: str,
    current_user: TokenData = Depends(require_admin)
):
    """Get comprehensive statistics for a salon"""
    try:
        salon_service = SalonService()
        stats = await salon_service.get_salon_stats(salon_id)
        
        return {
            "success": True,
            "data": stats
        }
    
    except Exception as e:
        logger.error(f"Failed to fetch salon stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch salon stats"
        )


@router.post("/salons/{salon_id}/activate")
async def activate_salon(
    salon_id: str,
    current_user: TokenData = Depends(require_admin)
):
    """Activate a salon"""
    try:
        salon_service = SalonService()
        salon = await salon_service.activate_salon(salon_id)
        
        return {
            "success": True,
            "message": "Salon activated successfully",
            "data": salon
        }
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to activate salon: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to activate salon"
        )


@router.post("/salons/{salon_id}/deactivate")
async def deactivate_salon(
    salon_id: str,
    reason: Optional[str] = None,
    current_user: TokenData = Depends(require_admin)
):
    """Deactivate a salon"""
    try:
        salon_service = SalonService()
        salon = await salon_service.deactivate_salon(salon_id, reason=reason)
        
        return {
            "success": True,
            "message": "Salon deactivated successfully",
            "data": salon
        }
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to deactivate salon: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate salon"
        )


@router.post("/salons/{salon_id}/verify")
async def verify_salon(
    salon_id: str,
    current_user: TokenData = Depends(require_admin)
):
    """Verify a salon"""
    try:
        salon_service = SalonService()
        salon = await salon_service.verify_salon(
            salon_id=salon_id,
            admin_id=current_user.user_id
        )
        
        return {
            "success": True,
            "message": "Salon verified successfully",
            "data": salon
        }
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to verify salon: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify salon"
        )


@router.get("/salons/pending-verification")
async def get_pending_verification_salons(
    limit: int = 50,
    current_user: TokenData = Depends(require_admin)
):
    """Get salons pending verification (payment done but not verified)"""
    try:
        salon_service = SalonService()
        salons = await salon_service.get_pending_verification_salons(limit=limit)
        
        return {
            "success": True,
            "data": salons,
            "count": len(salons)
        }
    
    except Exception as e:
        logger.error(f"Failed to fetch pending verification salons: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch pending verification salons"
        )


@router.get("/salons/pending-payment")
async def get_pending_payment_salons(
    limit: int = 50,
    current_user: TokenData = Depends(require_admin)
):
    """Get salons pending registration payment"""
    try:
        salon_service = SalonService()
        salons = await salon_service.get_pending_payment_salons(limit=limit)
        
        return {
            "success": True,
            "data": salons,
            "count": len(salons)
        }
    
    except Exception as e:
        logger.error(f"Failed to fetch pending payment salons: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch pending payment salons"
        )


# =====================================================
# SYSTEM CONFIGURATION MANAGEMENT
# =====================================================

@router.get("/config", response_model=List[SystemConfigResponse])
async def get_all_configs(
    current_user: TokenData = Depends(require_admin)
):
    """
    Get all system configurations
    - Admin only
    - Returns all config entries including sensitive ones (for admin visibility)
    """
    try:
        config_service = ConfigService()
        configs = await config_service.get_all_configs()
        
        return configs
    
    except Exception as e:
        logger.error(f"Failed to fetch configs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch configurations: {str(e)}"
        )


@router.get("/config/{config_key}", response_model=SystemConfigResponse)
async def get_config(
    config_key: str,
    current_user: TokenData = Depends(require_admin)
):
    """
    Get a specific configuration by key
    - Admin only
    """
    try:
        config_service = ConfigService()
        config = await config_service.get_config(config_key)
        
        return config
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to fetch config {config_key}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch configuration: {str(e)}"
        )


@router.post("/config", response_model=SystemConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_config(
    config: SystemConfigCreate,
    current_user: TokenData = Depends(require_admin)
):
    """
    Create a new system configuration
    - Admin only
    """
    try:
        config_service = ConfigService()
        new_config = await config_service.create_config(
            config_key=config.config_key,
            config_value=config.config_value,
            description=config.description,
            config_type=config.config_type.value
        )
        
        logger.info(f"Admin {current_user.user_id} created config: {config.config_key}")
        
        return new_config
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to create config: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create configuration: {str(e)}"
        )


@router.put("/config/{config_key}", response_model=SystemConfigResponse)
async def update_config(
    config_key: str,
    config_update: SystemConfigUpdate,
    current_user: TokenData = Depends(require_admin)
):
    """
    Update a system configuration
    - Admin only
    - Tracks who made the change
    """
    try:
        config_service = ConfigService()
        
        # Build update dictionary
        updates = {"updated_by": current_user.user_id}
        
        if config_update.config_value is not None:
            updates["config_value"] = config_update.config_value
        if config_update.description is not None:
            updates["description"] = config_update.description
        if config_update.is_active is not None:
            updates["is_active"] = config_update.is_active
        
        updated_config = await config_service.update_config(config_key, updates)
        
        logger.info(f"Admin {current_user.user_id} updated config: {config_key}")
        
        return updated_config
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to update config {config_key}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update configuration: {str(e)}"
        )


@router.delete("/config/{config_key}")
async def delete_config(
    config_key: str,
    current_user: TokenData = Depends(require_admin)
):
    """
    Delete a system configuration
    - Admin only
    - Use with caution
    """
    try:
        config_service = ConfigService()
        await config_service.delete_config(config_key)
        
        logger.warning(f"Admin {current_user.user_id} deleted config: {config_key}")
        
        return {
            "success": True,
            "message": f"Configuration '{config_key}' deleted successfully"
        }
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to delete config {config_key}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete configuration: {str(e)}"
        )
