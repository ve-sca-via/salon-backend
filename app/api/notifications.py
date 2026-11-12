"""
Push notification endpoints.

    POST   /notifications/devices   — register this phone's Expo push token (after sign-in)
    DELETE /notifications/devices   — remove it (on sign-out)

Any authenticated user may register their own device; sending is done by backend
events (new booking, ...) through PushService, never by a client.
"""
from fastapi import APIRouter, Depends
from supabase import Client

from app.core.auth import TokenData, get_current_user
from app.core.database import get_db_client
from app.schemas.request.notification import DeviceRegister, DeviceUnregister
from app.services.push_service import PushService

router = APIRouter(prefix="/notifications", tags=["notifications"])


def get_push_service(db: Client = Depends(get_db_client)) -> PushService:
    return PushService(db_client=db)


@router.post("/devices")
async def register_device(
    body: DeviceRegister,
    current_user: TokenData = Depends(get_current_user),
    push_service: PushService = Depends(get_push_service),
):
    """Register (or move to the signed-in user) a phone's push token."""
    await push_service.register_device(
        user_id=current_user.user_id,
        expo_push_token=body.expo_push_token,
        platform=body.platform,
        app=body.app,
        device_id=body.device_id,
    )
    return {"success": True, "message": "Device registered"}


@router.delete("/devices")
async def unregister_device(
    body: DeviceUnregister,
    current_user: TokenData = Depends(get_current_user),
    push_service: PushService = Depends(get_push_service),
):
    """Remove a push token for the signed-in user (call before signing out)."""
    await push_service.unregister_device(current_user.user_id, body.expo_push_token)
    return {"success": True, "message": "Device removed"}
