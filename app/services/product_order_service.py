import logging
from typing import Dict, Any, List, Optional
from fastapi import HTTPException, status
import uuid
import datetime

from app.services.product_service import effective_unit_price, is_b2b_role
from app.core.database import db_exec

logger = logging.getLogger(__name__)

# Allowed order lifecycle states (kept in sync with the admin route's Literal
# and the product_orders table comment).
VALID_ORDER_STATUSES = {"pending", "paid", "shipped", "delivered", "cancelled"}

class ProductOrderService:
    def __init__(self, db_client):
        self.db = db_client

    async def _get_razorpay_creds(self):
        """Fetch Razorpay credentials from database (with env fallback for dev mode)"""
        from app.services.config_service import ConfigService
        from app.services.payment import resolve_razorpay_credentials

        config_service = ConfigService(self.db)
        key_id, key_secret = await resolve_razorpay_credentials(
            config_service, allow_env_fallback=True
        )

        is_placeholder = (
            not key_id or not key_secret or
            key_id.startswith("placeholder") or
            key_secret.startswith("placeholder")
        )

        return key_id, key_secret, is_placeholder

    async def _price_items(self, user_role: str, items: List[Dict[str, Any]]) -> tuple:
        """
        Validate items (exist, active, in stock) and price them server-side.

        Shared by create_order and validate_coupon so the subtotal a coupon is
        previewed against is computed exactly the way create_order will compute
        it moments later. Returns (validated_items, subtotal). Raises
        HTTPException on any invalid item — never silently drops one.
        """
        product_ids = [item['product_id'] for item in items]
        products_resp = await db_exec(self.db.table("products").select("*").in_("id", product_ids))
        products_map = {p['id']: p for p in products_resp.data or []}

        validated_items = []
        subtotal = 0.0

        for item in items:
            product_id = item['product_id']
            if product_id not in products_map:
                raise HTTPException(status_code=400, detail=f"Product not found: {product_id}")

            product = products_map[product_id]

            if not product.get('is_active', True):
                raise HTTPException(
                    status_code=400,
                    detail=f"\"{product['name']}\" is no longer available."
                )

            item_qty = item.get('quantity', 1)

            # Reject up front, before taking any payment. This doesn't close the
            # race between two concurrent checkouts on the last unit — that's
            # caught at payment time by decrement_product_stock — but it does
            # catch the common case of someone ordering more than currently exists.
            available = product.get('stock_quantity')
            if available is not None and item_qty > available:
                raise HTTPException(
                    status_code=400,
                    detail=f"Only {available} unit(s) of \"{product['name']}\" left in stock."
                )

            # Force the DB price to prevent client-side tampering (shared with cart)
            db_price = effective_unit_price(product, user_role)

            item_total = db_price * item_qty
            subtotal += item_total

            validated_items.append({
                "product_id": product_id,
                "product_name": product['name'],
                "quantity": item_qty,
                "unit_price": db_price,
                "image_url": product.get('image_urls', [None])[0] if product.get('image_urls') else None
            })

        return validated_items, round(subtotal, 2)

    async def validate_coupon(self, user_id: str, code: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Preview a platform product coupon against a would-be order ("Apply
        coupon" button on /checkout/products). Does NOT redeem — redemption
        happens at payment-captured time. Mirrors CustomerService.validate_coupon's
        shape but for products (no convenience fee, no salon-sale best-of).
        """
        from app.services.pricing_service import PricingService

        profile_resp = await db_exec(self.db.table("profiles").select("user_role").eq("id", user_id).single())
        user_role = profile_resp.data.get("user_role") if profile_resp.data else "customer"

        _, subtotal = await self._price_items(user_role, items)

        pricing = await PricingService(self.db).compute_product_order_pricing(
            subtotal=subtotal,
            customer_id=user_id,
            coupon_code=code,
        )

        if not pricing["coupon_id"]:
            return {
                "valid": False,
                "reason": pricing["coupon_reason"] or "This coupon could not be applied.",
                "coupon_id": None,
                "coupon_code": None,
                "breakdown": None,
            }

        return {
            "valid": True,
            "reason": None,
            "coupon_id": pricing["coupon_id"],
            "coupon_code": pricing["coupon_code"],
            "breakdown": {
                "subtotal": pricing["subtotal"],
                "discount_amount": pricing["discount_amount"],
                "total_amount": pricing["total_amount"],
            },
        }

    async def create_order(
        self,
        user_id: str,
        order_data: Dict[str, Any],
        items: List[Dict[str, Any]],
        coupon_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new product order and a Razorpay order"""

        # 1. Fetch user role for price validation
        profile_resp = await db_exec(self.db.table("profiles").select("user_role").eq("id", user_id).single())
        user_role = profile_resp.data.get("user_role") if profile_resp.data else "customer"

        # B2B accounts (vendor, regular_buyer) owe a one-time registration fee
        # before they can buy — the activation email says so, but nothing used
        # to enforce it. Fail open if there's no salon row to check: that's an
        # inconsistent account state, not a reason to block every B2B order.
        if is_b2b_role(user_role):
            salon_resp = await db_exec(
                self.db.table("salons")
                # `salons` has no registration_fee_amount column (selecting it
                # 500'd every B2B order — 42703). The amount owed is resolved
                # the same way checkout does: per-account override, else the
                # global default for the salon_type.
                .select("registration_fee_paid, salon_type, custom_registration_fee_amount")
                .eq("vendor_id", user_id)
                .maybe_single()
            )
            salon = salon_resp.data if salon_resp else None
            if salon and not salon.get("registration_fee_paid"):
                from app.services.config_service import ConfigService

                try:
                    fee = await ConfigService(self.db).get_registration_fee_for_salon(salon)
                except ValueError:
                    # Missing fee config must not turn the gate into a 500;
                    # still block, just without quoting an amount.
                    logger.warning("Registration fee config missing; gating order without amount")
                    fee = None
                fee_text = f" (₹{fee:,.0f})" if fee else ""
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Please complete your registration payment{fee_text} before ordering products."
                )

        # 2. Validate items and prices
        validated_items, subtotal = await self._price_items(user_role, items)

        # 3. Resolve an optional platform coupon against the server-computed
        # subtotal (never trust a client-supplied discount — see audit C-5).
        # A platform coupon is the only kind that can ever apply here (products
        # are admin-managed; see get_valid_product_coupon). An invalid/expired
        # code is not a hard error — the order proceeds without a discount, and
        # the reason is surfaced back for the frontend to toast.
        from app.services.pricing_service import PricingService

        pricing = await PricingService(self.db).compute_product_order_pricing(
            subtotal=subtotal,
            customer_id=user_id,
            coupon_code=coupon_code,
        )
        discount_total = pricing["discount_amount"]
        total_amount = pricing["total_amount"]
        applied_coupon_id = pricing["coupon_id"]
        applied_coupon_code = pricing["coupon_code"]
        coupon_reason = pricing["coupon_reason"]

        if total_amount < 1: # Razorpay minimum
            total_amount = 1.0

        # Generate a unique order number
        order_number = f"ORD-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}-{str(uuid.uuid4())[:4].upper()}"

        try:
            from app.services.payment import RazorpayService

            key_id, key_secret, is_dev_mode = await self._get_razorpay_creds()

            # amount is in rupees; amount_paise is the smallest-unit value the
            # Razorpay checkout expects (matches payment_service's cart order).
            rzp_amount = float(total_amount)
            rzp_amount_paise = int(round(total_amount * 100))

            if is_dev_mode:
                # Simulation mode: Use a fake Razorpay order ID
                logger.info(f"Using simulation mode for order {order_number} (invalid/placeholder credentials)")
                razorpay_order_id = f"dev_order_{uuid.uuid4().hex[:16]}"
                rzp_currency = "INR"
            else:
                # Real Razorpay mode: Initialize service with current keys
                temp_rzp_service = RazorpayService(razorpay_key_id=key_id, razorpay_key_secret=key_secret)

                rzp_order = await temp_rzp_service.create_order(
                    amount=float(total_amount),
                    receipt=order_number,
                    notes={
                        "payment_type": "product_order",
                        "user_id": user_id,
                        "order_number": order_number
                    }
                )
                razorpay_order_id = rzp_order['order_id']
                rzp_amount = rzp_order['amount']
                rzp_amount_paise = rzp_order['amount_paise']
                rzp_currency = rzp_order['currency']

            # 3. Insert order into database
            order_insert_data = {
                "user_id": user_id,
                "order_number": order_number,
                "subtotal": subtotal,
                "discount_total": discount_total,
                "total_amount": total_amount,
                "coupon_id": applied_coupon_id,
                "coupon_code": applied_coupon_code,
                "shipping_address": order_data.get('shipping_address'),
                "razorpay_order_id": razorpay_order_id,
                "status": "pending",
                "payment_status": "pending",
                "user_type": user_role
            }
            
            order_response = await db_exec(self.db.table("product_orders").insert(order_insert_data))
            
            if not order_response.data:
                raise Exception("Failed to insert order into database")
                
            order_row = order_response.data[0]
            order_id = order_row['id']

            # 4. Insert order items
            order_items_data = []
            for item in validated_items:
                order_items_data.append({
                    "order_id": order_id,
                    "product_id": item['product_id'],
                    "product_name": item['product_name'],
                    "quantity": item['quantity'],
                    "unit_price": item['unit_price'],
                    "total_price": item['unit_price'] * item['quantity'],
                    "image_url": item.get('image_url')
                })
                
            await db_exec(self.db.table("product_order_items").insert(order_items_data))

            return {
                "order": order_row,
                "razorpay_order_id": razorpay_order_id,
                "amount": rzp_amount,
                "amount_paise": rzp_amount_paise,
                "currency": rzp_currency,
                "key_id": key_id,
                "coupon_reason": coupon_reason,
                "dev_mode": is_dev_mode
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to create product order: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create order"
            )

    async def _decrement_stock_for_order(self, order_id: str) -> None:
        """
        Best-effort, idempotent stock decrement for a just-paid order (RPC
        `decrement_product_stock`, migration 20261103000000).

        Called after an order is marked paid, from all three paths that can do
        that (browser verify, dev-verify, webhook) — any of which can fire more
        than once for the same order, which is why the RPC itself is the thing
        guaranteeing "exactly once", not this caller.

        Payment is already captured by the time this runs, so a failure here
        (a genuine oversell race) is logged, not raised — there is no good way
        to un-charge the buyer from inside this call.
        """
        try:
            await db_exec(self.db.rpc("decrement_product_stock", {"p_order_id": order_id}))
        except Exception as e:
            logger.error(f"Stock decrement failed for order {order_id}: {e}")

    async def _redeem_coupon_for_order(self, order: Dict[str, Any]) -> None:
        """
        Redeem the coupon applied at create_order time, now that the order is
        paid (same D2 decision as bookings: redeem only on paid, never at
        creation). Idempotent via redeem_product_coupon()'s own guard, so this
        can safely run again if verify_payment/dev_complete_order/the webhook
        race or retry for the same order — same pattern as stock decrement.

        No-op when the order carries no coupon.
        """
        coupon_id = order.get("coupon_id")
        if not coupon_id:
            return
        try:
            from app.services.coupon_service import CouponService

            result = await CouponService(self.db).redeem_product(
                coupon_id=coupon_id,
                user_id=order["user_id"],
                product_order_id=order["id"],
                discount_amount=order.get("discount_total") or 0,
            )
            if not result.get("success"):
                logger.warning(
                    f"Coupon redemption did not succeed for order {order.get('order_number')}: "
                    f"{result.get('reason')}"
                )
        except Exception as e:
            logger.error(f"Coupon redemption failed for order {order.get('id')}: {e}")

    async def dev_complete_order(self, user_id: str, order_id: str) -> Dict[str, Any]:
        """DEV ONLY: Mark order as paid without Razorpay verification"""
        try:
            update_data = {
                "status": "paid",
                "payment_status": "completed",
                "razorpay_payment_id": f"dev_pay_{uuid.uuid4().hex[:12]}",
                "updated_at": datetime.datetime.now().isoformat()
            }
            result = await db_exec(self.db.table("product_orders").update(update_data)\
                .eq("id", order_id)\
                .eq("user_id", user_id))

            if not result.data:
                raise HTTPException(status_code=404, detail="Order not found")

            await self._decrement_stock_for_order(result.data[0]["id"])
            await self._redeem_coupon_for_order(result.data[0])

            return {
                "success": True,
                "order_id": result.data[0]["id"],
                "order_number": result.data[0]["order_number"],
                "dev_mode": True
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Dev complete order failed: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to complete order")


    async def verify_payment(self, user_id: str, razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str) -> Dict[str, Any]:
        """Verify Razorpay payment signature and update order status"""
        
        try:
            from app.services.payment import RazorpayService
            
            # Use same credentials as creation
            key_id, key_secret, _ = await self._get_razorpay_creds()
            temp_rzp_service = RazorpayService(razorpay_key_id=key_id, razorpay_key_secret=key_secret)

            # 1. Verify signature with Razorpay
            is_valid = temp_rzp_service.verify_payment_signature(
                razorpay_order_id=razorpay_order_id,
                razorpay_payment_id=razorpay_payment_id,
                razorpay_signature=razorpay_signature
            )

            if not is_valid:
                raise HTTPException(status_code=400, detail="Invalid payment signature")

            # 2. Update order status in DB
            update_data = {
                "status": "paid",
                "payment_status": "completed",
                "razorpay_payment_id": razorpay_payment_id,
                "updated_at": datetime.datetime.now().isoformat()
            }

            result = await db_exec(self.db.table("product_orders").update(update_data)\
                .eq("razorpay_order_id", razorpay_order_id)\
                .eq("user_id", user_id))

            if not result.data:
                raise HTTPException(status_code=404, detail="Order not found")

            await self._decrement_stock_for_order(result.data[0]['id'])
            await self._redeem_coupon_for_order(result.data[0])

            return {
                "success": True,
                "order_id": result.data[0]['id'],
                "order_number": result.data[0]['order_number']
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to verify payment: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to verify payment"
            )

    async def mark_order_paid_from_webhook(
        self, razorpay_order_id: str, razorpay_payment_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Mark a product order paid from the `payment.captured` webhook.

        The browser path (`verify_payment`) proves the payment with an
        order|payment signature and scopes the update to the signed-in user. A
        webhook has neither: its proof is the HMAC over the webhook body, already
        verified by the caller, and there is no session to scope to — so the order
        id alone identifies the row.

        Guarded on `payment_status = 'pending'`, which also means a webhook cannot
        resurrect an order someone has since cancelled.

        Returns the updated order, or None when there was nothing pending to
        update (already paid, cancelled, or no such order).
        """
        try:
            result = await db_exec(self.db.table("product_orders").update({
                "status": "paid",
                "payment_status": "completed",
                "razorpay_payment_id": razorpay_payment_id,
                "updated_at": datetime.datetime.now().isoformat()
            })\
                .eq("razorpay_order_id", razorpay_order_id)\
                .eq("payment_status", "pending"))

            if not result.data:
                return None

            order = result.data[0]
            logger.info(
                f"Product order {order.get('order_number')} marked paid by webhook "
                f"(payment {razorpay_payment_id})"
            )
            await self._decrement_stock_for_order(order["id"])
            await self._redeem_coupon_for_order(order)
            return order
        except Exception as e:
            logger.error(
                f"Failed to mark product order paid from webhook for order "
                f"{razorpay_order_id}: {e}"
            )
            raise

    async def find_by_razorpay_order_id(self, razorpay_order_id: str) -> Optional[Dict[str, Any]]:
        """
        The product order behind a Razorpay order, or None.

        Used by the webhook to decide which flow a captured payment belongs to.
        """
        try:
            response = await db_exec(self.db.table("product_orders")\
                .select("id, order_number, user_id, status, payment_status, razorpay_payment_id")\
                .eq("razorpay_order_id", razorpay_order_id)\
                .maybe_single())
            return getattr(response, "data", None) or None
        except Exception as e:
            logger.warning(
                f"Could not look up product order for Razorpay order {razorpay_order_id}: {e}"
            )
            return None

    async def get_order_by_id(self, user_id: str, order_id: str) -> Optional[Dict[str, Any]]:
        """
        A single product order with its line items, scoped to its owner.

        Backs `/order-confirmation`'s refresh/direct-link fallback — the
        sessionStorage handoff from checkout is per-viewer only, so a refresh or
        a shared link needs a real way to refetch by id.
        """
        try:
            order_resp = await db_exec(
                self.db.table("product_orders").select("*")
                .eq("id", order_id).eq("user_id", user_id).maybe_single()
            )
            order = order_resp.data if order_resp else None
            if not order:
                return None

            items_resp = await db_exec(
                self.db.table("product_order_items").select("*").eq("order_id", order_id)
            )
            order["items"] = items_resp.data or []
            return order
        except Exception as e:
            logger.error(f"Error fetching product order {order_id}: {e}")
            return None

    async def get_user_orders(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all product orders for a user"""
        try:
            orders_response = await db_exec(self.db.table("product_orders").select("*").eq("user_id", user_id).order("created_at", desc=True))
            orders = orders_response.data or []
            if not orders:
                return []

            # Fetch all line items in one query, then group by order_id
            order_ids = [o['id'] for o in orders]
            items_response = await db_exec(self.db.table("product_order_items").select("*").in_("order_id", order_ids))
            items_by_order: Dict[str, List[Dict[str, Any]]] = {}
            for it in items_response.data or []:
                items_by_order.setdefault(it['order_id'], []).append(it)

            for order in orders:
                order['items'] = items_by_order.get(order['id'], [])

            return orders
        except Exception as e:
            logger.error(f"Error fetching user orders: {e}")
            return []

    async def get_all_orders(self) -> List[Dict[str, Any]]:
        """Get all product orders for admin"""
        try:
            logger.info("Fetching all product orders for admin...")
            # 1. Fetch all orders
            orders_response = await db_exec(self.db.table("product_orders")\
                .select("*")\
                .order("created_at", desc=True))
            
            orders = orders_response.data or []
            logger.info(f"Found {len(orders)} orders in database")
            
            if not orders:
                return []

            # 2. Collect all unique user IDs
            user_ids = list(set(order['user_id'] for order in orders))
            
            # 3. Fetch profiles for these users
            profiles_response = await db_exec(self.db.table("profiles")\
                .select("id, full_name, phone, user_role")\
                .in_("id", user_ids))
            
            profiles_map = {p['id']: p for p in profiles_response.data or []}

            # 4. Fetch all line items in one query, then group by order_id
            order_ids = [order['id'] for order in orders]
            items_response = await db_exec(self.db.table("product_order_items")\
                .select("*")\
                .in_("order_id", order_ids))
            items_by_order: Dict[str, List[Dict[str, Any]]] = {}
            for it in items_response.data or []:
                items_by_order.setdefault(it['order_id'], []).append(it)

            result = []
            for order in orders:
                order['profiles'] = profiles_map.get(order['user_id'])
                order['items'] = items_by_order.get(order['id'], [])
                result.append(order)

            return result
        except Exception as e:
            logger.error(f"Error fetching all orders: {e}")
            raise HTTPException(status_code=500, detail="Failed to fetch orders")

    async def update_order_status(self, order_id: str, status: str) -> Dict[str, Any]:
        """Update order status (e.g., shipped, delivered, cancelled)"""
        if status not in VALID_ORDER_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid order status")
        try:
            update_data = {
                "status": status,
                "updated_at": datetime.datetime.now().isoformat()
            }

            result = await db_exec(self.db.table("product_orders").update(update_data)\
                .eq("id", order_id))

            if not result.data:
                raise HTTPException(status_code=404, detail="Order not found")

            return {
                "success": True,
                "order": result.data[0]
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to update order status: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to update order status")
