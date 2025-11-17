from pydantic import BaseModel, Field
from typing import Optional


class ServiceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    duration_minutes: int = Field(..., gt=0)
    price: float = Field(..., ge=0)
    description: Optional[str] = None
    category_id: Optional[str] = None
    image_url: Optional[str] = None


class ServiceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    duration_minutes: Optional[int] = Field(None, gt=0)
    price: Optional[float] = Field(None, ge=0)
    description: Optional[str] = None
    category_id: Optional[str] = None
    image_url: Optional[str] = None


class StaffCreate(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=200)
    phone: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = True


class StaffUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=200)
    phone: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class StatusToggle(BaseModel):
    is_active: bool
