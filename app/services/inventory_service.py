"""
Inventory Service — the product stock ledger.

Products ship from one central warehouse that admins manage (client decision,
2026-11-27), so stock is a single number per product: `products.stock_quantity`.
What this service adds is the *why*: every change to that number goes through a
SECURITY DEFINER RPC (migration 20261127000000) that updates the balance and
appends a `product_stock_movements` row in the same transaction.

    adjust_stock()      +N / -N with a reason (restock, damaged, adjustment)
    set_stock()         "the count is now N" — used by the product edit form
    restore_order_stock()  give a cancelled order's units back (idempotent)
    list_movements()    a product's history, newest first

Sales are ledgered inside `decrement_product_stock`, called by the order flow.
Never write `products.stock_quantity` directly — the ledger would stop summing.
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from app.core.database import db_exec

logger = logging.getLogger(__name__)

# Reasons an admin may pick by hand. 'sale' and 'order_cancelled' are written
# only by the order flow; 'initial' only at product creation.
MANUAL_REASONS = {"restock", "adjustment", "damaged"}


def _raise_for_rpc_error(e: Exception, product_id: str) -> None:
    """Translate the stock RPCs' RAISE EXCEPTION codes into HTTP errors."""
    msg = str(e)
    if "insufficient_stock" in msg:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stock cannot go below zero",
        )
    if "product_not_found" in msg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product not found: {product_id}",
        )
    if "stock_cannot_be_negative" in msg or "stock_change_must_be_nonzero" in msg:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid stock change")
    logger.error(f"Stock RPC failed for product {product_id}: {e}")
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to update stock",
    )


def _rpc_scalar(response) -> Any:
    """PostgREST returns a scalar RPC result bare or wrapped in a list."""
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return data[0] if data else None
    return data


class InventoryService:
    def __init__(self, db_client):
        self.db = db_client

    async def adjust_stock(
        self,
        product_id: str,
        change: int,
        reason: str,
        note: Optional[str],
        actor_id: Optional[str],
    ) -> int:
        """Apply +change/-change to a product's stock. Returns the new balance."""
        if change == 0:
            raise HTTPException(status_code=400, detail="Change must not be zero")
        try:
            resp = await db_exec(self.db.rpc("adjust_product_stock", {
                "p_product_id": product_id,
                "p_change": change,
                "p_reason": reason,
                "p_note": note,
                "p_actor": actor_id,
            }))
        except Exception as e:
            _raise_for_rpc_error(e, product_id)
        balance = _rpc_scalar(resp)
        logger.info(f"Stock {reason} {change:+d} on product {product_id} -> {balance} (by {actor_id})")
        return balance

    async def set_stock(
        self,
        product_id: str,
        new_qty: int,
        reason: str,
        note: Optional[str],
        actor_id: Optional[str],
    ) -> int:
        """Set a product's stock to an absolute count (ledgers the difference)."""
        try:
            resp = await db_exec(self.db.rpc("set_product_stock", {
                "p_product_id": product_id,
                "p_new_qty": new_qty,
                "p_reason": reason,
                "p_note": note,
                "p_actor": actor_id,
            }))
        except Exception as e:
            _raise_for_rpc_error(e, product_id)
        return _rpc_scalar(resp)

    async def record_initial_stock(self, product_id: str, qty: int, actor_id: Optional[str]) -> None:
        """Opening ledger row for a just-created product. Best-effort."""
        if not qty or qty <= 0:
            return
        try:
            await db_exec(self.db.table("product_stock_movements").insert({
                "product_id": product_id,
                "change": qty,
                "balance_after": qty,
                "reason": "initial",
                "created_by": actor_id,
            }))
        except Exception as e:
            logger.error(f"Could not record initial stock for product {product_id}: {e}")

    async def restore_order_stock(self, order_id: str, actor_id: Optional[str]) -> bool:
        """
        Return a cancelled order's units to stock. True if anything was returned.

        Idempotent (product_orders.stock_restored) and a no-op for an order that
        never took stock (unpaid). Raises on DB failure so the caller can decide.
        """
        resp = await db_exec(self.db.rpc("restore_order_stock", {
            "p_order_id": order_id,
            "p_actor": actor_id,
        }))
        return bool(_rpc_scalar(resp))

    async def list_movements(self, product_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """A product's stock history, newest first."""
        try:
            resp = await db_exec(
                self.db.table("product_stock_movements")
                .select("*")
                .eq("product_id", product_id)
                .order("created_at", desc=True)
                .limit(limit)
            )
            return resp.data or []
        except Exception as e:
            logger.error(f"Failed to list stock movements for {product_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to fetch stock history")
