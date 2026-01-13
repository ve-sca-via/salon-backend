-- Migration: Normalize bookings table by removing redundant customer data
-- Date: 2026-01-09
-- Description: Remove denormalized customer fields that are already in profiles table
--              Customer data will be fetched via JOIN with profiles table

-- Step 1: Drop dependent view first
-- The bookings_with_payments view depends on these columns
DROP VIEW IF EXISTS bookings_with_payments CASCADE;

-- Step 2: Drop denormalized customer columns
-- These fields are redundant as they exist in the profiles table
ALTER TABLE public.bookings 
DROP COLUMN IF EXISTS customer_name,
DROP COLUMN IF EXISTS customer_phone,
DROP COLUMN IF EXISTS customer_email;

-- Step 3: Recreate bookings_with_payments view with JOIN to profiles
-- This view now fetches customer data from profiles table dynamically
CREATE OR REPLACE VIEW bookings_with_payments AS
SELECT 
  b.id,
  b.booking_number,
  b.customer_id,
  b.salon_id,
  b.services,
  b.booking_date,
  b.booking_time,
  b.service_price,
  b.convenience_fee,
  b.total_amount,
  b.status,
  b.created_at,
  b.updated_at,
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
  (cf.status = 'success') as is_convenience_fee_paid,
  (sp.status = 'success') as is_service_paid,
  (cf.status = 'success' AND sp.status = 'success') as is_fully_paid
FROM bookings b
LEFT JOIN profiles p ON p.id = b.customer_id
LEFT JOIN payments cf ON cf.booking_id = b.id 
  AND cf.payment_type = 'convenience_fee' 
  AND cf.deleted_at IS NULL
LEFT JOIN payments sp ON sp.booking_id = b.id 
  AND sp.payment_type = 'service_payment' 
  AND sp.deleted_at IS NULL
WHERE b.deleted_at IS NULL;

COMMENT ON VIEW bookings_with_payments IS 'Bookings with payment summary. Customer data (name, phone, email) is now fetched from profiles table via JOIN for data consistency.';

-- Step 4: Add performance indexes for common queries
-- Index on customer_id for filtering bookings by customer
CREATE INDEX IF NOT EXISTS idx_bookings_customer_id 
ON public.bookings(customer_id);

-- Index on salon_id for filtering bookings by salon
CREATE INDEX IF NOT EXISTS idx_bookings_salon_id 
ON public.bookings(salon_id);

-- Composite index for salon bookings by date (common vendor query)
CREATE INDEX IF NOT EXISTS idx_bookings_salon_date 
ON public.bookings(salon_id, booking_date DESC);

-- Index on status for filtering by booking status
CREATE INDEX IF NOT EXISTS idx_bookings_status 
ON public.bookings(status);

-- Index on booking_number for quick lookup by booking number
CREATE INDEX IF NOT EXISTS idx_bookings_number 
ON public.bookings(booking_number);

-- Composite index for customer bookings by date (common customer query)
CREATE INDEX IF NOT EXISTS idx_bookings_customer_date 
ON public.bookings(customer_id, booking_date DESC);

-- Step 3: Add comments for documentation
COMMENT ON TABLE public.bookings IS 
'Normalized bookings table. Customer data (name, phone, email) is fetched via JOIN with profiles table to maintain data consistency.';

COMMENT ON COLUMN public.bookings.services IS 
'Historical snapshot of services at booking time (JSONB). Preserved for historical accuracy even if service details change later.';

COMMENT ON COLUMN public.bookings.customer_id IS 
'Foreign key to profiles.id. Use JOIN to fetch current customer name, phone, email.';

-- Step 6: Verify the structure
-- After this migration, customer data should always be fetched via:
-- SELECT b.*, p.full_name, p.email, p.phone 
-- FROM bookings b 
-- JOIN profiles p ON b.customer_id = p.id
-- 
-- Or use the bookings_with_payments view which includes customer data automatically
