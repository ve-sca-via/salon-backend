import logging
from typing import Dict, Any, List, Optional
from fastapi import HTTPException, status
import uuid
import datetime

from app.services.product_service import effective_unit_price
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

    async def create_order(self, user_id: str, order_data: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a new product order and a Razorpay order"""
        
        # 1. Fetch user role for price validation
        profile_resp = await db_exec(self.db.table("profiles").select("user_role").eq("id", user_id).single())
        user_role = profile_resp.data.get("user_role") if profile_resp.data else "customer"

        # 2. Validate items and prices
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

            # Force the DB price to prevent client-side tampering (shared with cart)
            db_price = effective_unit_price(product, user_role)

            item_qty = item.get('quantity', 1)
            item_total = db_price * item_qty
            subtotal += item_total
            
            validated_items.append({
                "product_id": product_id,
                "product_name": product['name'],
                "quantity": item_qty,
                "unit_price": db_price,
                "image_url": product.get('image_urls', [None])[0] if product.get('image_urls') else None
            })

        # Product orders have no discount/coupon flow, so the total IS the
        # server-computed subtotal. This used to subtract a client-supplied
        # `discount_total`, which made every order payable for ₹1 (audit C-5).
        # The column is kept at 0 so the row shape is unchanged.
        discount_total = 0.0
        total_amount = subtotal

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
