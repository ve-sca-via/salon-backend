from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Literal, Optional
from app.core.auth import require_admin, TokenData
from app.core.database import get_db_client
from app.core.validators import UUIDPath
from app.schemas.request.base import PartialUpdateModel
from app.services.product_order_service import ProductOrderService
from supabase import Client

router = APIRouter()

class UpdateStatusRequest(BaseModel):
    # The full enum stays accepted so the contract is unchanged; which moves are
    # actually allowed is enforced by ProductOrderService (ALLOWED_TRANSITIONS).
    status: Literal["pending", "paid", "shipped", "delivered", "cancelled"]
    courier_name: Optional[str] = Field(None, max_length=100)
    tracking_number: Optional[str] = Field(None, max_length=100)
    tracking_url: Optional[str] = Field(None, max_length=500)
    # Only read when cancelling: return the order's units to stock.
    restock: bool = True
    note: Optional[str] = Field(None, max_length=500)


class UpdateShipmentRequest(PartialUpdateModel):
    """Blank = untouched, null = clear (docs/PARTIAL_UPDATES.md)."""
    courier_name: Optional[str] = Field(None, max_length=100)
    tracking_number: Optional[str] = Field(None, max_length=100)
    tracking_url: Optional[str] = Field(None, max_length=500)


def get_product_order_service(db: Client = Depends(get_db_client)) -> ProductOrderService:
    """Dependency injection for ProductOrderService"""
    return ProductOrderService(db_client=db)

@router.get("/")
async def get_all_orders(
    product_order_service: ProductOrderService = Depends(get_product_order_service)
):
    """Get all product orders for admin"""
    return await product_order_service.get_all_orders()

@router.patch("/{order_id}/status")
async def update_order_status(
    order_id: UUIDPath,
    request: UpdateStatusRequest,
    current_user: TokenData = Depends(require_admin),
    product_order_service: ProductOrderService = Depends(get_product_order_service)
):
    """
    Move an order to its next status.

    Allowed: pending→cancelled, paid→shipped/delivered/cancelled,
    shipped→delivered/cancelled. `paid` is set only by the payment flow.
    Cancelling a paid order returns its units to stock (unless `restock` is
    false) but does not refund — `refund_required` says when to refund in Razorpay.
    """
    return await product_order_service.update_order_status(
        order_id=order_id,
        status=request.status,
        actor_id=current_user.user_id,
        courier_name=request.courier_name,
        tracking_number=request.tracking_number,
        tracking_url=request.tracking_url,
        restock=request.restock,
        note=request.note,
    )


@router.patch("/{order_id}/shipment")
async def update_order_shipment(
    order_id: UUIDPath,
    request: UpdateShipmentRequest,
    current_user: TokenData = Depends(require_admin),
    product_order_service: ProductOrderService = Depends(get_product_order_service)
):
    """Set or correct courier / tracking details without changing the status."""
    return await product_order_service.update_shipment(
        order_id, request.model_dump(exclude_unset=True), actor_id=current_user.user_id
    )


@router.get("/{order_id}/events")
async def get_order_events(
    order_id: UUIDPath,
    product_order_service: ProductOrderService = Depends(get_product_order_service)
):
    """The order's timeline: admin status changes and delivery-partner updates."""
    return {"events": await product_order_service.get_order_events(order_id)}
