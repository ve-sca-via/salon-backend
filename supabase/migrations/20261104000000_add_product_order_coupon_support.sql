-- =====================================================
-- Migration: Coupon support for product orders
-- Date: 2026-11-04
-- Purpose:
--   Coupons only ever worked on bookings (see 20260614000001_create_coupons.sql,
--   20260617000000_harden_coupon_redemption.sql). Products are 100% admin-managed
--   (no vendor-owned product inventory), so only PLATFORM-scope coupons are ever
--   usable on a product order — this migration does not add a vendor-scope path
--   for products.
--
--   product_orders already has subtotal/discount_total/total_amount columns
--   (20260509000001_create_product_orders_table.sql) — discount_total has sat
--   unused at 0 since product_order_service deliberately had no discount flow
--   (see docs/PAYMENT_FLOW_AUDIT.md C-5). This migration starts using it.
-- =====================================================

-- =====================================================
-- 1. coupons.applies_to gains 'product'
-- =====================================================
ALTER TABLE public.coupons DROP CONSTRAINT IF EXISTS coupons_applies_to_check;
ALTER TABLE public.coupons
    ADD CONSTRAINT coupons_applies_to_check
    CHECK (applies_to IN ('service', 'convenience_fee', 'product'));

-- A product coupon only ever makes sense platform-wide (no vendor-owned
-- product catalog to scope it to).
ALTER TABLE public.coupons DROP CONSTRAINT IF EXISTS coupons_product_scope_platform;
ALTER TABLE public.coupons
    ADD CONSTRAINT coupons_product_scope_platform
    CHECK (applies_to != 'product' OR scope = 'platform');

-- =====================================================
-- 2. coupon_redemptions: generalize to product orders too
-- =====================================================
ALTER TABLE public.coupon_redemptions
    ADD COLUMN IF NOT EXISTS product_order_id UUID REFERENCES public.product_orders(id) ON DELETE CASCADE;

COMMENT ON COLUMN public.coupon_redemptions.product_order_id IS
'Product order this redemption applies to. Exactly one of booking_id/product_order_id is set per row.';

ALTER TABLE public.coupon_redemptions DROP CONSTRAINT IF EXISTS coupon_redemptions_exactly_one_target;
ALTER TABLE public.coupon_redemptions
    ADD CONSTRAINT coupon_redemptions_exactly_one_target CHECK (
        (booking_id IS NOT NULL AND product_order_id IS NULL)
        OR (booking_id IS NULL AND product_order_id IS NOT NULL)
    );

-- coupon_redemptions_unique_booking (UNIQUE(coupon_id, booking_id)) does not
-- guard product redemptions — NULL booking_id never collides with itself in a
-- UNIQUE index. Add the equivalent for the product side.
CREATE UNIQUE INDEX IF NOT EXISTS idx_coupon_redemptions_unique_product_order
    ON public.coupon_redemptions (coupon_id, product_order_id)
    WHERE product_order_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_coupon_redemptions_product_order
    ON public.coupon_redemptions (product_order_id) WHERE product_order_id IS NOT NULL;

-- =====================================================
-- 3. product_orders: coupon linkage
-- =====================================================
ALTER TABLE public.product_orders
    ADD COLUMN IF NOT EXISTS coupon_id   UUID REFERENCES public.coupons(id),
    ADD COLUMN IF NOT EXISTS coupon_code TEXT;

COMMENT ON COLUMN public.product_orders.coupon_id IS
'Platform coupon applied to this order, if any.';
COMMENT ON COLUMN public.product_orders.coupon_code IS
'Snapshot of the coupon code used at order time (the coupons row may be edited or the code reissued).';

CREATE INDEX IF NOT EXISTS idx_product_orders_coupon_id
    ON public.product_orders (coupon_id) WHERE coupon_id IS NOT NULL;

