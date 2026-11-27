"""
Admin inventory endpoints — stock ledger for the central warehouse.

    POST /admin/inventory/{product_id}/adjust     restock / damaged / correction
    GET  /admin/inventory/{product_id}/movements  that product's stock history

Stock levels themselves are on the product (`stock_quantity`, listed by
GET /products/admin/all). See app/services/inventory_service.py.
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from supabase import Client

from app.core.auth import require_admin, TokenData
from app.core.database import get_db_client
from app.core.validators import UUIDPath
from app.services.inventory_service import InventoryService

router = APIRouter()


class StockAdjustRequest(BaseModel):
    # Positive adds units, negative removes them. 'damaged' must be negative,
    # 'restock' positive; 'adjustment' (a count correction) either way.
    change: int = Field(..., ge=-100000, le=100000)
    reason: Literal["restock", "adjustment", "damaged"]
    note: Optional[str] = Field(None, max_length=500)


def get_inventory_service(db: Client = Depends(get_db_client)) -> InventoryService:
    return InventoryService(db)


@router.post("/{product_id}/adjust")
async def adjust_stock(
    product_id: UUIDPath,
    request: StockAdjustRequest,
    current_user: TokenData = Depends(require_admin),
    inventory: InventoryService = Depends(get_inventory_service),
):
    """Add or remove units with a reason. Returns the new stock balance."""
    from fastapi import HTTPException

    if request.change == 0:
        raise HTTPException(status_code=422, detail="change must not be zero")
    if request.reason == "restock" and request.change < 0:
        raise HTTPException(status_code=422, detail="A restock must add units (positive change)")
    if request.reason == "damaged" and request.change > 0:
        raise HTTPException(status_code=422, detail="A damaged write-off must remove units (negative change)")

    balance = await inventory.adjust_stock(
        product_id, request.change, request.reason, request.note, current_user.user_id
    )
    return {"success": True, "product_id": product_id, "stock_quantity": balance}


@router.get("/{product_id}/movements")
async def list_movements(
    product_id: UUIDPath,
    limit: int = Query(100, ge=1, le=500),
    inventory: InventoryService = Depends(get_inventory_service),
):
    """A product's stock history, newest first."""
    return {"movements": await inventory.list_movements(product_id, limit=limit)}
