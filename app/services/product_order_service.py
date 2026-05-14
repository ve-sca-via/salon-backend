import logging
from typing import Dict, Any, List
from fastapi import HTTPException, status
import uuid
import datetime

logger = logging.getLogger(__name__)

class ProductOrderService:
    def __init__(self, db_client):
        self.db = db_client

    async def _get_razorpay_creds(self):
        """Fetch Razorpay credentials from database or environment"""
        from app.services.config_service import ConfigService
        from app.core.config import settings
        
        db_key_id = None
        db_key_secret = None
        
        try:
            config_service = ConfigService(self.db)
            db_key_id = await config_service.get_config_value("razorpay_key_id")
            db_key_secret = await config_service.get_config_value("razorpay_key_secret")
        except Exception:
            pass

        key_id = db_key_id or settings.RAZORPAY_KEY_ID
        key_secret = db_key_secret or settings.RAZORPAY_KEY_SECRET
        
        is_placeholder = (
            not key_id or not key_secret or 
            key_id.startswith("placeholder") or 
            key_secret.startswith("placeholder")
        )
        
        return key_id, key_secret, is_placeholder

    async def create_order(self, user_id: str, order_data: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a new product order and a Razorpay order"""
        
        # 1. Fetch user role for price validation
        profile_resp = self.db.table("profiles").select("user_role").eq("id", user_id).single().execute()
        user_role = profile_resp.data.get("user_role") if profile_resp.data else "customer"
        is_b2b = user_role in ['vendor', 'regular_buyer']

        # 2. Validate items and prices
        product_ids = [item['product_id'] for item in items]
        products_resp = self.db.table("products").select("*").in_("id", product_ids).execute()
        products_map = {p['id']: p for p in products_resp.data or []}

        validated_items = []
        subtotal = 0.0

        for item in items:
            product_id = item['product_id']
            if product_id not in products_map:
                raise HTTPException(status_code=400, detail=f"Product not found: {product_id}")
            
            product = products_map[product_id]
            
            # Determine correct price based on role
            db_price = product.get("discount_price") or product.get("price") or 0.0
            if is_b2b and product.get('b2b_discount_price') is not None:
                db_price = product['b2b_discount_price']
            
            # Force the DB price to prevent tampering
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

        discount_total = order_data.get('discount_total', 0.0)
        total_amount = subtotal - discount_total
        
        if total_amount < 1: # Razorpay minimum
            total_amount = 1.0

        # Generate a unique order number
        order_number = f"ORD-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}-{str(uuid.uuid4())[:4].upper()}"

        try:
            from app.core.config import settings
            from app.services.payment import RazorpayService

            key_id, key_secret, is_dev_mode = await self._get_razorpay_creds()

            if is_dev_mode:
                # Simulation mode: Use a fake Razorpay order ID
                logger.info(f"Using simulation mode for order {order_number} (invalid/placeholder credentials)")
                razorpay_order_id = f"dev_order_{uuid.uuid4().hex[:16]}"
                rzp_amount = float(total_amount)
                rzp_currency = "INR"
            else:
                # Real Razorpay mode: Initialize service with current keys
                temp_rzp_service = RazorpayService(razorpay_key_id=key_id, razorpay_key_secret=key_secret)
                
                rzp_order = temp_rzp_service.create_order(
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
                "payment_status": "pending"
            }
            
            order_response = self.db.table("product_orders").insert(order_insert_data).execute()
            
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
                
            self.db.table("product_order_items").insert(order_items_data).execute()

            return {
                "order": order_row,
                "razorpay_order_id": razorpay_order_id,
                "amount": rzp_amount,
                "currency": rzp_currency,
                "key_id": key_id,
                "dev_mode": is_dev_mode
            }

        except Exception as e:
            logger.error(f"Failed to create product order: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e) if not isinstance(e, HTTPException) else e.detail
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
            result = self.db.table("product_orders").update(update_data)\
                .eq("id", order_id)\
                .eq("user_id", user_id).execute()

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
            raise HTTPException(status_code=500, detail=str(e))


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
                "updated_at": "now()"
            }
            
            result = self.db.table("product_orders").update(update_data)\
                .eq("razorpay_order_id", razorpay_order_id)\
                .eq("user_id", user_id).execute()

            if not result.data:
                raise HTTPException(status_code=404, detail="Order not found")

            return {
                "success": True,
                "order_id": result.data[0]['id'],
                "order_number": result.data[0]['order_number']
            }

        except Exception as e:
            logger.error(f"Failed to verify payment: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e) if not isinstance(e, HTTPException) else e.detail
            )

    async def get_user_orders(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all product orders for a user"""
        try:
            orders_response = self.db.table("product_orders").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
            orders = orders_response.data or []
            
            result = []
            for order in orders:
                items_response = self.db.table("product_order_items").select("*").eq("order_id", order['id']).execute()
                order['items'] = items_response.data or []
                result.append(order)
                
            return result
        except Exception as e:
            logger.error(f"Error fetching user orders: {e}")
            return []

    async def get_all_orders(self) -> List[Dict[str, Any]]:
        """Get all product orders for admin"""
        try:
            logger.info("Fetching all product orders for admin...")
            # 1. Fetch all orders
            orders_response = self.db.table("product_orders")\
                .select("*")\
                .order("created_at", desc=True)\
                .execute()
            
            orders = orders_response.data or []
            logger.info(f"Found {len(orders)} orders in database")
            
            if not orders:
                return []

            # 2. Collect all unique user IDs
            user_ids = list(set(order['user_id'] for order in orders))
            
            # 3. Fetch profiles for these users
            profiles_response = self.db.table("profiles")\
                .select("id, full_name, phone, user_role")\
                .in_("id", user_ids)\
                .execute()
            
            profiles_map = {p['id']: p for p in profiles_response.data or []}
            
            result = []
            for order in orders:
                # Add profile data
                order['profiles'] = profiles_map.get(order['user_id'])
                
                # Fetch items for this order
                items_response = self.db.table("product_order_items")\
                    .select("*")\
                    .eq("order_id", order['id'])\
                    .execute()
                order['items'] = items_response.data or []
                result.append(order)
                
            return result
        except Exception as e:
            logger.error(f"Error fetching all orders: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def update_order_status(self, order_id: str, status: str) -> Dict[str, Any]:
        """Update order status (e.g., shipped, delivered, cancelled)"""
        try:
            update_data = {
                "status": status,
                "updated_at": "now()"
            }
            
            result = self.db.table("product_orders").update(update_data)\
                .eq("id", order_id).execute()

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
            raise HTTPException(status_code=500, detail=str(e))
