"""
Request Pydantic schemas for partner ("Partner with us") endpoints
All partner request models should be defined here for consistency
"""
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, Literal


# =====================================================
# PARTNER REQUEST SCHEMAS
# =====================================================

class PartnerRequestCreate(BaseModel):
    """Schema for submitting a 'Partner with us' onboarding inquiry"""
    owner_name: str
    shop_name: str
    shop_type: Literal['Salon', 'Spa', 'Clinic', 'Other']
    email: EmailStr
    phone: str
    location: str

    @field_validator('owner_name', 'shop_name', 'phone', 'location')
    @classmethod
    def not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field cannot be empty")
        return cleaned


class PartnerRequestStatusUpdate(BaseModel):
    """Schema for updating a partner request's status (admin only)"""
    status: Literal['new', 'contacted', 'approved', 'rejected']
    admin_notes: Optional[str] = None
