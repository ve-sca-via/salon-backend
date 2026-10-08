"""
Razorpay Webhook Service

The second path from "money moved" to "we know about it". Until now there was
only one: the browser's success callback. If it was lost — tab closed, network
dropped, a crash between the charge and our request — the payment was captured
and nothing in our system knew. No booking, no record, no alert; only Razorpay's
dashboard had the truth (payment audit C-3).

This handles `payment.captured` for all three flows and routes it to whichever
pre-payment record the Razorpay order belongs to:

    payment_intents              -> complete the cart booking
    product_orders               -> mark the order paid
    vendor_registration_payments -> record the fee and activate the salon

Every branch is idempotent, because a webhook is delivered at least once and can
arrive before, during or after the browser callback. Where both can run, they
converge on the same guard the browser path already used: a booking is unique on
`razorpay_payment_id`, a product order and a registration payment only move out
of `pending` once.

Trust model: the only thing authenticating this request is the HMAC in the
`X-Razorpay-Signature` header, computed over the exact bytes of the body with the
webhook secret. Nothing in the body is believed before that check passes, and the
signature is checked against the raw bytes, never a re-serialised copy.
"""

import hashlib
import hmac
import json
import logging
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks

from app.services.config_service import ConfigService

logger = logging.getLogger(__name__)

WEBHOOK_SECRET_CONFIG_KEY = "razorpay_webhook_secret"

# Events we act on. Anything else is acknowledged and ignored — Razorpay lets you
# subscribe to dozens, and a 2xx on an event we do not handle is correct: it means
# "received", not "acted upon".
HANDLED_EVENTS = {"payment.captured", "payment.failed"}


class WebhookSecretMissing(Exception):
    """
    Raised when no webhook secret is configured.

    Distinct from a bad signature: a bad signature is a request to reject, while a
    missing secret is our own misconfiguration, and the endpoint answers 503 so
    Razorpay keeps retrying until someone sets it.
    """


