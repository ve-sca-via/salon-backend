import logging
from typing import Dict, Any, List
from fastapi import HTTPException, status
from app.services.payment import razorpay_service
import uuid
import datetime

logger = logging.getLogger(__name__)

class ProductOrderService:
    def __init__(self, db_client):
        self.db = db_client

    async def create_order(self, user_id: str, order_data: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a new product order and a Razorpay order"""
        
        # 1. Calculate totals
        subtotal = sum(item['unit_price'] * item['quantity'] for item in items)
        discount_total = order_data.get('discount_total', 0.0)
        total_amount = subtotal - discount_total
        
        # Generate a unique order number
        order_number = f"ORD-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}-{str(uuid.uuid4())[:4].upper()}"

        try:
            from app.core.config import settings

            # Detect dev/placeholder credentials — skip real Razorpay call
            is_dev_mode = (
                not settings.is_production or
                not settings.RAZORPAY_KEY_ID or
                settings.RAZORPAY_KEY_ID.startswith("placeholder")
            )

            if is_dev_mode:
                # Use a fake Razorpay order ID for dev
                fake_rzp_order_id = f"dev_order_{uuid.uuid4().hex[:16]}"
                rzp_amount = float(total_amount)
                rzp_currency = "INR"
            else:
                rzp_order = razorpay_service.create_order(
                    amount=float(total_amount),
                    receipt=order_number,
                    notes={
                        "payment_type": "product_order",
                        "user_id": user_id,
                        "order_number": order_number
                    }
                )
                fake_rzp_order_id = rzp_order['order_id']
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
                "razorpay_order_id": fake_rzp_order_id,
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
            for item in items:
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
                "razorpay_order_id": fake_rzp_order_id,
                "amount": rzp_amount,
                "currency": rzp_currency,
                "dev_mode": is_dev_mode
            }

        except Exception as e:
            logger.error(f"Failed to create product order: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create order"
            )


    async def verify_payment(self, user_id: str, razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str) -> Dict[str, Any]:
        """Verify Razorpay payment signature and update order status"""
        
        try:
            # 1. Verify signature with Razorpay
            is_valid = razorpay_service.verify_payment_signature(
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
                detail=str(e)
            )

    async def dev_complete_order(self, user_id: str, order_id: str) -> Dict[str, Any]:
        """DEV ONLY: Mark order as paid without Razorpay verification"""
        try:
            import uuid
            update_data = {
                "status": "paid",
                "payment_status": "completed",
                "razorpay_payment_id": f"dev_pay_{uuid.uuid4().hex[:12]}",
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
                .select("id, full_name, phone")\
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
