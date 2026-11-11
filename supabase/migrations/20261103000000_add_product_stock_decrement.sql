-- =====================================================
-- Migration: Atomic, idempotent stock decrement for paid product orders
-- Date: 2026-11-03
-- Purpose:
--   Product orders never touched products.stock_quantity — a product's stock
--   only ever moved if a vendor/admin edited it by hand, and nothing stopped
--   two buyers from both checking out the last unit. Decrementing happens once
--   per order, at the moment it's marked paid (verify_payment / dev_complete_order
--   / the Razorpay webhook), all of which can fire more than once for the same
--   order — so the function is idempotent via product_orders.stock_decremented
--   rather than relying on callers to decrement exactly once.
-- =====================================================

ALTER TABLE public.product_orders
    ADD COLUMN IF NOT EXISTS stock_decremented BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN public.product_orders.stock_decremented IS
'Set TRUE the first (and only) time decrement_product_stock() successfully runs for this order. Guards against double-decrementing when verify_payment/dev_complete_order/the webhook race or retry.';

CREATE OR REPLACE FUNCTION decrement_product_stock(p_order_id UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_item RECORD;
BEGIN
    -- Claim this order for decrementing. If another call already claimed it
    -- (or the order doesn't exist), there is nothing to do.
    UPDATE product_orders
    SET stock_decremented = TRUE
    WHERE id = p_order_id AND stock_decremented = FALSE;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    FOR v_item IN
        SELECT product_id, quantity
        FROM product_order_items
        WHERE order_id = p_order_id
    LOOP
        UPDATE products
        SET stock_quantity = stock_quantity - v_item.quantity
        WHERE id = v_item.product_id AND stock_quantity >= v_item.quantity;

        IF NOT FOUND THEN
            -- Raising rolls back this whole transaction, including the claim
            -- above, so a genuine oversell race doesn't silently leave stock
            -- half-decremented or the order stuck looking "already handled".
            RAISE EXCEPTION 'insufficient_stock_for_product_%', v_item.product_id;
        END IF;
    END LOOP;

    RETURN TRUE;
END;
$$;

-- SECURITY DEFINER + trusts its arguments: only the backend (service_role)
-- may call it. Postgres grants EXECUTE to PUBLIC by default, and Supabase's
-- default privileges grant it to anon/authenticated, so revoke all three.
REVOKE EXECUTE ON FUNCTION decrement_product_stock(UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION decrement_product_stock(UUID) TO service_role;

COMMENT ON FUNCTION decrement_product_stock(UUID) IS
'Atomically decrements stock for every item on a paid product order, exactly once per order. Raises (rolling back entirely) if any item no longer has enough stock — the caller should log and let the order stand, since payment was already captured by then.';