class RazorpayWebhookService:
    """Verifies and dispatches Razorpay webhook deliveries."""

    def __init__(self, db_client):
        self.db = db_client

    # =====================================================
    # AUTHENTICATION
    # =====================================================

    async def resolve_secret(self) -> str:
        """The configured webhook secret, or raise WebhookSecretMissing."""
        secret = await ConfigService(self.db).get_cached_config_value(
            WEBHOOK_SECRET_CONFIG_KEY
        )
        if not secret:
            raise WebhookSecretMissing(
                f"'{WEBHOOK_SECRET_CONFIG_KEY}' is not set in system configuration"
            )
        return secret

    @staticmethod
    def signature_is_valid(raw_body: bytes, signature: Optional[str], secret: str) -> bool:
        """
        Check Razorpay's `X-Razorpay-Signature` against the raw request body.

        Razorpay signs webhooks as hex HMAC-SHA256 over the body bytes with the
        webhook secret (the same thing `razorpay.Utility.verify_webhook_signature`
        does, reimplemented here so verification needs no API credentials and no
        client object). `compare_digest` keeps the comparison constant-time.
        """
        if not signature:
            return False

        expected = hmac.new(
            secret.encode("utf-8"), raw_body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    @staticmethod
    def parse_body(raw_body: bytes) -> Optional[Dict[str, Any]]:
        """Decode a verified body. None if it is not a JSON object."""
        try:
            parsed = json.loads(raw_body)
        except (ValueError, TypeError) as e:
            logger.error(f"Razorpay webhook body is not valid JSON: {e}")
            return None
        if not isinstance(parsed, dict):
            logger.error("Razorpay webhook body is not a JSON object")
            return None
        return parsed

    # =====================================================
    # DISPATCH
    # =====================================================

    async def handle_event(
        self,
        event: Dict[str, Any],
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> Dict[str, Any]:
        """
        Act on a verified webhook event.

        Returns a small dict describing what was done, which the endpoint logs and
        the tests assert on. Raises only on failures worth a retry — the endpoint
        turns those into a non-2xx so Razorpay delivers again.
        """
        event_name = event.get("event")
        if event_name not in HANDLED_EVENTS:
            logger.info(f"Razorpay webhook: ignoring unhandled event {event_name!r}")
            return {"event": event_name, "action": "ignored"}

        payment = (
            event.get("payload", {})
            .get("payment", {})
            .get("entity", {})
        )
        if not isinstance(payment, dict) or not payment.get("id"):
            logger.error(
                f"Razorpay webhook {event_name!r} carried no payment entity; ignoring"
            )
            return {"event": event_name, "action": "ignored", "reason": "no_payment_entity"}

        if event_name == "payment.failed":
            return await self._handle_payment_failed(payment)
        return await self._handle_payment_captured(payment, background_tasks)

    async def _handle_payment_captured(
        self,
        payment: Dict[str, Any],
        background_tasks: Optional[BackgroundTasks],
    ) -> Dict[str, Any]:
        payment_id = payment["id"]
        order_id = payment.get("order_id")

        if not order_id:
            # A payment made outside an order (e.g. a payment link) is not
            # something any of our flows create.
            logger.warning(
                f"Razorpay webhook: captured payment {payment_id} has no order id; ignoring"
            )
            return {"action": "ignored", "reason": "no_order_id", "payment_id": payment_id}

        # --- Flow A: cart checkout -------------------------------------------
        from app.services.payment_intent_service import PaymentIntentService

        intent_service = PaymentIntentService(self.db)
        intent = await intent_service.get_by_order_id(order_id)

        if intent:
            await intent_service.mark_captured(order_id, razorpay_payment_id=payment_id)

            if not self._captured_amount_covers(payment, intent.get("amount"), payment_id):
                return {
                    "action": "skipped",
                    "reason": "amount_mismatch",
                    "flow": "cart_checkout",
                    "payment_id": payment_id,
                }

            from app.services.customer_service import CustomerService

            booking = await CustomerService(self.db).create_booking_from_intent(
                intent, payment_id, background_tasks=background_tasks
            )

            if not booking:
                # create_booking_from_intent has already logged why, at ERROR.
                return {
                    "action": "unresolved",
                    "flow": "cart_checkout",
                    "payment_id": payment_id,
                }

            await intent_service.mark_completed(
                order_id,
                booking_id=booking.get("id"),
                razorpay_payment_id=payment_id,
            )
            return {
                "action": "booking_completed",
                "flow": "cart_checkout",
                "payment_id": payment_id,
                "booking_id": booking.get("id"),
            }

        # --- Flow B: product order -------------------------------------------
        from app.services.product_order_service import ProductOrderService

        product_service = ProductOrderService(self.db)
        product_order = await product_service.find_by_razorpay_order_id(order_id)

        if product_order:
            updated = await product_service.mark_order_paid_from_webhook(order_id, payment_id)
            if updated:
                return {
                    "action": "order_paid",
                    "flow": "product_order",
                    "payment_id": payment_id,
                    "order_number": updated.get("order_number"),
                }
            logger.info(
                f"Razorpay webhook: product order {product_order.get('order_number')} "
                f"was not pending (status {product_order.get('payment_status')!r}); "
                "nothing to update"
            )
            return {
                "action": "already_settled",
                "flow": "product_order",
                "payment_id": payment_id,
                "order_number": product_order.get("order_number"),
            }

        # --- Flow C: vendor registration fee ---------------------------------
        if await self._registration_payment_exists(order_id):
            from app.services.payment_service import PaymentService

            result = await PaymentService(self.db).complete_vendor_registration_from_webhook(
                razorpay_order_id=order_id,
                razorpay_payment_id=payment_id,
                background_tasks=background_tasks,
            )
            return {
                "action": "registration_recorded",
                "flow": "vendor_registration",
                "payment_id": payment_id,
                "activated": result.get("activated"),
            }

        # --- Nothing matches --------------------------------------------------
        # Captured money against an order we have no record of. This is the alert
        # worth waking someone for: it is either a payment for a record that failed
        # to insert, or an order created by a different environment sharing the
        # same Razorpay account.
        logger.error(
            f"Razorpay webhook: captured payment {payment_id} for order {order_id} "
            "matches no payment intent, product order or registration payment. "
            "Money has been taken with nothing in our system to attach it to."
        )
        return {"action": "orphan", "payment_id": payment_id, "order_id": order_id}

    async def _handle_payment_failed(self, payment: Dict[str, Any]) -> Dict[str, Any]:
        """
        Record a gateway-reported failure.

        Informational only — a failed payment needs nothing undone, because no flow
        records anything as paid until a capture. Worth storing so an intent that
        was abandoned looks different from one still in flight.
        """
        payment_id = payment["id"]
        order_id = payment.get("order_id")
        reason = payment.get("error_description") or payment.get("error_reason")

        if not order_id:
            return {"action": "ignored", "reason": "no_order_id", "payment_id": payment_id}

        from app.services.payment_intent_service import PaymentIntentService

        await PaymentIntentService(self.db).mark_failed(order_id, reason=reason)
        logger.info(
            f"Razorpay webhook: payment {payment_id} failed for order {order_id} "
            f"({reason or 'no reason given'})"
        )
        return {"action": "failure_recorded", "payment_id": payment_id}

    # =====================================================
    # HELPERS
    # =====================================================

    @staticmethod
    def _captured_amount_covers(
        payment: Dict[str, Any],
        intent_amount: Any,
        payment_id: str,
    ) -> bool:
        """
        Confirm the captured amount is at least what the intent pinned.

        Razorpay reports paise. A capture for *less* than we pinned would mean
        recording a booking as paid for more than was collected, so it is refused
        and left for a person. A capture for more is logged and accepted — the
        booking is still owed.
        """
        try:
            captured_paise = int(payment.get("amount"))
            pinned_paise = int(round(float(intent_amount) * 100))
        except (TypeError, ValueError):
            logger.warning(
                f"Razorpay webhook: could not compare amounts for payment {payment_id} "
                f"(captured {payment.get('amount')!r}, pinned {intent_amount!r}); "
                "proceeding on the pinned breakdown"
            )
            return True

        if captured_paise < pinned_paise:
            logger.error(
                f"Razorpay webhook: payment {payment_id} captured {captured_paise} paise "
                f"but the intent pinned {pinned_paise}. Refusing to record a booking as "
                "paid for more than was collected; needs manual follow-up."
            )
            return False

        if captured_paise > pinned_paise:
            logger.warning(
                f"Razorpay webhook: payment {payment_id} captured {captured_paise} paise, "
                f"more than the pinned {pinned_paise}. Recording the booking anyway."
            )

        return True

    async def _registration_payment_exists(self, razorpay_order_id: str) -> bool:
        """Whether this Razorpay order is a vendor registration fee."""
        try:
            response = self.db.table("vendor_registration_payments")\
                .select("id")\
                .eq("razorpay_order_id", razorpay_order_id)\
                .maybe_single()\
                .execute()
            return bool(getattr(response, "data", None))
        except Exception as e:
            logger.warning(
                f"Could not look up registration payment for order {razorpay_order_id}: {e}"
            )
            return False
