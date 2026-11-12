"""
Push Service - device registration and delivery through the Expo Push API.

Delivery path: backend -> Expo (https://exp.host/--/api/v2/push/send) -> FCM/APNs ->
the phone. Expo is a thin HTTP wrapper over the OS networks, so this file is the only
place that knows about it.

Sending NEVER raises: a push is a courtesy on top of a booking/order that already
happened, so a failure is logged and swallowed. Tokens Expo reports as
`DeviceNotRegistered` (app uninstalled, token revoked) are deactivated so we stop
sending to them.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.database import db_exec

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
EXPO_CHUNK_SIZE = 100  # Expo accepts at most 100 messages per request
_TOKEN_RE = re.compile(r"^Expo(nent)?PushToken\[[^\]\s]+\]$")


def is_valid_expo_token(token: str) -> bool:
    """Whether `token` looks like an Expo push token (ExponentPushToken[...])."""
    return bool(token) and bool(_TOKEN_RE.match(token))


class PushService:
    def __init__(self, db_client):
        self.db = db_client

    # ------------------------------------------------------------------
    # Device registration
    # ------------------------------------------------------------------
    async def register_device(
        self,
        user_id: str,
        expo_push_token: str,
        platform: str,
        app: str,
        device_id: Optional[str] = None,
    ) -> None:
        """
        Attach a phone's push token to `user_id`.

        Upserts on the token: when a different user signs in on the same phone the
        row moves to them, so the previous account stops receiving pushes there.
        """
        now = datetime.now(timezone.utc).isoformat()
        await db_exec(
            self.db.table("device_tokens").upsert(
                {
                    "user_id": user_id,
                    "expo_push_token": expo_push_token,
                    "platform": platform,
                    "app": app,
                    "device_id": device_id,
                    "is_active": True,
                    "last_seen_at": now,
                },
                on_conflict="expo_push_token",
            )
        )

    async def unregister_device(self, user_id: str, expo_push_token: str) -> None:
        """Remove a token on sign-out. Scoped to the user so nobody can drop another's."""
        await db_exec(
            self.db.table("device_tokens")
            .delete()
            .eq("expo_push_token", expo_push_token)
            .eq("user_id", user_id)
        )

    async def deactivate_user_devices(self, user_id: str) -> None:
        """Stop all pushes to a user (e.g. account deletion)."""
        await db_exec(
            self.db.table("device_tokens").delete().eq("user_id", user_id)
        )

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------
    async def _active_tokens(self, user_id: str) -> List[str]:
        response = await db_exec(
            self.db.table("device_tokens")
            .select("expo_push_token")
            .eq("user_id", user_id)
            .eq("is_active", True)
        )
        return [row["expo_push_token"] for row in (response.data or [])]

    async def send_to_user(
        self,
        user_id: Optional[str],
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        channel_id: str = "bookings",
    ) -> int:
        """
        Push to every active phone of `user_id`. Returns how many Expo accepted.
        Never raises.
        """
        if not user_id:
            return 0
        try:
            tokens = await self._active_tokens(user_id)
            if not tokens:
                return 0
            return await self._send(tokens, title, body, data or {}, channel_id)
        except Exception as error:
            logger.warning(f"Push to user {user_id} failed: {error}")
            return 0

    async def _send(
        self,
        tokens: List[str],
        title: str,
        body: str,
        data: Dict[str, Any],
        channel_id: str,
    ) -> int:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if settings.EXPO_ACCESS_TOKEN:
            headers["Authorization"] = f"Bearer {settings.EXPO_ACCESS_TOKEN}"

        accepted = 0
        dead: List[str] = []
        async with httpx.AsyncClient(timeout=10.0) as client:
            for start in range(0, len(tokens), EXPO_CHUNK_SIZE):
                chunk = tokens[start:start + EXPO_CHUNK_SIZE]
                messages = [
                    {
                        "to": token,
                        "title": title,
                        "body": body,
                        "data": data,
                        "sound": "default",
                        "priority": "high",
                        "channelId": channel_id,
                    }
                    for token in chunk
                ]
                response = await client.post(EXPO_PUSH_URL, json=messages, headers=headers)
                if response.status_code != 200:
                    logger.warning(f"Expo push HTTP {response.status_code}: {response.text[:200]}")
                    continue
                tickets = (response.json() or {}).get("data") or []
                for token, ticket in zip(chunk, tickets):
                    if ticket.get("status") == "ok":
                        accepted += 1
                    elif (ticket.get("details") or {}).get("error") == "DeviceNotRegistered":
                        dead.append(token)
                    else:
                        logger.warning(f"Expo push rejected: {ticket.get('message')}")

        if dead:
            try:
                await db_exec(
                    self.db.table("device_tokens")
                    .update({"is_active": False})
                    .in_("expo_push_token", dead)
                )
            except Exception as error:
                logger.warning(f"Could not deactivate {len(dead)} dead push tokens: {error}")
        return accepted
