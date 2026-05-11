from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any, List
from pydantic import BaseModel
from app.core.auth import require_admin
from app.core.database import get_db_client
from app.services.product_order_service import ProductOrderService
from supabase import Client

router = APIRouter()

class UpdateStatusRequest(BaseModel):
    status: str

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
    order_id: str,
    request: UpdateStatusRequest,
    product_order_service: ProductOrderService = Depends(get_product_order_service)
):
    """Update order status"""
    return await product_order_service.update_order_status(
        order_id=order_id,
        status=request.status
    )
