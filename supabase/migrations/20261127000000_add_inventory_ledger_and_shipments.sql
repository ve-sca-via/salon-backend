-- =====================================================
-- Migration: Inventory ledger + shipment tracking for product orders
-- Date: 2026-11-27
-- Purpose:
--   Products ship from one central warehouse, managed by admins. Until now
--   products.stock_quantity was a bare counter: an admin edit overwrote it
--   with no record of who/why, a cancelled paid order never gave its units
--   back, and an order had nowhere to keep courier/tracking details.
--
--   This adds (additive only — old code keeps working unchanged):
--     * product_stock_movements  — append-only ledger; every change to
--                                  stock_quantity writes one row
--     * product_order_events     — status timeline per order (admin actions
--                                  and delivery-partner webhook updates)
--     * product_orders shipment columns + stock_restored guard
--     * adjust_product_stock()   — admin restock / damage / correction
--     * set_product_stock()      — "set to N" (legacy product edit form)
--     * restore_order_stock()    — give a cancelled order's units back, once
--     * decrement_product_stock() now also writes 'sale' ledger rows
--
--   Single warehouse by client decision: no location dimension on purpose.
-- =====================================================

-- ---------- Ledger ----------
CREATE TABLE IF NOT EXISTS product_stock_movements (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id     UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    order_id       UUID REFERENCES product_orders(id) ON DELETE SET NULL,
    change         INTEGER NOT NULL CHECK (change <> 0),
    balance_after  INTEGER NOT NULL CHECK (balance_after >= 0),
    reason         TEXT NOT NULL CHECK (reason IN (
                       'initial',          -- stock entered when the product was created
                       'restock',          -- new units received at the warehouse
                       'adjustment',       -- stock count correction (either direction)
                       'damaged',          -- written off: damaged / expired / lost
                       'sale',             -- paid order (decrement_product_stock)
                       'order_cancelled'   -- cancelled order's units returned
                   )),
    note           TEXT,
    created_by     UUID REFERENCES profiles(id) ON DELETE SET NULL,  -- NULL = system
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_product_stock_movements_product
    ON product_stock_movements(product_id, created_at DESC);

ALTER TABLE product_stock_movements ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role has full access to product_stock_movements"
    ON product_stock_movements FOR ALL TO service_role USING (true) WITH CHECK (true);

COMMENT ON TABLE product_stock_movements IS
'Append-only stock ledger. products.stock_quantity is the running balance; every change to it writes one row here (via the stock RPCs). Never update or delete rows.';

-- ---------- Order timeline ----------
CREATE TABLE IF NOT EXISTS product_order_events (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id     UUID NOT NULL REFERENCES product_orders(id) ON DELETE CASCADE,
    source       TEXT NOT NULL CHECK (source IN ('admin', 'delivery_webhook', 'system')),
    event        TEXT NOT NULL,          -- order status set, or the courier's own status
    from_status  TEXT,
    to_status    TEXT,                   -- NULL when the event did not change the order status
    note         TEXT,
    payload      JSONB,                  -- raw webhook body, for debugging partner integrations
    created_by   UUID REFERENCES profiles(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_product_order_events_order
    ON product_order_events(order_id, created_at);

ALTER TABLE product_order_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role has full access to product_order_events"
    ON product_order_events FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ---------- Shipment columns ----------
ALTER TABLE product_orders
    ADD COLUMN IF NOT EXISTS stock_restored  BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS courier_name    TEXT,
    ADD COLUMN IF NOT EXISTS tracking_number TEXT,
    ADD COLUMN IF NOT EXISTS tracking_url    TEXT,
    ADD COLUMN IF NOT EXISTS shipped_at      TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS delivered_at    TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS cancelled_at    TIMESTAMPTZ;

COMMENT ON COLUMN product_orders.stock_restored IS
'Set TRUE the first (and only) time restore_order_stock() returns this order''s units to stock. Mirrors stock_decremented.';

-- ---------- adjust_product_stock ----------
CREATE OR REPLACE FUNCTION adjust_product_stock(
    p_product_id UUID,
    p_change     INTEGER,
    p_reason     TEXT,
    p_note       TEXT,
    p_actor      UUID
)
RETURNS INTEGER   -- new balance
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_balance INTEGER;
BEGIN
    IF p_change = 0 THEN
        RAISE EXCEPTION 'stock_change_must_be_nonzero';
    END IF;

    UPDATE products
    SET stock_quantity = stock_quantity + p_change, updated_at = now()
    WHERE id = p_product_id AND stock_quantity + p_change >= 0
    RETURNING stock_quantity INTO v_balance;

    IF NOT FOUND THEN
        IF EXISTS (SELECT 1 FROM products WHERE id = p_product_id) THEN
            RAISE EXCEPTION 'insufficient_stock_for_product_%', p_product_id;
        END IF;
        RAISE EXCEPTION 'product_not_found_%', p_product_id;
    END IF;

    INSERT INTO product_stock_movements (product_id, change, balance_after, reason, note, created_by)
    VALUES (p_product_id, p_change, v_balance, p_reason, p_note, p_actor);

    RETURN v_balance;
END;
$$;

-- ---------- set_product_stock ----------
-- "Set the count to N", computing the delta under a row lock so a sale that
-- lands at the same moment is not silently overwritten. No-op if unchanged.
CREATE OR REPLACE FUNCTION set_product_stock(
    p_product_id UUID,
    p_new_qty    INTEGER,
    p_reason     TEXT,
    p_note       TEXT,
    p_actor      UUID
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_current INTEGER;
BEGIN
    IF p_new_qty < 0 THEN
        RAISE EXCEPTION 'stock_cannot_be_negative';
    END IF;

    SELECT stock_quantity INTO v_current FROM products WHERE id = p_product_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'product_not_found_%', p_product_id;
    END IF;

    IF v_current = p_new_qty THEN
        RETURN v_current;
    END IF;

    RETURN adjust_product_stock(p_product_id, p_new_qty - v_current, p_reason, p_note, p_actor);
END;
$$;

-- ---------- decrement_product_stock (now ledgered) ----------
-- Same signature, same idempotency claim as 20261103000000; adds the ledger row.
CREATE OR REPLACE FUNCTION decrement_product_stock(p_order_id UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_item    RECORD;
    v_balance INTEGER;
BEGIN
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
        WHERE id = v_item.product_id AND stock_quantity >= v_item.quantity
        RETURNING stock_quantity INTO v_balance;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'insufficient_stock_for_product_%', v_item.product_id;
        END IF;

        INSERT INTO product_stock_movements (product_id, order_id, change, balance_after, reason)
        VALUES (v_item.product_id, p_order_id, -v_item.quantity, v_balance, 'sale');
    END LOOP;

    RETURN TRUE;
END;
$$;

-- ---------- restore_order_stock ----------
-- Returns a cancelled order's units, exactly once, and only if they were
-- ever taken (an unpaid order never decremented, so there is nothing to give back).
CREATE OR REPLACE FUNCTION restore_order_stock(p_order_id UUID, p_actor UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_item    RECORD;
    v_balance INTEGER;
BEGIN
    UPDATE product_orders
    SET stock_restored = TRUE
    WHERE id = p_order_id AND stock_decremented = TRUE AND stock_restored = FALSE;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    FOR v_item IN
        SELECT product_id, quantity
        FROM product_order_items
        WHERE order_id = p_order_id
    LOOP
        UPDATE products
        SET stock_quantity = stock_quantity + v_item.quantity
        WHERE id = v_item.product_id
        RETURNING stock_quantity INTO v_balance;

        -- A hard-deleted product has nothing to return stock to; skip it.
        IF FOUND THEN
            INSERT INTO product_stock_movements (product_id, order_id, change, balance_after, reason, created_by)
            VALUES (v_item.product_id, p_order_id, v_item.quantity, v_balance, 'order_cancelled', p_actor);
        END IF;
    END LOOP;

    RETURN TRUE;
END;
$$;

-- Backend (service_role) only — see 20261105000000 for why all three are revoked.
REVOKE EXECUTE ON FUNCTION adjust_product_stock(UUID, INTEGER, TEXT, TEXT, UUID) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION adjust_product_stock(UUID, INTEGER, TEXT, TEXT, UUID) TO service_role;
REVOKE EXECUTE ON FUNCTION set_product_stock(UUID, INTEGER, TEXT, TEXT, UUID) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION set_product_stock(UUID, INTEGER, TEXT, TEXT, UUID) TO service_role;
REVOKE EXECUTE ON FUNCTION decrement_product_stock(UUID) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION decrement_product_stock(UUID) TO service_role;
REVOKE EXECUTE ON FUNCTION restore_order_stock(UUID, UUID) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION restore_order_stock(UUID, UUID) TO service_role;

-- ---------- Opening balances ----------
-- One 'initial' row per product that already has stock, so every product's
-- ledger sums to its current stock_quantity from day one.
INSERT INTO product_stock_movements (product_id, change, balance_after, reason, note)
SELECT p.id, p.stock_quantity, p.stock_quantity, 'initial', 'Opening balance (ledger introduced)'
FROM products p
WHERE p.stock_quantity > 0
  AND NOT EXISTS (SELECT 1 FROM product_stock_movements m WHERE m.product_id = p.id);
