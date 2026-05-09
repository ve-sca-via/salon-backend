import logging
from typing import Dict, Any, List, Optional
from fastapi import HTTPException, status
from supabase import Client

logger = logging.getLogger(__name__)

class ProductCartService:
    def __init__(self, db_client: Client):
        self.db = db_client

    async def get_cart(self, user_id: str) -> Dict[str, Any]:
        """Get all product cart items for a user"""
        try:
            response = self.db.table("product_cart_items")\
                .select("*, products(*)")\
                .eq("user_id", user_id)\
                .execute()
            
            items = response.data or []
            
            # Transform to match frontend expectations
            processed_items = []
            total_amount = 0.0
            item_count = 0
            
            for item in items:
                product = item.get("products", {})
                price = product.get("discount_price") or product.get("price") or 0.0
                quantity = item.get("quantity", 1)
                line_total = price * quantity
                
                total_amount += line_total
                item_count += quantity
                
                processed_items.append({
                    "id": item.get("id"),
                    "product_id": item.get("product_id"),
                    "name": product.get("name"),
                    "price": price,
                    "quantity": quantity,
                    "image_url": product.get("image_urls", [None])[0] if product.get("image_urls") else None,
                    "image_urls": product.get("image_urls", []),
                    "total": line_total
                })
                
            return {
                "success": True,
                "items": processed_items,
                "total_amount": total_amount,
                "item_count": item_count
            }
        except Exception as e:
            logger.error(f"Failed to get product cart: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve cart: {str(e)}"
            )

    async def add_to_cart(self, user_id: str, product_id: str, quantity: int = 1) -> Dict[str, Any]:
        """Add a product to the cart or increment quantity"""
        try:
            # 1. Check if product exists and has stock
            product_resp = self.db.table("products").select("id, stock_quantity").eq("id", product_id).single().execute()
            if not product_resp.data:
                raise HTTPException(status_code=404, detail="Product not found")
            
            # 2. Check if already in cart
            existing = self.db.table("product_cart_items")\
                .select("id, quantity")\
                .eq("user_id", user_id)\
                .eq("product_id", product_id)\
                .execute()
            
            if existing.data:
                # Update quantity
                new_qty = existing.data[0]["quantity"] + quantity
                response = self.db.table("product_cart_items").update({"quantity": new_qty}).eq("id", existing.data[0]["id"]).execute()
            else:
                # Insert new
                response = self.db.table("product_cart_items").insert({
                    "user_id": user_id,
                    "product_id": product_id,
                    "quantity": quantity
                }).execute()
                
            return {"success": True, "message": "Product added to cart"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to add to product cart: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def update_item(self, user_id: str, item_id: str, quantity: int) -> Dict[str, Any]:
        """Update quantity of an item in the cart"""
        try:
            if quantity <= 0:
                return await self.remove_item(user_id, item_id)
                
            response = self.db.table("product_cart_items").update({"quantity": quantity})\
                .eq("id", item_id)\
                .eq("user_id", user_id).execute()
                
            if not response.data:
                raise HTTPException(status_code=404, detail="Cart item not found")
                
            return {"success": True, "message": "Cart updated"}
        except Exception as e:
            logger.error(f"Failed to update product cart item: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def remove_item(self, user_id: str, item_id: str) -> Dict[str, Any]:
        """Remove an item from the cart"""
        try:
            self.db.table("product_cart_items").delete().eq("id", item_id).eq("user_id", user_id).execute()
            return {"success": True, "message": "Item removed"}
        except Exception as e:
            logger.error(f"Failed to remove from product cart: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def clear_cart(self, user_id: str) -> Dict[str, Any]:
        """Clear the entire cart for a user"""
        try:
            self.db.table("product_cart_items").delete().eq("user_id", user_id).execute()
            return {"success": True, "message": "Cart cleared"}
        except Exception as e:
            logger.error(f"Failed to clear product cart: {e}")
            raise HTTPException(status_code=500, detail=str(e))
