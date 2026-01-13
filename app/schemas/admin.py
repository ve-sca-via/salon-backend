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


class StatusToggle(BaseModel):
    is_active: bool


# Service Category Schemas
class ServiceCategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    icon_url: Optional[str] = None
    display_order: int = Field(default=0, ge=0)
    is_active: bool = Field(default=True)


class ServiceCategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    icon_url: Optional[str] = None
    display_order: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None
