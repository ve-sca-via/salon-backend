-- Migration: Fix bookings_with_payments view
-- Date: 2026-01-11
-- Description: Recreate bookings_with_payments view with correct structure including deleted_at column

-- Drop existing view
DROP VIEW IF EXISTS public.bookings_with_payments CASCADE;

-- Recreate view with all required columns
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
  b.convenience_fee,
  b.total_amount,
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

-- Add comment
COMMENT ON VIEW bookings_with_payments IS 'Bookings with payment summary and customer data. Customer information (name, phone, email) is fetched from profiles table via JOIN for data consistency.';
