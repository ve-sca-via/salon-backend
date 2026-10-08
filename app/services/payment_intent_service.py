"""
Payment Intent Service

Our own record of what a Razorpay order was for, written when the order is
created and read when the payment comes back — from the browser at checkout, or
from the `payment.captured` webhook when the browser never returns.

Why this exists (payment audit H-2 / C-3):

- The pinned priced breakdown and the cart snapshot used to live only in the
  Razorpay order's `notes`, so every cart checkout spent an external
  `orders.fetch` reading them back — inside the request the customer waits on
  *after* being charged. Reading them from our own table costs one local query
  in the same round as everything else.
- Razorpay's `notes` caps values at 256 characters; a cart of a few services
  could truncate the snapshot. `jsonb` cannot.
- A webhook has no browser and no cart state. Everything it needs to complete
  the booking — salon, appointment, pinned amounts, coupon — is here.

Writes are deliberately fail-soft: the customer has a live Razorpay order by the
time we get here, and refusing the payment because our own bookkeeping row did
not insert would be worse than the degraded path (checkout recomputes pricing
server-side, exactly as it does today when the snapshot is unreadable). Every
such failure is logged at ERROR with the order id, because it is also the
condition that leaves a capture unreconcilable.
"""

import json
import logging
from typing import Any, Dict, List, Optional
from app.core.database import db_exec

logger = logging.getLogger(__name__)

# Columns checkout and the webhook actually use. Selected explicitly so adding a
# column to the table does not silently widen the payload of a hot read.
INTENT_COLUMNS = (
    "id, razorpay_order_id, intent_type, customer_id, salon_id, amount, "
    "currency, pricing, cart_snapshot, coupon_code, booking_date, time_slots, "
    "status, razorpay_payment_id, booking_id, captured_at, completed_at"
)


def _as_json_value(value: Any) -> Any:
    """
    Normalise a jsonb column that may come back as a string.

    Supabase returns `jsonb` already decoded, but the column is written from
    Python dicts/lists and a value that was ever stored as a JSON *string*
    (older rows, or a client that encoded it itself) must not reach the caller
    as text. Anything unparseable comes back untouched for the caller to reject.
    """
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value
    return value


class PaymentIntentService:
    """Reads and writes the `payment_intents` table."""

    def __init__(self, db_client):
        self.db = db_client

    async def create_cart_intent(
        self,
        *,
        razorpay_order_id: str,
        customer_id: str,
        salon_id: Optional[str],
        amount: float,
        pricing: Dict[str, Any],
        cart_snapshot: List[Dict[str, Any]],
        currency: str = "INR",
        coupon_code: Optional[str] = None,
        booking_date: Optional[str] = None,
        time_slots: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Record the snapshot behind a freshly created cart order.

        Returns the inserted row, or None if the insert failed — see the module
        docstring on why that is not raised.
        """
        row = {
            "razorpay_order_id": razorpay_order_id,
            "intent_type": "cart_checkout",
            "customer_id": customer_id,
            "salon_id": salon_id,
            "amount": amount,
            "currency": currency,
            "pricing": pricing,
            "cart_snapshot": cart_snapshot,
            "coupon_code": coupon_code,
            "booking_date": booking_date,
            "time_slots": time_slots,
            "status": "created",
        }

        try:
            response = await db_exec(self.db.table("payment_intents").insert(row))
        except Exception as e:
            logger.error(
                f"Failed to record payment intent for order {razorpay_order_id}: {e}. "
                "Checkout will fall back to a server-side recompute and the "
                "payment.captured webhook will not be able to complete this booking."
            )
            return None

        data = getattr(response, "data", None)
        if not data:
            logger.error(
                f"Payment intent insert returned no row for order {razorpay_order_id}"
            )
            return None

        logger.info(f"Recorded payment intent for order {razorpay_order_id}")
        return data[0]

    async def get_by_order_id(self, razorpay_order_id: str) -> Optional[Dict[str, Any]]:
        """
        The intent for a Razorpay order, or None.

        None is an expected answer, not an error: orders created before this
        table existed have no intent row, and the callers fall back accordingly.
        """
        try:
            # maybe_single(): a missing intent is a value, not a PGRST116 to be
            # masked as a 500.
            response = await db_exec(self.db.table("payment_intents")\
                .select(INTENT_COLUMNS)\
                .eq("razorpay_order_id", razorpay_order_id)\
                .maybe_single())
        except Exception as e:
            logger.warning(
                f"Could not read payment intent for order {razorpay_order_id}: {e}"
            )
            return None

        intent = getattr(response, "data", None)
        if not intent:
            return None

        for key in ("pricing", "cart_snapshot", "time_slots"):
            if intent.get(key) is not None:
                intent[key] = _as_json_value(intent[key])

        return intent

    async def mark_captured(
        self,
        razorpay_order_id: str,
        *,
        razorpay_payment_id: str,
    ) -> None:
        """
        Record that Razorpay has the money, whether or not a booking exists yet.

        Status is left alone: `completed` is about our side of the transaction,
        and a capture with no booking is precisely the state reconciliation
        needs to be able to see.
        """
        await self._update(
            razorpay_order_id,
            {
                "razorpay_payment_id": razorpay_payment_id,
                "captured_at": "now()",
            },
            "captured",
        )

    async def mark_completed(
        self,
        razorpay_order_id: str,
        *,
        booking_id: Optional[str],
        razorpay_payment_id: Optional[str] = None,
    ) -> None:
        """Record that this intent became a booking."""
        updates: Dict[str, Any] = {
            "status": "completed",
            "booking_id": booking_id,
            "completed_at": "now()",
        }
        if razorpay_payment_id:
            updates["razorpay_payment_id"] = razorpay_payment_id
        await self._update(razorpay_order_id, updates, "completed")

    async def mark_failed(self, razorpay_order_id: str, *, reason: Optional[str]) -> None:
        """
        Record a gateway-reported failure.

        Guarded on `status = 'created'` so a late `payment.failed` for an order
        that was retried and paid cannot overwrite a completed booking.
        """
        await self._update(
            razorpay_order_id,
            {"status": "failed", "failure_reason": (reason or "")[:500]},
            "failed",
            only_while_created=True,
        )

    async def _update(
        self,
        razorpay_order_id: str,
        updates: Dict[str, Any],
        what: str,
        only_while_created: bool = False,
    ) -> None:
        """
        Apply a status update, logging rather than raising on failure.

        Every caller is on a path where the money has already moved and the
        booking is the thing that matters; losing a bookkeeping update must not
        turn a completed payment into an error response.
        """
        try:
            query = self.db.table("payment_intents").update(updates)\
                .eq("razorpay_order_id", razorpay_order_id)
            if only_while_created:
                query = query.eq("status", "created")
            await db_exec(query)
        except Exception as e:
            logger.error(
                f"Failed to mark payment intent {razorpay_order_id} as {what}: {e}"
            )
