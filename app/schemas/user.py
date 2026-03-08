from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8)
    role: str = Field(..., description="relationship_manager or customer")
    phone: Optional[str] = None
    age: int = Field(..., ge=18, le=100, description="User age, must be between 18 and 100")
    gender: str = Field(..., description="User gender: male, female, or other")


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    role: Optional[str] = None


class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None


class ProfileUpdateRequest(BaseModel):
    """Request schema for customers updating their own profile"""
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    age: Optional[int] = Field(None, ge=13, le=120)
    gender: Optional[str] = Field(None)

    @validator('gender')
    def validate_gender(cls, v):
        if v is not None and v.lower() not in ['male', 'female', 'other']:
            raise ValueError("Gender must be 'male', 'female', or 'other'")
        return v.lower() if v else v


class ChangePasswordRequest(BaseModel):
    """Request schema for changing password (requires current password)"""
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, description="Minimum 8 characters")
