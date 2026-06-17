-- =====================================================
-- Migration: Harden coupon redemption (audit remediation)
-- Date: 2026-06-17
-- Purpose:
--   Address the production-readiness audit:
--     * C2  redeem_coupon() is now AUTHORITATIVE: it re-validates the validity
--           window, salon scope, first-time eligibility and usage limits INSIDE
--           the locked transaction (previously only is_active + limits).
--     * H4  First-time restriction is enforced at redemption under the row lock,
--           closing the "unlimited reuse when per-user limit is NULL" hole and
--           the concurrent double-first-booking race.
--     * H6  coupon_redemptions now snapshots salon_id, coupon_code, funded_by,
--           scope and the GROSS coupon discount, so settlement / reporting does
--           not depend on the (mutable, reusable) coupons row.
--     * D3  First-time excludes CANCELLED bookings (a cancelled booking no
--           longer locks a customer out of first-time offers).
--     * L16 Index bookings.coupon_id for redemption/reporting joins.
--     * L18 coupon_redemption_report view for analytics.
-- =====================================================

-- =====================================================
-- 1. Snapshot columns on coupon_redemptions (H6)
-- =====================================================
ALTER TABLE public.coupon_redemptions
    ADD COLUMN IF NOT EXISTS gross_discount NUMERIC(10, 2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS salon_id       UUID,
    ADD COLUMN IF NOT EXISTS coupon_code    TEXT,
    ADD COLUMN IF NOT EXISTS funded_by      TEXT,
    ADD COLUMN IF NOT EXISTS scope          TEXT;

COMMENT ON COLUMN public.coupon_redemptions.gross_discount IS
'Full coupon discount value at redemption (independent of any concurrent salon sale). discount_amount stays the net delta recorded against the booking.';
COMMENT ON COLUMN public.coupon_redemptions.salon_id IS
'Salon the redemption occurred at (snapshot from the booking).';
COMMENT ON COLUMN public.coupon_redemptions.coupon_code IS
'Coupon code at redemption time (snapshot; the coupons row may be edited or the code reissued).';
COMMENT ON COLUMN public.coupon_redemptions.funded_by IS
'Who funded the discount at redemption time: platform | vendor (snapshot).';
COMMENT ON COLUMN public.coupon_redemptions.scope IS
'Coupon scope at redemption time: platform | vendor (snapshot).';

CREATE INDEX IF NOT EXISTS idx_coupon_redemptions_salon
    ON public.coupon_redemptions (salon_id);

-- =====================================================
-- 2. Index bookings.coupon_id (L16)
-- =====================================================
CREATE INDEX IF NOT EXISTS idx_bookings_coupon_id
    ON public.bookings (coupon_id) WHERE coupon_id IS NOT NULL;

-- =====================================================
-- 3. redeem_coupon() — now authoritative (C2, H4, D3, H6)
-- =====================================================
-- Adds an optional p_gross_discount param (defaults to p_discount_amount for
-- backward compatibility). Re-validates everything that can change between the
-- order-time price check and redemption, under FOR UPDATE on the coupon row.
--
-- Drop the previous 4-arg signature first: adding a defaulted param creates a
-- NEW overload (not a replacement), which makes the name ambiguous for GRANT
-- and for PostgREST rpc() resolution.
DROP FUNCTION IF EXISTS redeem_coupon(UUID, UUID, UUID, NUMERIC);

CREATE OR REPLACE FUNCTION redeem_coupon(
    p_coupon_id       UUID,
    p_user_id         UUID,
    p_booking_id      UUID,
    p_discount_amount NUMERIC,
    p_gross_discount  NUMERIC DEFAULT NULL
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
    v_booking          RECORD;
    v_user_redemptions INTEGER;
    v_prior_bookings   INTEGER;
    v_existing         UUID;
    v_now              TIMESTAMPTZ := now();
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

    -- Validity window (was previously NOT re-checked at redemption)
    IF v_coupon.valid_from IS NOT NULL AND v_now < v_coupon.valid_from THEN
        RETURN QUERY SELECT FALSE, 'not_started'::TEXT, FALSE;
        RETURN;
    END IF;
    IF v_coupon.valid_until IS NOT NULL AND v_now > v_coupon.valid_until THEN
        RETURN QUERY SELECT FALSE, 'expired'::TEXT, FALSE;
        RETURN;
    END IF;

    -- Booking is needed for salon scope + first-time + snapshot
    SELECT id, salon_id, customer_id INTO v_booking
    FROM bookings
    WHERE id = p_booking_id;

    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, 'booking_not_found'::TEXT, FALSE;
        RETURN;
    END IF;

    -- Salon scope: vendor coupons only at their salon
    IF v_coupon.scope = 'vendor'
       AND v_coupon.salon_id IS DISTINCT FROM v_booking.salon_id THEN
        RETURN QUERY SELECT FALSE, 'wrong_salon'::TEXT, FALSE;
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

    -- First-time restriction (enforced here so a NULL per-user limit cannot be
    -- abused, and concurrent first bookings cannot both pass). Excludes the
    -- current booking, cancelled bookings and soft-deleted rows (D3).
    IF v_coupon.first_time_scope IS NOT NULL THEN
        SELECT COUNT(*) INTO v_prior_bookings
        FROM bookings b
        WHERE b.customer_id = p_user_id
          AND b.id <> p_booking_id
          AND b.deleted_at IS NULL
          AND b.status <> 'cancelled'
          AND (
              v_coupon.first_time_scope <> 'vendor'
              OR b.salon_id = v_coupon.salon_id
          );

        IF v_prior_bookings > 0 THEN
            RETURN QUERY SELECT FALSE, 'not_first_time'::TEXT, FALSE;
            RETURN;
        END IF;
    END IF;

    -- Record redemption (+ snapshot) and bump cached counter (same transaction)
    INSERT INTO coupon_redemptions (
        coupon_id, user_id, booking_id, discount_amount,
        gross_discount, salon_id, coupon_code, funded_by, scope
    )
    VALUES (
        p_coupon_id, p_user_id, p_booking_id, COALESCE(p_discount_amount, 0),
        COALESCE(p_gross_discount, p_discount_amount, 0),
        v_booking.salon_id, v_coupon.code, v_coupon.funded_by, v_coupon.scope
    );

    UPDATE coupons SET used_count = used_count + 1 WHERE id = p_coupon_id;

    RETURN QUERY SELECT TRUE, 'redeemed'::TEXT, FALSE;
END;
$$;

GRANT EXECUTE ON FUNCTION redeem_coupon(UUID, UUID, UUID, NUMERIC, NUMERIC) TO authenticated;
GRANT EXECUTE ON FUNCTION redeem_coupon(UUID, UUID, UUID, NUMERIC, NUMERIC) TO service_role;

COMMENT ON FUNCTION redeem_coupon(UUID, UUID, UUID, NUMERIC, NUMERIC) IS
'Atomically re-validates a coupon (active, window, scope, first-time, total & per-user limits) under FOR UPDATE and records a snapshotted redemption. Idempotent per (coupon_id, booking_id).';

-- =====================================================
-- 4. Reporting view (L18)
-- =====================================================
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
    s.business_name      AS salon_name
FROM coupon_redemptions cr
LEFT JOIN coupons c ON c.id = cr.coupon_id
LEFT JOIN salons  s ON s.id = cr.salon_id;

COMMENT ON VIEW public.coupon_redemption_report IS
'Flat, settlement-ready view of coupon redemptions using the redemption-time snapshot (code/scope/funded_by/salon) rather than the mutable coupons row.';
