"""Request schemas for push-notification device registration."""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.services.push_service import is_valid_expo_token


class DeviceRegister(BaseModel):
    """A phone's Expo push token, sent by the mobile app after sign-in."""
    expo_push_token: str = Field(..., max_length=200, description="ExponentPushToken[...] from expo-notifications")
    platform: Literal["android", "ios"]
    app: Literal["partner-app", "customer-app"]
    device_id: Optional[str] = Field(None, max_length=200)

    @field_validator("expo_push_token")
    @classmethod
    def _valid_token(cls, value: str) -> str:
        if not is_valid_expo_token(value):
            raise ValueError("expo_push_token must look like ExponentPushToken[...]")
        return value


class DeviceUnregister(BaseModel):
    expo_push_token: str = Field(..., max_length=200)
