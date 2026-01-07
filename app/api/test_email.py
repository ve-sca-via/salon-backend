"""
Test Email Endpoint - For Debugging Email Functionality
Only available in development/staging environments
"""
from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import BaseModel, EmailStr
from app.core.config import settings
from app.services.email import get_email_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/test-email", tags=["Testing"])


class TestEmailRequest(BaseModel):
    """Test email request"""
    to_email: EmailStr
    test_type: str = "approval"  # approval, booking, welcome, rejection


# Only enable in non-production environments
@router.post("/send")
async def send_test_email(request: TestEmailRequest = Body(...)):
    """
    Send a test email for debugging
    
    **Available test types:**
    - `approval` - Vendor approval email
    - `welcome` - Welcome vendor email
    - `booking` - Booking confirmation email
    - `rejection` - Vendor rejection email
    - `career` - Career application confirmation
    
    **Only available in development/staging environments**
    """
    # Security: Only allow in non-production
    if settings.is_production:
        raise HTTPException(
            status_code=403,
            detail="Test email endpoint is disabled in production"
        )
    
    email_service = get_email_service()
    
    try:
        if request.test_type == "approval":
            success = await email_service.send_vendor_approval_email(
                to_email=request.to_email,
                owner_name="Test Owner",
                salon_name="Test Salon & Spa",
                registration_token="test_token_eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
                registration_fee=5000.0
            )
            
        elif request.test_type == "welcome":
            success = await email_service.send_welcome_vendor_email(
                to_email=request.to_email,
                owner_name="Test Owner",
                salon_name="Test Salon & Spa"
            )
            
        elif request.test_type == "booking":
            success = await email_service.send_booking_confirmation_email(
                to_email=request.to_email,
                customer_name="Test Customer",
                salon_name="Test Salon & Spa",
                services=[
                    {"name": "Haircut", "unit_price": 500},
                    {"name": "Hair Color", "unit_price": 1500}
                ],
                booking_date="2025-12-01",
                booking_time="10:00 AM",
                staff_name="John Stylist",
                total_amount=2000.0,
                booking_id="test-booking-123"
            )
            
        elif request.test_type == "rejection":
            success = await email_service.send_vendor_rejection_email(
                to_email=request.to_email,
                owner_name="Test Owner",
                salon_name="Test Salon & Spa",
                rejection_reason="Incomplete documentation provided. Please resubmit with all required documents.",
                rm_name="Test RM"
            )
            
        elif request.test_type == "career":
            success = await email_service.send_career_application_confirmation(
                to_email=request.to_email,
                applicant_name="Test Applicant",
                position="Hair Stylist",
                application_number="APP-2025-001"
            )
            
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid test_type: {request.test_type}. Choose: approval, welcome, booking, rejection, career"
            )
        
        if success:
            return {
                "success": True,
                "message": f"Test email ({request.test_type}) sent successfully!",
                "details": {
                    "to_email": request.to_email,
                    "test_type": request.test_type,
                    "email_enabled": settings.EMAIL_ENABLED,
                    "smtp_host": settings.SMTP_HOST,
                    "smtp_port": settings.SMTP_PORT,
                    "mailpit_url": "http://127.0.0.1:54324" if settings.is_development else None
                }
            }
        else:
            return {
                "success": False,
                "message": "Failed to send test email",
                "details": {
                    "to_email": request.to_email,
                    "test_type": request.test_type
                }
            }
            
    except Exception as e:
        logger.error(f"Test email error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send test email: {str(e)}"
        )


@router.get("/status")
async def get_email_status():
    """
    Get current email configuration status
    """
    if settings.is_production:
        raise HTTPException(
            status_code=403,
            detail="Test email endpoint is disabled in production"
        )
    
    return {
        "email_enabled": settings.EMAIL_ENABLED,
        "email_from": settings.EMAIL_FROM,
        "email_from_name": settings.EMAIL_FROM_NAME,
        "admin_email": settings.ADMIN_EMAIL,
        "smtp_config": {
            "host": settings.SMTP_HOST,
            "port": settings.SMTP_PORT,
            "tls": settings.SMTP_TLS,
            "ssl": settings.SMTP_SSL,
            "user_configured": bool(settings.SMTP_USER)
        },
        "frontend_urls": {
            "frontend": settings.FRONTEND_URL,
            "admin_panel": settings.ADMIN_PANEL_URL,
            "vendor_portal": settings.VENDOR_PORTAL_URL,
            "rm_portal": settings.RM_PORTAL_URL
        },
        "mailpit_url": "http://127.0.0.1:54324" if settings.is_development else None,
        "environment": settings.ENVIRONMENT
    }
