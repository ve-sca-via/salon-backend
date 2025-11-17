-- ============================================================================
-- 03_PROFILES.SQL - USER PROFILES TABLE
-- ============================================================================
-- Production-ready user profiles with Indian compliance

CREATE TABLE profiles (
  -- Primary Key
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  
  -- Basic Info
  full_name VARCHAR(255) NOT NULL,
  email VARCHAR(255) NOT NULL UNIQUE,
  phone VARCHAR(20),
  avatar_url TEXT,
  
  -- Address (Indian format)
  address_line1 TEXT,
  address_line2 TEXT,
  city VARCHAR(100),
  state VARCHAR(100),
  pincode VARCHAR(6), -- Indian pincode (6 digits)
  
  -- Phone Verification (OTP auth)
  phone_verified BOOLEAN DEFAULT false,
  phone_verified_at TIMESTAMPTZ,
  phone_verification_method VARCHAR(50), -- 'otp', 'call', 'manual'
  
  -- User Role & Status
  user_role user_role NOT NULL DEFAULT 'customer',
  is_active BOOLEAN DEFAULT true,
  
  -- Audit Trail (Compliance)
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  deleted_at TIMESTAMPTZ,
  deleted_by UUID REFERENCES auth.users(id),
  
  -- Constraints
  CONSTRAINT valid_email 
    CHECK (email ~* '^[a-zA-Z0-9.!#$%&''*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$'),
  
  CONSTRAINT valid_phone_format 
    CHECK (phone IS NULL OR phone ~ '^\+?[1-9]\d{1,14}$'), -- E.164 international format
  
  CONSTRAINT valid_pincode_format 
    CHECK (pincode IS NULL OR pincode ~ '^\d{6}$') -- Indian 6-digit pincode
);

-- Indexes for performance
CREATE INDEX idx_profiles_email ON profiles(email) WHERE deleted_at IS NULL;
CREATE INDEX idx_profiles_phone ON profiles(phone) WHERE phone IS NOT NULL AND deleted_at IS NULL;
CREATE INDEX idx_profiles_user_role ON profiles(user_role);
CREATE INDEX idx_profiles_deleted_at ON profiles(deleted_at);
CREATE INDEX idx_profiles_city_state ON profiles(city, state) WHERE deleted_at IS NULL;

-- Unique phone constraint (only for verified phones)
CREATE UNIQUE INDEX idx_profiles_phone_unique 
  ON profiles(phone) 
  WHERE phone_verified = true AND phone IS NOT NULL AND deleted_at IS NULL;

-- Enable RLS (Row Level Security)
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

-- Updated timestamp trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_updated_at
  BEFORE UPDATE ON profiles
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

-- Table comments
COMMENT ON TABLE profiles IS 'User profiles with Indian compliance (DPDP Act 2023). Supports phone OTP authentication.';
COMMENT ON COLUMN profiles.phone_verified IS 'Whether phone number is verified via OTP';
COMMENT ON COLUMN profiles.phone_verification_method IS 'How phone was verified: otp, call, or manual';
COMMENT ON COLUMN profiles.pincode IS 'Indian 6-digit pincode (validated)';
COMMENT ON COLUMN profiles.deleted_at IS 'Soft delete timestamp (NULL = active)';
