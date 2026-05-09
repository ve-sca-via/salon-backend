import logging
from typing import Dict, Any, List
from fastapi import HTTPException, status
from app.core.database import get_db_connection
from app.services.payment import razorpay_service
import uuid
import datetime

logger = logging.getLogger(__name__)

class ProductOrderService:
    async def create_order(self, user_id: str, order_data: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a new product order and a Razorpay order"""
        
        # 1. Calculate totals
        subtotal = sum(item['unit_price'] * item['quantity'] for item in items)
        discount_total = order_data.get('discount_total', 0.0)
        total_amount = subtotal - discount_total
        
        # Generate a unique order number
        order_number = f"ORD-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}-{str(uuid.uuid4())[:4].upper()}"

        try:
            async with get_db_connection() as db:
                # 2. Create Razorpay order
                # total_amount is in INR, Razorpay takes INR and converts to paise in create_order
                rzp_order = razorpay_service.create_order(
                    amount=float(total_amount),
                    receipt=order_number,
                    notes={
                        "payment_type": "product_order",
                        "user_id": user_id,
                        "order_number": order_number
                    }
                )

                # 3. Insert order into database
                result = await db.execute("""
                    INSERT INTO product_orders (
                        user_id, order_number, subtotal, discount_total, total_amount,
                        shipping_address, razorpay_order_id, status, payment_status
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending', 'pending')
                    RETURNING id, order_number, total_amount, status, razorpay_order_id, created_at
                """, user_id, order_number, subtotal, discount_total, total_amount,
                    order_data.get('shipping_address'), rzp_order['order_id'])
                
                order_row = dict(result[0])
                order_id = order_row['id']

                # 4. Insert order items
                for item in items:
                    await db.execute("""
                        INSERT INTO product_order_items (
                            order_id, product_id, product_name, quantity, unit_price, total_price, image_url
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """, order_id, item['product_id'], item['product_name'], item['quantity'], 
                        item['unit_price'], item['unit_price'] * item['quantity'], item.get('image_url'))

                return {
                    "order": order_row,
                    "razorpay_order_id": rzp_order['order_id'],
                    "amount": rzp_order['amount'],
                    "currency": rzp_order['currency']
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
            async with get_db_connection() as db:
                result = await db.execute("""
                    UPDATE product_orders
                    SET status = 'paid', payment_status = 'completed', razorpay_payment_id = $1, updated_at = now()
                    WHERE razorpay_order_id = $2 AND user_id = $3
                    RETURNING id, order_number, status
                """, razorpay_payment_id, razorpay_order_id, user_id)

                if not result:
                    raise HTTPException(status_code=404, detail="Order not found")

                return {
                    "success": True,
                    "order_id": result[0]['id'],
                    "order_number": result[0]['order_number']
                }

        except Exception as e:
            logger.error(f"Failed to verify payment: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )

    async def get_user_orders(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all product orders for a user"""
        async with get_db_connection() as db:
            orders = await db.execute("""
                SELECT * FROM product_orders
                WHERE user_id = $1
                ORDER BY created_at DESC
            """, user_id)
            
            result = []
            for order in orders:
                order_dict = dict(order)
                # Fetch items
                items = await db.execute("""
                    SELECT * FROM product_order_items
                    WHERE order_id = $1
                """, order['id'])
                order_dict['items'] = [dict(item) for item in items]
                result.append(order_dict)
                
            return result

product_order_service = ProductOrderService()
