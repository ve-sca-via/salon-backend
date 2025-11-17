-- ============================================================================
-- MIGRATION: Add services jsonb field to bookings table
-- ============================================================================
-- Support multiple services per booking

-- Ensure duration_minutes column exists (add if missing)
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS duration_minutes INTEGER DEFAULT 60;

-- Add services jsonb field to store array of services
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS services JSONB;

-- Add index for services queries
CREATE INDEX IF NOT EXISTS idx_bookings_services ON bookings USING GIN (services) WHERE deleted_at IS NULL;

-- Update existing bookings to populate services field from single service_id
UPDATE bookings
SET services = jsonb_build_array(
  jsonb_build_object(
    'service_id', service_id,
    'quantity', 1,
    'price', service_price,
    'duration_minutes', duration_minutes
  )
)
WHERE services IS NULL AND deleted_at IS NULL;

-- Add constraint to ensure services array is not empty
ALTER TABLE bookings ADD CONSTRAINT bookings_services_not_empty
  CHECK (jsonb_array_length(services) > 0);

-- Update RLS policies to include services field
-- (No changes needed for RLS as it's column-level)