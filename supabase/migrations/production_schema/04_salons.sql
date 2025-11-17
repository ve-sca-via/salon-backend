-- ============================================================================
-- 04_SALONS.SQL - SALONS TABLE
-- ============================================================================
-- Production-ready salon management with Indian GST compliance

CREATE TABLE salons (
  -- Primary Key
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Business Info
  business_name VARCHAR(255) NOT NULL,
  description TEXT,
  email VARCHAR(255) NOT NULL,
  phone VARCHAR(20) NOT NULL,
  
  -- Owner/Vendor
  vendor_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
  
  -- Location (Indian format)
  address TEXT NOT NULL,
  city VARCHAR(100) NOT NULL,
  state VARCHAR(100) NOT NULL,
  pincode VARCHAR(6) NOT NULL,
  latitude DECIMAL(10, 8),
  longitude DECIMAL(11, 8),
  location geography(POINT, 4326), -- PostGIS for nearby search
  
  -- Business Registration
  gst_number VARCHAR(15), -- Indian GST format (15 alphanumeric)
  pan_number VARCHAR(10), -- Indian PAN (optional)
  
  -- Images & Media
  logo_url TEXT,
  cover_images TEXT[] DEFAULT ARRAY[]::TEXT[],
  
  -- Rating & Reviews
  average_rating DECIMAL(3, 2) DEFAULT 0.0,
  total_reviews INTEGER DEFAULT 0,
  
  -- Business Hours
  opening_time TIME,
  closing_time TIME,
  working_days VARCHAR(100)[], -- ['monday', 'tuesday', ...]
  
  -- Status & Registration
  is_active BOOLEAN DEFAULT true,
  is_verified BOOLEAN DEFAULT false,
  verified_at TIMESTAMPTZ,
  verified_by UUID REFERENCES auth.users(id), -- Admin who verified
  
  -- Registration Payment
  registration_fee_paid BOOLEAN DEFAULT false,
  registration_payment_id UUID, -- FK added later (references vendor_registration_payments)
  
  -- Relationship Manager Assignment
  assigned_rm UUID REFERENCES auth.users(id),
  
  -- Audit Trail (Compliance)
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  created_by UUID REFERENCES auth.users(id),
  updated_by UUID REFERENCES auth.users(id),
  deleted_at TIMESTAMPTZ,
  deleted_by UUID REFERENCES auth.users(id),
  
  -- Constraints
  CONSTRAINT valid_gst_format 
    CHECK (gst_number IS NULL OR gst_number ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'),
  
  CONSTRAINT valid_pincode_format 
    CHECK (pincode ~ '^\d{6}$'),
  
  CONSTRAINT valid_rating 
    CHECK (average_rating >= 0 AND average_rating <= 5),
  
  CONSTRAINT valid_coordinates 
    CHECK (
      (latitude IS NULL AND longitude IS NULL) OR 
      (latitude IS NOT NULL AND longitude IS NOT NULL AND 
       latitude BETWEEN -90 AND 90 AND 
       longitude BETWEEN -180 AND 180)
    )
);

-- Performance Indexes
CREATE INDEX idx_salons_vendor_id ON salons(vendor_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_salons_city_state ON salons(city, state) WHERE deleted_at IS NULL;
CREATE INDEX idx_salons_location ON salons USING GIST(location) WHERE deleted_at IS NULL; -- Geospatial
CREATE INDEX idx_salons_active_verified ON salons(is_active, is_verified, registration_fee_paid) WHERE deleted_at IS NULL;
CREATE INDEX idx_salons_deleted_at ON salons(deleted_at);
CREATE INDEX idx_salons_assigned_rm ON salons(assigned_rm) WHERE deleted_at IS NULL;
CREATE INDEX idx_salons_rating ON salons(average_rating DESC) WHERE is_active = true AND deleted_at IS NULL;

-- Unique constraint
CREATE UNIQUE INDEX idx_salons_gst_unique 
  ON salons(gst_number) 
  WHERE gst_number IS NOT NULL AND deleted_at IS NULL;

-- Enable RLS
ALTER TABLE salons ENABLE ROW LEVEL SECURITY;

-- Updated timestamp trigger
CREATE TRIGGER set_updated_at
  BEFORE UPDATE ON salons
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

-- Auto-update location point from lat/lng
CREATE OR REPLACE FUNCTION update_salon_location()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.latitude IS NOT NULL AND NEW.longitude IS NOT NULL THEN
    NEW.location := ST_SetSRID(ST_MakePoint(NEW.longitude, NEW.latitude), 4326)::geography;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_salon_location
  BEFORE INSERT OR UPDATE OF latitude, longitude ON salons
  FOR EACH ROW
  EXECUTE FUNCTION update_salon_location();

-- Table comments
COMMENT ON TABLE salons IS 'Salon business profiles with Indian GST compliance and geospatial location';
COMMENT ON COLUMN salons.gst_number IS 'Indian GST number (15 chars: 2-digit state code + 10-char PAN + entity + checksum)';
COMMENT ON COLUMN salons.location IS 'PostGIS geography point for nearby salon queries (auto-populated from lat/lng)';
COMMENT ON COLUMN salons.registration_fee_paid IS 'Whether vendor paid one-time platform registration fee';
COMMENT ON COLUMN salons.deleted_at IS 'Soft delete timestamp (NULL = active)';
