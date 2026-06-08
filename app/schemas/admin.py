from pydantic import BaseModel, Field
from typing import Optional


class ServiceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    duration_minutes: int = Field(..., gt=0)
    price: float = Field(..., ge=0)
    description: Optional[str] = None
    # Taxonomy: pick existing nodes by id, or create/match by name (3 levels).
    category_id: Optional[str] = None
    subcategory_id: Optional[str] = None
    sub_subcategory_id: Optional[str] = None
    category_name: Optional[str] = Field(None, min_length=1, max_length=255)
    subcategory_name: Optional[str] = Field(None, min_length=1, max_length=255)
    sub_subcategory_name: Optional[str] = Field(None, min_length=1, max_length=255)
    gender_category: Optional[str] = Field("both", pattern="^(male|female|both)$")
    image_url: Optional[str] = None


class ServiceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    duration_minutes: Optional[int] = Field(None, gt=0)
    price: Optional[float] = Field(None, ge=0)
    description: Optional[str] = None
    category_id: Optional[str] = None
    subcategory_id: Optional[str] = None
    sub_subcategory_id: Optional[str] = None
    category_name: Optional[str] = Field(None, min_length=1, max_length=255)
    subcategory_name: Optional[str] = Field(None, min_length=1, max_length=255)
    sub_subcategory_name: Optional[str] = Field(None, min_length=1, max_length=255)
    gender_category: Optional[str] = Field(None, pattern="^(male|female|both)$")
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


# Service Subcategory Schemas (Category 2 — nested under Category 1)
class ServiceSubcategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    icon_url: Optional[str] = None
    display_order: int = Field(default=0, ge=0)
    is_active: bool = Field(default=True)
    # Optional parent subcategory -> creates a level-3 sub-subcategory.
    # NULL/omitted = a level-2 subcategory directly under the category.
    parent_subcategory_id: Optional[str] = None


class ServiceSubcategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    icon_url: Optional[str] = None
    display_order: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None
