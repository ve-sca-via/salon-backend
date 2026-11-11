from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, field_validator
from app.core.auth import get_current_user, TokenData
from app.core.validators import UUIDPath
from app.core.database import get_db_client
from app.services.product_order_service import ProductOrderService
from app.schemas.response.coupon import ProductCouponValidationResult, AvailableCouponResponse
from supabase import Client

router = APIRouter(prefix="/product-orders", tags=["product-orders"])

class OrderItemSchema(BaseModel):
    # Only product_id + quantity are honored — price/name/image are re-fetched
    # server-side from the products table to prevent client-side price tampering.
    product_id: str
    quantity: int = 1

class CreateOrderRequest(BaseModel):
    # `coupon_code` is only ever resolved against the server-computed subtotal
    # (PricingService.compute_product_order_pricing) — never trust a
    # client-supplied discount amount. A discount_total/total_amount field here
    # would reopen the "buy anything for ₹1" hole from docs/PAYMENT_FLOW_AUDIT.md
    # C-5, so only the code itself is accepted, same as the booking checkout.
    shipping_address: Dict[str, Any]
    items: List[OrderItemSchema]
    coupon_code: Optional[str] = Field(None, min_length=1, max_length=40)

    @field_validator("coupon_code")
    @classmethod
    def _normalize_coupon_code(cls, v):
        return v.strip().upper() if v else None

class ValidateCouponRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=40)
    items: List[OrderItemSchema]

    @field_validator("code")
    @classmethod
    def _normalize_code(cls, v: str) -> str:
        return v.strip().upper()

class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str

def get_product_order_service(db: Client = Depends(get_db_client)) -> ProductOrderService:
    """Dependency injection for ProductOrderService"""
    return ProductOrderService(db_client=db)

@router.post("/create")
async def create_order(
    request: CreateOrderRequest,
    current_user: TokenData = Depends(get_current_user),
    product_order_service: ProductOrderService = Depends(get_product_order_service)
):
    """Create a new product order and get Razorpay order details"""
    order_data = {
        "shipping_address": request.shipping_address
    }
    items_data = [item.model_dump() for item in request.items]

    return await product_order_service.create_order(
        user_id=current_user.user_id,
        order_data=order_data,
        items=items_data,
        coupon_code=request.coupon_code
    )

@router.post("/validate-coupon", response_model=ProductCouponValidationResult)
async def validate_coupon(
    request: ValidateCouponRequest,
    current_user: TokenData = Depends(get_current_user),
    product_order_service: ProductOrderService = Depends(get_product_order_service)
):
    """
    Preview a platform coupon against a would-be product order ("Apply coupon"
    button on /checkout/products). Does NOT redeem — redemption happens once
    the order is actually paid.
    """
    items_data = [item.model_dump() for item in request.items]
    return await product_order_service.validate_coupon(
        user_id=current_user.user_id,
        code=request.code,
        items=items_data
    )

@router.get("/available-coupons", response_model=List[AvailableCouponResponse])
async def list_available_coupons(
    current_user: TokenData = Depends(get_current_user),
    db: Client = Depends(get_db_client)
):
    """
    Platform coupons the current customer can discover and apply on the
    product checkout page ("available offers"). Always platform-wide — there
    is no vendor-owned product catalog to scope a coupon to.
    """
    from app.services.coupon_service import CouponService
    return await CouponService(db).list_available_product_coupons(current_user.user_id)

@router.post("/verify")
async def verify_payment(
    request: VerifyPaymentRequest,
    current_user: TokenData = Depends(get_current_user),
    product_order_service: ProductOrderService = Depends(get_product_order_service)
):
    """Verify Razorpay payment and mark order as paid"""
    return await product_order_service.verify_payment(
        user_id=current_user.user_id,
        razorpay_order_id=request.razorpay_order_id,
        razorpay_payment_id=request.razorpay_payment_id,
        razorpay_signature=request.razorpay_signature
    )

@router.post("/dev-verify/{order_id}")
async def dev_verify_payment(
    order_id: UUIDPath,
    current_user: TokenData = Depends(get_current_user),
    product_order_service: ProductOrderService = Depends(get_product_order_service)
):
    """
    DEV ONLY: Simulate a successful payment without real Razorpay credentials.
    Marks the order as paid directly. Returns 403 in production.
    """
    from app.core.config import settings
    if settings.is_production:
        raise HTTPException(status_code=403, detail="Not available in production")
    return await product_order_service.dev_complete_order(
        user_id=current_user.user_id,
        order_id=order_id
    )

@router.get("/my-orders")
async def get_my_orders(
    current_user: TokenData = Depends(get_current_user),
    product_order_service: ProductOrderService = Depends(get_product_order_service)
):
    """Get all orders for the current user"""
    return await product_order_service.get_user_orders(user_id=current_user.user_id)

@router.get("/{order_id}")
async def get_order(
    order_id: UUIDPath,
    current_user: TokenData = Depends(get_current_user),
    product_order_service: ProductOrderService = Depends(get_product_order_service)
):
    """
    Get a single product order belonging to the current user.

    Defined after /my-orders: a path-param route registered before a literal one
    would shadow it (FastAPI/Starlette match in registration order).
    """
    order = await product_order_service.get_order_by_id(
        user_id=current_user.user_id, order_id=order_id
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order
