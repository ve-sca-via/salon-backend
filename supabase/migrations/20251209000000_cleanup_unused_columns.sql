-- ============================================================================
-- CLEANUP UNUSED COLUMNS - Multi-Service Bookings
-- ============================================================================
-- Removes unused columns from bookings table that are no longer needed
-- with the multi-service JSONB system
-- 
-- SAFE TO RUN: All removed columns are verified as unused in application code

-- ============================================================================
-- STEP 1: Remove GST columns (never used in application)
-- ============================================================================

-- GST columns were added but never implemented
-- GST is already included in service prices, not tracked separately

-- Drop check constraints first
ALTER TABLE public.bookings DROP CONSTRAINT IF EXISTS bookings_cgst_check;
ALTER TABLE public.bookings DROP CONSTRAINT IF EXISTS bookings_sgst_check;
ALTER TABLE public.bookings DROP CONSTRAINT IF EXISTS bookings_igst_check;
ALTER TABLE public.bookings DROP CONSTRAINT IF EXISTS valid_gst_sum;

-- Drop the GST columns
ALTER TABLE public.bookings DROP COLUMN IF EXISTS gst_rate;
ALTER TABLE public.bookings DROP COLUMN IF EXISTS cgst;
ALTER TABLE public.bookings DROP COLUMN IF EXISTS sgst;
ALTER TABLE public.bookings DROP COLUMN IF EXISTS igst;

COMMENT ON TABLE public.bookings IS 'Customer bookings with multi-service support via services JSONB array. Service prices are inclusive of all taxes.';

-- ============================================================================
-- STEP 2: Remove legacy single-service column
-- ============================================================================

-- service_id column is no longer used - all bookings use services JSONB array

-- Drop views that depend on service_id first
DROP VIEW IF EXISTS bookings_with_payments CASCADE;

-- Drop the foreign key constraint
ALTER TABLE public.bookings DROP CONSTRAINT IF EXISTS bookings_service_id_fkey;

-- Drop the check constraint that required either service_id OR services
ALTER TABLE public.bookings DROP CONSTRAINT IF EXISTS bookings_must_have_service;

-- Drop the service_id column
ALTER TABLE public.bookings DROP COLUMN IF EXISTS service_id;

-- Add new check constraint requiring services array
ALTER TABLE public.bookings
ADD CONSTRAINT bookings_must_have_services CHECK (
  services IS NOT NULL AND jsonb_array_length(services) > 0
);

COMMENT ON CONSTRAINT bookings_must_have_services ON public.bookings IS 'Ensures booking has services array populated with at least one service';

-- ============================================================================
-- STEP 3: Remove redundant payment tracking columns
-- ============================================================================

-- These boolean flags are redundant - payment status is tracked in payments table
-- Drop check constraints first
ALTER TABLE public.bookings DROP CONSTRAINT IF EXISTS convenience_payment_logic;
ALTER TABLE public.bookings DROP CONSTRAINT IF EXISTS service_payment_logic;

-- Drop the redundant payment tracking columns
ALTER TABLE public.bookings DROP COLUMN IF EXISTS convenience_fee_paid;
ALTER TABLE public.bookings DROP COLUMN IF EXISTS convenience_fee_paid_at;
ALTER TABLE public.bookings DROP COLUMN IF EXISTS service_price_paid;
ALTER TABLE public.bookings DROP COLUMN IF EXISTS service_price_paid_at;

-- ============================================================================
-- STEP 4: Update constraint and add documentation
-- ============================================================================

-- Update total amount constraint (simpler without GST)
ALTER TABLE public.bookings DROP CONSTRAINT IF EXISTS valid_total_amount;

ALTER TABLE public.bookings
ADD CONSTRAINT valid_total_amount CHECK (total_amount = (service_price + convenience_fee));

COMMENT ON CONSTRAINT valid_total_amount ON public.bookings IS 'Ensures total equals service price + convenience fee (all taxes included in service price)';

-- Add helpful column documentation
COMMENT ON COLUMN public.bookings.services IS 'Multi-service cart: [{service_id, service_name, quantity, unit_price, line_total, duration_minutes}]. Required for all bookings.';

COMMENT ON COLUMN public.bookings.service_price IS 'Total service amount to be paid at salon (sum of all line_total in services array)';

COMMENT ON COLUMN public.bookings.convenience_fee IS 'Platform booking fee (6% of service_price) paid online via Razorpay';

COMMENT ON COLUMN public.bookings.total_amount IS 'Complete booking amount: service_price + convenience_fee';

COMMENT ON COLUMN public.bookings.duration_minutes IS 'Total duration of all services in the booking';

-- ============================================================================
-- STEP 5: Recreate bookings_with_payments view without service_id
-- ============================================================================

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
  b.customer_name,
  b.customer_phone,
  b.customer_email,
  b.created_at,
  b.updated_at,
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
LEFT JOIN payments cf ON cf.booking_id = b.id 
  AND cf.payment_type = 'convenience_fee' 
  AND cf.deleted_at IS NULL
LEFT JOIN payments sp ON sp.booking_id = b.id 
  AND sp.payment_type = 'service_payment' 
  AND sp.deleted_at IS NULL
WHERE b.deleted_at IS NULL;

COMMENT ON VIEW bookings_with_payments IS 'Bookings with payment summary from payments table. Updated to use services JSONB array instead of service_id.';

-- ============================================================================
-- STEP 6: Verify data integrity
-- ============================================================================

-- Ensure all bookings have services array populated
DO $$
DECLARE
  invalid_count INTEGER;
BEGIN
  SELECT COUNT(*) INTO invalid_count
  FROM public.bookings
  WHERE (services IS NULL OR jsonb_array_length(services) = 0)
    AND deleted_at IS NULL;
  
  IF invalid_count > 0 THEN
    RAISE EXCEPTION 'Found % bookings without services array. Run migration 20251119120000_make_service_id_nullable.sql first to populate services from service_id', invalid_count;
  END IF;
END $$;

-- ============================================================================
-- SUMMARY
-- ============================================================================

-- Removed columns:
-- ✓ gst_rate, cgst, sgst, igst (never used, taxes included in prices)
-- ✓ service_id (replaced by services JSONB array)
-- ✓ convenience_fee_paid, convenience_fee_paid_at (tracked in payments table)
-- ✓ service_price_paid, service_price_paid_at (tracked in payments table)
--
-- Updated constraints:
-- ✓ valid_total_amount (simplified without GST)
-- ✓ bookings_must_have_services (requires services array, not service_id)
--
-- Result:
-- ✓ Cleaner schema focused on multi-service JSONB structure
-- ✓ Payment status tracked in dedicated payments table
-- ✓ No redundant or unused columns
