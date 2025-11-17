-- ============================================================================
-- UPDATE VENDOR JOIN REQUESTS TABLE
-- ============================================================================
-- Add missing columns to match the actual form data being collected

-- Add new columns for comprehensive vendor request data
ALTER TABLE vendor_join_requests
  ADD COLUMN IF NOT EXISTS business_type VARCHAR(50),
  ADD COLUMN IF NOT EXISTS owner_name VARCHAR(255),
  ADD COLUMN IF NOT EXISTS owner_email VARCHAR(255),
  ADD COLUMN IF NOT EXISTS owner_phone VARCHAR(20),
  ADD COLUMN IF NOT EXISTS business_address TEXT,
  ADD COLUMN IF NOT EXISTS latitude DECIMAL(10, 8),
  ADD COLUMN IF NOT EXISTS longitude DECIMAL(11, 8),
  ADD COLUMN IF NOT EXISTS business_license TEXT,
  ADD COLUMN IF NOT EXISTS rm_id UUID REFERENCES rm_profiles(id),
  ADD COLUMN IF NOT EXISTS documents JSONB DEFAULT '{}'::jsonb;

-- Update existing NOT NULL constraints since we're adding columns
-- Make email/phone nullable since we have owner_email/owner_phone
ALTER TABLE vendor_join_requests
  ALTER COLUMN email DROP NOT NULL,
  ALTER COLUMN phone DROP NOT NULL;

-- Add comment
COMMENT ON COLUMN vendor_join_requests.business_type IS 'Type of business: salon, spa, etc';
COMMENT ON COLUMN vendor_join_requests.documents IS 'Additional documents as JSON';
COMMENT ON COLUMN vendor_join_requests.rm_id IS 'Relationship Manager who submitted this request';
