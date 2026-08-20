"""
Request Pydantic schemas for Feature entitlement endpoints.
"""
from pydantic import BaseModel, Field


class FeatureStatusUpdate(BaseModel):
    """Flip a feature's entitlement status."""
    status: str = Field(
        ...,
        description=(
            "internal = staff only (built, unsold) | "
            "enabled = client has it | "
            "disabled = off for everyone (kill switch)"
        ),
        json_schema_extra={"example": "enabled"},
    )
