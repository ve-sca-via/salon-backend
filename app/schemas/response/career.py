"""
Response Pydantic schemas for career endpoints
All career response models should be defined here for consistency
"""
from pydantic import BaseModel
from typing import Optional, Any, Dict
from datetime import datetime


# =====================================================
# CAREER RESPONSE SCHEMAS
# =====================================================

class CareerApplicationResponse(BaseModel):
    """Response after successful career application submission"""
    id: str
    message: str
    application_number: str
    email_sent: bool = True
    warning: Optional[str] = None


class CareerApplicationUpdateResponse(BaseModel):
    """Response after updating career application status"""
    message: str
    application: Dict[str, Any]  # Full application data
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "Application updated successfully",
                "application": {
                    "id": "a1b2c3d4-...",
                    "application_number": "CA-20260112-A1B2C3D4",
                    "status": "shortlisted",
                    "full_name": "John Doe",
                    "email": "john@example.com",
                    "admin_notes": "Good candidate",
                    "updated_at": "2026-01-12T10:30:00Z"
                }
            }
        }