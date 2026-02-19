"""
Admin Salon Management API Endpoints
Handles salon CRUD operations and status management for admins
"""
from fastapi import APIRouter, HTTPException, Depends, status
from typing import Optional
from app.core.auth import require_admin, TokenData
from app.services.salon_service import SalonService, SalonSearchParams
from app.schemas.request.vendor import SalonUpdate
from app.schemas.admin import StatusToggle
from app.core.database import get_db_client
from app.services.email import email_service
from supabase import Client
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def get_salon_service(db: Client = Depends(get_db_client)) -> SalonService:
    """Dependency injection for SalonService"""
    return SalonService(db_client=db)


# =====================================================
# SALON MANAGEMENT
# =====================================================

@router.get("/", operation_id="admin_get_all_salons")
async def get_all_salons_admin(
    current_user: TokenData = Depends(require_admin),
    city: Optional[str] = None,
    state: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_verified: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
    salon_service: SalonService = Depends(get_salon_service)
):
    """Get all salons with optional filtering"""

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


@router.put("/{salon_id}", operation_id="admin_update_salon")
async def update_salon(
    salon_id: str,
    updates: SalonUpdate,
    current_user: TokenData = Depends(require_admin),
    salon_service: SalonService = Depends(get_salon_service)
):
    """Update salon (protected fields excluded)"""

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


@router.delete("/{salon_id}", operation_id="admin_delete_salon")
async def delete_salon(
    salon_id: str,
    hard_delete: bool = False,
    current_user: TokenData = Depends(require_admin),
    salon_service: SalonService = Depends(get_salon_service)
):
    """Delete salon (soft delete by default, hard delete if specified)"""

    result = await salon_service.delete_salon(
        salon_id=salon_id,
        hard_delete=hard_delete
    )

    return {
        "success": True,
        "message": result.get("message", "Salon deleted successfully"),
        "data": result
    }


@router.put("/{salon_id}/status", operation_id="admin_toggle_salon_status")
async def toggle_salon_status(
    salon_id: str,
    request_body: StatusToggle,
    current_user: TokenData = Depends(require_admin),
    salon_service: SalonService = Depends(get_salon_service)
):
    """Toggle salon active/inactive status"""
    is_active = request_body.is_active

    # Construct a SalonUpdate model for typed service call
    from app.schemas.request.vendor import SalonUpdate as _SalonUpdate
    updated_salon = await salon_service.update_salon(
        salon_id=salon_id,
        updates=_SalonUpdate(is_active=is_active),
        admin_id=current_user.user_id
    )

    return {
        "success": True,
        "message": f"Salon {'activated' if is_active else 'deactivated'} successfully",
        "data": updated_salon
    }


@router.post("/{salon_id}/send-payment-reminder", operation_id="admin_send_payment_reminder")
async def send_payment_reminder(
    salon_id: str,
    current_user: TokenData = Depends(require_admin),
    salon_service: SalonService = Depends(get_salon_service),
    db: Client = Depends(get_db_client)
):
    """
    Send payment reminder email to salon owner for pending registration fee
    
    Only applicable to salons with registration_fee_paid = false
    """
    try:
        # Get salon details
        salon_response = db.table('salons').select('*').eq('id', salon_id).single().execute()
        
        if not salon_response.data:
            raise HTTPException(status_code=404, detail="Salon not found")
        
        salon = salon_response.data
        
        # Check if payment is already completed
        if salon.get('registration_fee_paid'):
            raise HTTPException(
                status_code=400, 
                detail="Registration fee already paid for this salon"
            )
        
        # Get salon email and business name
        owner_email = salon.get('email')
        salon_name = salon.get('business_name')
        
        if not owner_email:
            raise HTTPException(status_code=400, detail="Salon does not have email")
        if not salon_name:
            raise HTTPException(status_code=400, detail="Salon does not have business name")
        
        # Get registration fee from system config
        config_response = db.table('system_config').select('config_value').eq('config_key', 'registration_fee_amount').single().execute()
        registration_fee = float(config_response.data.get('config_value', 999.0)) if config_response.data else 999.0
        
        # Send payment reminder email - vendor just needs to login and pay
        email_sent = await email_service.send_payment_reminder_email(
            to_email=owner_email,
            salon_name=salon_name,
            registration_fee=registration_fee,
            salon_id=salon_id
        )
        
        if not email_sent:
            raise HTTPException(
                status_code=500,
                detail="Failed to send payment reminder email"
            )
        
        logger.info(f"Payment reminder sent to {owner_email} for salon {salon_id}")
        
        return {
            "success": True,
            "message": f"Payment reminder email sent to {owner_email}",
            "data": {
                "salon_id": salon_id,
                "salon_name": salon_name,
                "owner_email": owner_email
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending payment reminder: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send payment reminder: {str(e)}"
        )