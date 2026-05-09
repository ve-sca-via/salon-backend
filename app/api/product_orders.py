from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any, List
from pydantic import BaseModel
from app.core.auth import get_current_user, TokenData
from app.services.product_order_service import product_order_service

router = APIRouter(prefix="/product-orders", tags=["product-orders"])

class OrderItemSchema(BaseModel):
    product_id: str
    product_name: str
    quantity: int
    unit_price: float
    image_url: str = None

class CreateOrderRequest(BaseModel):
    shipping_address: Dict[str, Any]
    discount_total: float = 0.0
    items: List[OrderItemSchema]

class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str

@router.post("/create")
async def create_order(
    request: CreateOrderRequest,
    current_user: TokenData = Depends(get_current_user)
):
    """Create a new product order and get Razorpay order details"""
    order_data = {
        "shipping_address": request.shipping_address,
        "discount_total": request.discount_total
    }
    items_data = [item.dict() for item in request.items]
    
    return await product_order_service.create_order(
        user_id=current_user.user_id,
        order_data=order_data,
        items=items_data
    )

@router.post("/verify")
async def verify_payment(
    request: VerifyPaymentRequest,
    current_user: TokenData = Depends(get_current_user)
):
    """Verify Razorpay payment and mark order as paid"""
    return await product_order_service.verify_payment(
        user_id=current_user.user_id,
        razorpay_order_id=request.razorpay_order_id,
        razorpay_payment_id=request.razorpay_payment_id,
        razorpay_signature=request.razorpay_signature
    )

@router.get("/my-orders")
async def get_my_orders(
    current_user: TokenData = Depends(get_current_user)
):
    """Get all orders for the current user"""
    return await product_order_service.get_user_orders(user_id=current_user.user_id)
