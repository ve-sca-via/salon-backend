"""
Request Pydantic schemas for Banner endpoints.
Validation for the admin-managed home-screen carousel banners.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class BannerCreate(BaseModel):
    """Schema for creating a new carousel banner."""
    title: Optional[str] = Field(None, max_length=200, description="Optional caption / alt text / admin label")
    image_url: str = Field(..., min_length=1, max_length=1000, description="Banner image URL (from the upload endpoint)")
    link_url: Optional[str] = Field(None, max_length=1000, description="Optional tap target (deep link or external URL)")
    sort_order: int = Field(default=0, ge=0, description="Ascending display order in the carousel")
    is_active: bool = Field(default=True, description="Whether the banner is shown in the app")
    starts_at: Optional[datetime] = Field(None, description="Optional schedule window start (UTC)")
    ends_at: Optional[datetime] = Field(None, description="Optional schedule window end (UTC)")

    @model_validator(mode="after")
    def validate_window(self):
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class BannerUpdate(BaseModel):
    """Schema for updating a banner (all fields optional)."""
    title: Optional[str] = Field(None, max_length=200)
    image_url: Optional[str] = Field(None, min_length=1, max_length=1000)
    link_url: Optional[str] = Field(None, max_length=1000)
    sort_order: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_window(self):
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class BannerOrderItem(BaseModel):
    """A single (id, sort_order) pair used by the bulk reorder endpoint."""
    id: str = Field(..., description="Banner UUID")
    sort_order: int = Field(..., ge=0, description="New ascending position")


class BannerReorder(BaseModel):
    """Bulk reorder payload — the full ordered set of banners from the admin UI."""
    orders: List[BannerOrderItem] = Field(..., min_length=1, description="Banner id -> sort_order mapping")

    @field_validator("orders")
    @classmethod
    def validate_unique_ids(cls, v):
        ids = [item.id for item in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate banner ids in reorder payload")
        return v
