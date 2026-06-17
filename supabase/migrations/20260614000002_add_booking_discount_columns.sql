-- =====================================================
-- Migration: Add coupon/discount columns to bookings
-- Date: 2026-06-14
-- Purpose:
--   Record the discount applied to a booking at checkout time so every
--   transaction is auditable. The existing service_price / convenience_fee /
--   total_amount remain the FINAL payable values; the new columns capture the
--   pre-discount subtotal and the discount breakdown.
-- =====================================================

ALTER TABLE public.bookings
    ADD COLUMN IF NOT EXISTS subtotal_service_price   NUMERIC(10, 2),
    ADD COLUMN IF NOT EXISTS discount_amount          NUMERIC(10, 2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS convenience_fee_discount NUMERIC(10, 2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS coupon_id                UUID REFERENCES coupons(id),
    ADD COLUMN IF NOT EXISTS coupon_code              TEXT;

COMMENT ON COLUMN public.bookings.subtotal_service_price IS
'Service total before any coupon discount (sum of sale/discounted line totals). NULL for legacy rows.';
COMMENT ON COLUMN public.bookings.discount_amount IS
'Coupon discount applied to the service price (the "pay at salon" amount).';
COMMENT ON COLUMN public.bookings.convenience_fee_discount IS
'Coupon discount applied to the convenience fee (the online "pay now" amount).';
COMMENT ON COLUMN public.bookings.coupon_id IS
'Coupon applied to this booking, if any.';
COMMENT ON COLUMN public.bookings.coupon_code IS
'Snapshot of the coupon code used at booking time.';

-- Recreate bookings_with_payments to surface the new discount fields.
-- (Based on 20260111000000_fix_bookings_with_payments_view.sql.)
DROP VIEW IF EXISTS public.bookings_with_payments CASCADE;

CREATE VIEW public.bookings_with_payments AS
SELECT
  b.id,
  b.booking_number,
  b.customer_id,
  b.salon_id,
  b.services,
  b.booking_date,
  b.time_slots,
  b.service_price,
  b.subtotal_service_price,
  b.discount_amount,
  b.convenience_fee,
  b.convenience_fee_discount,
  b.total_amount,
  b.coupon_id,
  b.coupon_code,
  b.status,
  b.created_at,
  b.updated_at,
  b.deleted_at,
  -- Customer data from profiles table (normalized)
  p.full_name as customer_name,
  p.phone as customer_phone,
  p.email as customer_email,
  -- Convenience fee payment info
  cf.id as convenience_fee_payment_id,
  cf.amount as convenience_fee_amount,
  cf.status as convenience_fee_status,
  cf.paid_at as convenience_fee_paid_at,
  cf.razorpay_payment_id as convenience_fee_razorpay_payment_id,
  -- Service payment info
  sp.id as service_payment_id,
  sp.amount as service_payment_amount,
  sp.status as service_payment_status,
  sp.paid_at as service_payment_paid_at,
  sp.payment_method as service_payment_method,
  -- Computed flags for backward compatibility
  (cf.status::text = 'success'::text) as is_convenience_fee_paid,
  (sp.status::text = 'success'::text) as is_service_paid,
  (cf.status::text = 'success'::text AND sp.status::text = 'success'::text) as is_fully_paid
FROM bookings b
LEFT JOIN profiles p ON p.id = b.customer_id
LEFT JOIN payments cf ON cf.booking_id = b.id
  AND cf.payment_type::text = 'convenience_fee'::text
  AND cf.deleted_at IS NULL
LEFT JOIN payments sp ON sp.booking_id = b.id
  AND sp.payment_type::text = 'service_payment'::text
  AND sp.deleted_at IS NULL
WHERE b.deleted_at IS NULL;

COMMENT ON VIEW bookings_with_payments IS 'Bookings with payment summary, customer data and coupon discount breakdown. Customer information is fetched from profiles via JOIN.';
