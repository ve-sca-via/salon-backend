-- ============================================================================
-- MAKE service_id NULLABLE - Support Multi-Service Bookings
-- ============================================================================
-- The bookings table now supports multiple services via the 'services' JSONB column.
-- The legacy 'service_id' column should be nullable for backward compatibility.
-- 
-- BEFORE: service_id NOT NULL (single service only)
-- AFTER:  service_id NULL (multi-service support via 'services' jsonb)

-- Drop the NOT NULL constraint on service_id
ALTER TABLE public.bookings 
ALTER COLUMN service_id DROP NOT NULL;

-- Add comment explaining the change
COMMENT ON COLUMN public.bookings.service_id IS 'DEPRECATED: Legacy single service ID. Use services JSONB column for multi-service bookings. Kept nullable for backward compatibility.';

-- Update the foreign key to remain but allow NULL
-- (FK constraint already exists, just documenting the change)

-- Optional: Update existing single-service bookings to populate services array
-- This ensures data consistency for old bookings
UPDATE public.bookings
SET services = jsonb_build_array(
  jsonb_build_object(
    'service_id', service_id,
    'quantity', 1,
    'unit_price', service_price,
    'line_total', service_price,
    'duration_minutes', duration_minutes
  )
)
WHERE service_id IS NOT NULL 
  AND (services IS NULL OR services = '[]'::jsonb)
  AND deleted_at IS NULL;

-- Add a check constraint to ensure either service_id OR services is populated
ALTER TABLE public.bookings
ADD CONSTRAINT bookings_must_have_service CHECK (
  service_id IS NOT NULL OR (services IS NOT NULL AND jsonb_array_length(services) > 0)
);

COMMENT ON CONSTRAINT bookings_must_have_service ON public.bookings IS 'Ensures booking has either legacy service_id or new services array populated';

-- Update unique constraint for preventing double bookings
-- Drop old constraint that used service_id
DROP INDEX IF EXISTS idx_bookings_no_double_booking;

-- Recreate without service_id (just salon + datetime is enough)
CREATE UNIQUE INDEX idx_bookings_no_double_booking 
ON public.bookings(salon_id, booking_date, booking_time) 
WHERE status NOT IN ('cancelled', 'completed') AND deleted_at IS NULL;

COMMENT ON INDEX idx_bookings_no_double_booking IS 'Prevents double-booking same time slot at same salon (updated for multi-service support)';
