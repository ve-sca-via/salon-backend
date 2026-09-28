from pydantic import BaseModel, EmailStr, Field
from typing import Optional

from .request.base import IndianMobile, PartialUpdateModel


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8)
    role: str = Field(..., description="relationship_manager or customer")
    phone: IndianMobile = None
    age: int = Field(..., ge=18, le=100, description="User age, must be between 18 and 100")
    gender: str = Field(..., description="User gender: male, female, or other")


class UserUpdate(PartialUpdateModel):
    full_name: Optional[str] = None
    phone: IndianMobile = None
    is_active: Optional[bool] = None


class UserProfileUpdate(PartialUpdateModel):
    """Self-service profile edit for staff (`PUT /rm/profile`)."""
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    phone: IndianMobile = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
