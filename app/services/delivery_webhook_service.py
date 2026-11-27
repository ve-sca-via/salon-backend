"""
Delivery Webhook Service — partner-neutral shipment updates.

No delivery partner is chosen yet, so instead of one partner's format we accept
a small, documented one of our own (docs/INVENTORY_AND_DELIVERY.md):

    POST /webhooks/delivery
    X-Delivery-Signature: hex HMAC-SHA256(raw body, delivery_webhook_secret)
    {
      "order_number": "PO-...",          # or "tracking_number" (AWB) — one is required
      "tracking_number": "AWB123",
      "event": "picked_up",              # see EVENT_TO_STATUS
      "courier_name": "Delhivery",
      "tracking_url": "https://...",
      "note": "free text",
      "occurred_at": "2026-11-27T10:00:00Z"
    }

When a partner is chosen, its own webhook gets a thin adapter that translates
its payload into this shape and calls `handle_update` — no change to the order
flow. Every update lands on the order timeline (product_order_events) with the
raw body, whether or not it moved the order.

Trust model mirrors the Razorpay webhook: nothing in the body is read before the
HMAC over the exact bytes verifies.
"""
import hashlib
import hmac
import json
import logging
from typing import Any, Dict, Optional

from fastapi import HTTPException

from app.services.config_service import ConfigService
from app.services.product_order_service import ProductOrderService, ALLOWED_TRANSITIONS

logger = logging.getLogger(__name__)

DELIVERY_WEBHOOK_SECRET_CONFIG_KEY = "delivery_webhook_secret"

# Courier event -> the order status it implies (None = timeline entry only).
EVENT_TO_STATUS: Dict[str, Optional[str]] = {
    "manifested": None,          # shipment booked, not yet picked up
    "picked_up": "shipped",
    "in_transit": "shipped",
    "out_for_delivery": "shipped",
    "delivery_failed": None,     # attempt failed; courier will retry
    "delivered": "delivered",
    "rto_initiated": None,       # coming back to the warehouse
    "rto_delivered": "cancelled",  # back at the warehouse -> cancel + restock
    "shipment_cancelled": None,  # courier-side cancellation; admin decides the order
}


class DeliveryWebhookSecretMissing(Exception):
    pass


class DeliveryWebhookService:
    def __init__(self, db_client):
        self.db = db_client
        self.orders = ProductOrderService(db_client)

    async def resolve_secret(self) -> str:
        secret = await ConfigService(self.db).get_cached_config_value(
            DELIVERY_WEBHOOK_SECRET_CONFIG_KEY
        )
        if not secret:
            raise DeliveryWebhookSecretMissing(
                f"'{DELIVERY_WEBHOOK_SECRET_CONFIG_KEY}' is not set in system configuration"
            )
        return secret

    @staticmethod
    def signature_is_valid(raw_body: bytes, signature: Optional[str], secret: str) -> bool:
        if not signature:
            return False
        expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature.strip().lower())

    @staticmethod
    def parse_body(raw_body: bytes) -> Optional[Dict[str, Any]]:
        try:
            parsed = json.loads(raw_body)
        except (ValueError, TypeError):
            return None
        return parsed if isinstance(parsed, dict) else None

    async def handle_update(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply one shipment update. Returns what was done.

        Never raises for a bad/unknown/out-of-order update — redelivering the
        same body would not help, so those are acknowledged and logged. Raises
        only on our own failures (DB), so the partner retries.
        """
        event = str(body.get("event") or "").strip().lower()
        order_number = body.get("order_number")
        tracking_number = body.get("tracking_number")

        order = await self.orders.find_order_for_delivery(order_number, tracking_number)
        if not order:
            logger.warning(
                f"Delivery webhook: no order for order_number={order_number!r} "
                f"tracking_number={tracking_number!r} (event {event!r})"
            )
            return {"action": "order_not_found"}

        order_id = order["id"]
        note = body.get("note")
        if event not in EVENT_TO_STATUS:
            await self.orders._log_event(order_id, "delivery_webhook", event or "unknown",
                                         note=note, payload=body)
            return {"action": "logged_unknown_event", "event": event}

        target = EVENT_TO_STATUS[event]
        current = order.get("status")
        can_move = target and (target == current or target in ALLOWED_TRANSITIONS.get(current, set()))

        if not can_move:
            reason = None if target is None else f"ignored: order is '{current}', cannot become '{target}'"
            await self.orders._log_event(order_id, "delivery_webhook", event,
                                         from_status=current, note=reason or note, payload=body)
            # Still capture the AWB/courier the first time we hear them.
            await self._fill_missing_shipment_fields(order, body)
            return {"action": "logged", "event": event, "order_status": current}

        if target == current:
            await self.orders._log_event(order_id, "delivery_webhook", event,
                                         from_status=current, note=note, payload=body)
            await self._fill_missing_shipment_fields(order, body)
            return {"action": "logged", "event": event, "order_status": current}

        try:
            result = await self.orders.update_order_status(
                order_id,
                target,
                source="delivery_webhook",
                event=event,
                courier_name=body.get("courier_name"),
                tracking_number=tracking_number,
                tracking_url=body.get("tracking_url"),
                restock=True,   # rto_delivered: the parcel is physically back
                note=note,
                payload=body,
            )
        except HTTPException as e:
            if e.status_code in (400, 409):
                # Lost a race with an admin change — record it, don't retry.
                await self.orders._log_event(order_id, "delivery_webhook", event,
                                             from_status=current, note=f"ignored: {e.detail}", payload=body)
                return {"action": "logged", "event": event, "order_status": current}
            raise
        return {"action": "status_updated", "event": event, "from": current, "to": target,
                "stock_restored": result.get("stock_restored", False)}

    async def _fill_missing_shipment_fields(self, order: Dict[str, Any], body: Dict[str, Any]) -> None:
        fields = {
            col: body.get(col)
            for col in ("courier_name", "tracking_number", "tracking_url")
            if body.get(col) and not order.get(col)
        }
        if not fields:
            return
        from app.core.database import db_exec
        try:
            await db_exec(self.db.table("product_orders").update(fields).eq("id", order["id"]))
        except Exception as e:
            logger.error(f"Could not store shipment fields for order {order['id']}: {e}")