-- =====================================================
-- 4. redeem_product_coupon() — mirrors redeem_coupon()'s hardened semantics
--    (FOR UPDATE row lock, re-validates window/limits/first-time at redemption)
--    but against product_orders instead of bookings, and with no salon-scope
--    check since only platform coupons ever reach here.
-- =====================================================
CREATE OR REPLACE FUNCTION redeem_product_coupon(
    p_coupon_id        UUID,
    p_user_id          UUID,
    p_product_order_id UUID,
    p_discount_amount  NUMERIC
)
RETURNS TABLE (
    success              BOOLEAN,
    reason               TEXT,
    was_already_redeemed BOOLEAN
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_coupon           RECORD;
    v_user_redemptions INTEGER;
    v_prior_orders     INTEGER;
    v_existing         UUID;
    v_now              TIMESTAMPTZ := now();
BEGIN
    -- Idempotency: this coupon already redeemed for this order
    SELECT id INTO v_existing
    FROM coupon_redemptions
    WHERE coupon_id = p_coupon_id AND product_order_id = p_product_order_id;

    IF FOUND THEN
        RETURN QUERY SELECT TRUE, 'already_redeemed'::TEXT, TRUE;
        RETURN;
    END IF;

    -- Lock the coupon row so concurrent redemptions serialize on it
    SELECT * INTO v_coupon
    FROM coupons
    WHERE id = p_coupon_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, 'coupon_not_found'::TEXT, FALSE;
        RETURN;
    END IF;

    IF NOT v_coupon.is_active THEN
        RETURN QUERY SELECT FALSE, 'coupon_inactive'::TEXT, FALSE;
        RETURN;
    END IF;

    IF v_coupon.applies_to != 'product' OR v_coupon.scope != 'platform' THEN
        RETURN QUERY SELECT FALSE, 'not_applicable_to_products'::TEXT, FALSE;
        RETURN;
    END IF;

    IF v_coupon.valid_from IS NOT NULL AND v_now < v_coupon.valid_from THEN
        RETURN QUERY SELECT FALSE, 'not_started'::TEXT, FALSE;
        RETURN;
    END IF;
    IF v_coupon.valid_until IS NOT NULL AND v_now > v_coupon.valid_until THEN
        RETURN QUERY SELECT FALSE, 'expired'::TEXT, FALSE;
        RETURN;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM product_orders WHERE id = p_product_order_id) THEN
        RETURN QUERY SELECT FALSE, 'order_not_found'::TEXT, FALSE;
        RETURN;
    END IF;

    -- Total usage limit
    IF v_coupon.usage_limit_total IS NOT NULL
       AND v_coupon.used_count >= v_coupon.usage_limit_total THEN
        RETURN QUERY SELECT FALSE, 'total_limit_reached'::TEXT, FALSE;
        RETURN;
    END IF;

    -- Per-user usage limit (shared with any booking redemptions of this coupon —
    -- it's the same coupon row's limit)
    IF v_coupon.usage_limit_per_user IS NOT NULL THEN
        SELECT COUNT(*) INTO v_user_redemptions
        FROM coupon_redemptions
        WHERE coupon_id = p_coupon_id AND user_id = p_user_id;

        IF v_user_redemptions >= v_coupon.usage_limit_per_user THEN
            RETURN QUERY SELECT FALSE, 'per_user_limit_reached'::TEXT, FALSE;
            RETURN;
        END IF;
    END IF;

    -- First-time restriction, evaluated against prior product orders (not
    -- bookings) — "first time" means first product purchase, mirroring how a
    -- vendor-scoped booking coupon means "first at this salon" rather than
    -- "first anywhere".
    IF v_coupon.first_time_scope IS NOT NULL THEN
        SELECT COUNT(*) INTO v_prior_orders
        FROM product_orders po
        WHERE po.user_id = p_user_id
          AND po.id != p_product_order_id
          AND po.status != 'cancelled';

        IF v_prior_orders > 0 THEN
            RETURN QUERY SELECT FALSE, 'not_first_time'::TEXT, FALSE;
            RETURN;
        END IF;
    END IF;

    -- Record redemption (+ snapshot) and bump cached counter (same transaction)
    INSERT INTO coupon_redemptions (
        coupon_id, user_id, product_order_id, discount_amount,
        gross_discount, coupon_code, funded_by, scope
    )
    VALUES (
        p_coupon_id, p_user_id, p_product_order_id, COALESCE(p_discount_amount, 0),
        COALESCE(p_discount_amount, 0), v_coupon.code, v_coupon.funded_by, v_coupon.scope
    );

    UPDATE coupons SET used_count = used_count + 1 WHERE id = p_coupon_id;

    RETURN QUERY SELECT TRUE, 'redeemed'::TEXT, FALSE;
END;
$$;

GRANT EXECUTE ON FUNCTION redeem_product_coupon(UUID, UUID, UUID, NUMERIC) TO authenticated;
GRANT EXECUTE ON FUNCTION redeem_product_coupon(UUID, UUID, UUID, NUMERIC) TO service_role;

COMMENT ON FUNCTION redeem_product_coupon(UUID, UUID, UUID, NUMERIC) IS
'Atomically re-validates a platform/product coupon (active, window, first-time, total & per-user limits) under FOR UPDATE and records a snapshotted redemption against a product order. Idempotent per (coupon_id, product_order_id).';

-- =====================================================
-- 5. coupon_redemption_report: surface product_order_id too
-- =====================================================
-- CREATE OR REPLACE VIEW only ever allows appending a new column at the end —
-- it cannot reposition one among the existing columns. Earlier revisions of
-- this migration inserted product_order_id between booking_id and
-- discount_amount, which Postgres reads as renaming discount_amount to
-- product_order_id (SQLSTATE 42P16). Keep every pre-existing column in its
-- original name/position and append product_order_id last.
CREATE OR REPLACE VIEW public.coupon_redemption_report AS
SELECT
    cr.id                AS redemption_id,
    cr.coupon_id,
    cr.coupon_code,
    cr.scope,
    cr.funded_by,
    cr.salon_id,
    cr.user_id,
    cr.booking_id,
    cr.discount_amount,
    cr.gross_discount,
    cr.redeemed_at,
    c.title              AS coupon_title,
    c.applies_to,
    c.discount_type,
    c.discount_value,
    s.business_name      AS salon_name,
    cr.product_order_id
FROM coupon_redemptions cr
LEFT JOIN coupons c ON c.id = cr.coupon_id
LEFT JOIN salons  s ON s.id = cr.salon_id;

COMMENT ON VIEW public.coupon_redemption_report IS
'Flat, settlement-ready view of coupon redemptions (booking or product-order) using the redemption-time snapshot rather than the mutable coupons row.';
