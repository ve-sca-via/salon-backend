-- =====================================================
-- Migration: Coupons & Redemptions
-- Date: 2026-06-14
-- Purpose:
--   Transaction-time coupon system supporting every discount pattern the
--   marketplace needs:
--     * vendor-issued and admin/platform-issued coupon codes
--     * platform-wide coupons usable on ANY salon
--     * service-price discounts (flat / percentage, with cap)
--     * convenience-fee discounts / waivers
--     * first-time-user offers (per-coupon scope)
--     * usage limits (total + per-user) and validity windows
--   Discounts are recorded against the booking at checkout, NOT baked into the
--   service catalog (unlike salon_discount_promotions).
-- =====================================================

-- =====================================================
-- 1. coupons
-- =====================================================
CREATE TABLE IF NOT EXISTS coupons (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code                 TEXT NOT NULL,                              -- shareable string, stored uppercase
    title                TEXT NOT NULL,
    scope                TEXT NOT NULL CHECK (scope IN ('platform', 'vendor')),
    salon_id             UUID REFERENCES salons(id) ON DELETE CASCADE,
    created_by           UUID,                                      -- admin/vendor user id (audit)
    funded_by            TEXT NOT NULL CHECK (funded_by IN ('platform', 'vendor')),
    applies_to           TEXT NOT NULL CHECK (applies_to IN ('service', 'convenience_fee')),
    discount_type        TEXT NOT NULL CHECK (discount_type IN ('percentage', 'flat_amount')),
    discount_value       NUMERIC(10, 2) NOT NULL CHECK (discount_value > 0),
    max_discount_cap     NUMERIC(10, 2) CHECK (max_discount_cap IS NULL OR max_discount_cap >= 0),
    min_order_amount     NUMERIC(10, 2) CHECK (min_order_amount IS NULL OR min_order_amount >= 0),
    first_time_scope     TEXT CHECK (first_time_scope IS NULL OR first_time_scope IN ('platform', 'vendor')),
    usage_limit_total    INTEGER CHECK (usage_limit_total IS NULL OR usage_limit_total >= 0),
    usage_limit_per_user INTEGER DEFAULT 1 CHECK (usage_limit_per_user IS NULL OR usage_limit_per_user >= 0),
    used_count           INTEGER NOT NULL DEFAULT 0,
    valid_from           TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_until          TIMESTAMPTZ,
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- A percentage discount can never exceed 100%
    CONSTRAINT coupons_percentage_cap CHECK (
        discount_type != 'percentage' OR (discount_value > 0 AND discount_value <= 100)
    ),
    -- Vendor-scoped coupons must belong to a salon; platform coupons must not
    CONSTRAINT coupons_scope_salon CHECK (
        (scope = 'vendor' AND salon_id IS NOT NULL)
        OR (scope = 'platform' AND salon_id IS NULL)
    ),
    -- Validity window must be coherent
    CONSTRAINT coupons_valid_window CHECK (valid_until IS NULL OR valid_until >= valid_from)
);

-- One active coupon per code (case-insensitive). Inactive/expired duplicates allowed
-- so old codes can be retired and reissued.
CREATE UNIQUE INDEX IF NOT EXISTS idx_coupons_active_code
    ON coupons (UPPER(code)) WHERE is_active;

-- Lookup path used by validation: find active coupon for a code, scope and salon
CREATE INDEX IF NOT EXISTS idx_coupons_scope_salon_active
    ON coupons (scope, salon_id, is_active, valid_until);

ALTER TABLE coupons DISABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION update_coupons_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_coupons_updated_at ON coupons;
CREATE TRIGGER trigger_update_coupons_updated_at
    BEFORE UPDATE ON coupons
    FOR EACH ROW
    EXECUTE FUNCTION update_coupons_updated_at();

-- =====================================================
-- 2. coupon_redemptions
-- =====================================================
CREATE TABLE IF NOT EXISTS coupon_redemptions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    coupon_id       UUID NOT NULL REFERENCES coupons(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL,
    booking_id      UUID REFERENCES bookings(id) ON DELETE CASCADE,
    discount_amount NUMERIC(10, 2) NOT NULL DEFAULT 0,
    redeemed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- A given coupon can only be redeemed once per booking (idempotency)
    CONSTRAINT coupon_redemptions_unique_booking UNIQUE (coupon_id, booking_id)
);

CREATE INDEX IF NOT EXISTS idx_coupon_redemptions_coupon_user
    ON coupon_redemptions (coupon_id, user_id);

ALTER TABLE coupon_redemptions DISABLE ROW LEVEL SECURITY;

-- =====================================================
-- 3. redeem_coupon() - atomic redemption with limit enforcement
-- =====================================================
-- Mirrors the verify_payment_and_confirm_booking transaction-safety pattern.
-- Locks the coupon row, re-checks total and per-user limits INSIDE the
-- transaction, inserts the redemption and increments used_count. Prevents
-- over-redemption under concurrency. Idempotent on (coupon_id, booking_id).
CREATE OR REPLACE FUNCTION redeem_coupon(
    p_coupon_id       UUID,
    p_user_id         UUID,
    p_booking_id      UUID,
    p_discount_amount NUMERIC
)
RETURNS TABLE (
    success           BOOLEAN,
    reason            TEXT,
    was_already_redeemed BOOLEAN
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_coupon          RECORD;
    v_user_redemptions INTEGER;
    v_existing        UUID;
BEGIN
    -- Idempotency: this coupon already redeemed for this booking
    SELECT id INTO v_existing
    FROM coupon_redemptions
    WHERE coupon_id = p_coupon_id AND booking_id = p_booking_id;

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

    -- Total usage limit
    IF v_coupon.usage_limit_total IS NOT NULL
       AND v_coupon.used_count >= v_coupon.usage_limit_total THEN
        RETURN QUERY SELECT FALSE, 'total_limit_reached'::TEXT, FALSE;
        RETURN;
    END IF;

    -- Per-user usage limit
    IF v_coupon.usage_limit_per_user IS NOT NULL THEN
        SELECT COUNT(*) INTO v_user_redemptions
        FROM coupon_redemptions
        WHERE coupon_id = p_coupon_id AND user_id = p_user_id;

        IF v_user_redemptions >= v_coupon.usage_limit_per_user THEN
            RETURN QUERY SELECT FALSE, 'per_user_limit_reached'::TEXT, FALSE;
            RETURN;
        END IF;
    END IF;

    -- Record redemption + bump cached counter (same transaction)
    INSERT INTO coupon_redemptions (coupon_id, user_id, booking_id, discount_amount)
    VALUES (p_coupon_id, p_user_id, p_booking_id, COALESCE(p_discount_amount, 0));

    UPDATE coupons SET used_count = used_count + 1 WHERE id = p_coupon_id;

    RETURN QUERY SELECT TRUE, 'redeemed'::TEXT, FALSE;
END;
$$;

GRANT EXECUTE ON FUNCTION redeem_coupon TO authenticated;
GRANT EXECUTE ON FUNCTION redeem_coupon TO service_role;

COMMENT ON TABLE coupons IS
'Coupon definitions for vendor- and admin-issued discounts. Applied at checkout time via PricingService; never mutates the service catalog.';
COMMENT ON TABLE coupon_redemptions IS
'One row per coupon redemption, used to enforce total and per-user usage limits and for settlement reporting.';
COMMENT ON FUNCTION redeem_coupon IS
'Atomically validates usage limits and records a coupon redemption. Idempotent per (coupon_id, booking_id).';
