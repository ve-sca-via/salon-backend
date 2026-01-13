-- Migration: Clean up booking time fields for clarity
-- Date: 2026-01-09
-- Description: Remove redundant booking_time field as time_slots already stores appointment times
--              created_at already tracks when the booking was made

-- Analysis:
-- booking_time: Stores first appointment time (redundant with time_slots[0])
-- time_slots: Stores all appointment times (this is what we need)
-- created_at: Stores when booking was created (this is the true "booking time")

-- Step 1: Verify time_slots has data for all bookings
DO $$
DECLARE
  missing_count INTEGER;
BEGIN
  SELECT COUNT(*) INTO missing_count
  FROM bookings
  WHERE time_slots IS NULL OR jsonb_array_length(time_slots) = 0;
  
  IF missing_count > 0 THEN
    RAISE NOTICE 'Found % bookings without time_slots, will migrate data first', missing_count;
    
    -- Migrate booking_time to time_slots for old bookings
    UPDATE bookings
    SET time_slots = jsonb_build_array(
      to_char(booking_time::time, 'HH12:MI AM')
    )
    WHERE time_slots IS NULL OR jsonb_array_length(time_slots) = 0;
    
    RAISE NOTICE 'Migrated % bookings to use time_slots', missing_count;
  ELSE
    RAISE NOTICE 'All bookings already have time_slots data';
  END IF;
END $$;

-- Step 2: Add constraint to ensure time_slots is never empty
ALTER TABLE bookings
ADD CONSTRAINT time_slots_not_empty 
CHECK (jsonb_array_length(time_slots) > 0);

-- Step 3: Drop dependent views first
DROP VIEW IF EXISTS pending_payments CASCADE;
DROP VIEW IF EXISTS bookings_with_payments CASCADE;

-- Step 4: Drop the redundant booking_time column completely
ALTER TABLE bookings DROP COLUMN IF EXISTS booking_time;

-- Step 5: Add documentation comments for clarity
COMMENT ON COLUMN bookings.time_slots IS 
'Array of appointment time slots (1-3 slots). This is the primary field for appointment times. Format: ["2:30 PM", "4:45 PM"]';

COMMENT ON COLUMN bookings.created_at IS 
'Timestamp when the booking was created. This is the true "booking time" (when customer made the booking).';

COMMENT ON COLUMN bookings.services IS 
'Historical snapshot of booked services with prices and quantities at booking time. Preserved even if service prices change or services are deleted. This JSONB array is intentionally denormalized for audit trail purposes.';

-- Step 6: Recreate bookings_with_payments view without booking_time

CREATE OR REPLACE VIEW bookings_with_payments AS
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

COMMENT ON VIEW bookings_with_payments IS 
'Bookings with payment summary. Uses time_slots for appointment times and created_at for booking timestamp. Customer data fetched from profiles via JOIN.';


-- Step 7: Recreate pending_payments view without booking_time
CREATE OR REPLACE VIEW pending_payments AS
SELECT 
  p.id,
  p.booking_id,
  b.booking_number,
  b.booking_date,
  b.time_slots,
  p.payment_type,
  p.amount,
  p.customer_id,
  prof.full_name as customer_name,
  b.salon_id,
  s.business_name as salon_name,
  p.created_at,
  EXTRACT(EPOCH FROM (now() - p.created_at))/3600 as hours_pending
FROM payments p
JOIN bookings b ON b.id = p.booking_id
JOIN profiles prof ON prof.id = p.customer_id
JOIN salons s ON s.id = b.salon_id
WHERE p.status = 'pending'
  AND p.deleted_at IS NULL
  AND b.deleted_at IS NULL
ORDER BY p.created_at DESC;

COMMENT ON VIEW pending_payments IS 
'Pending payments view. Uses time_slots array instead of deprecated booking_time field.';