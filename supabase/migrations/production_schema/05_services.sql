-- ============================================================================
-- 05_SERVICES.SQL - SERVICES & CATEGORIES
-- ============================================================================
-- Production-ready service catalog with categories

-- Service Categories (Hair, Spa, Nails, etc.)
CREATE TABLE service_categories (
  -- Primary Key
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Category Info
  name VARCHAR(100) NOT NULL UNIQUE,
  description TEXT,
  icon_url TEXT,
  display_order INTEGER DEFAULT 0,
  
  -- Status
  is_active BOOLEAN DEFAULT true,
  
  -- Audit Trail
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

-- Services offered by salons
CREATE TABLE services (
  -- Primary Key
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Service Info
  name VARCHAR(255) NOT NULL,
  description TEXT,
  category_id UUID NOT NULL REFERENCES service_categories(id) ON DELETE RESTRICT,
  salon_id UUID NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
  
  -- Pricing
  price NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
  discounted_price NUMERIC(10, 2) CHECK (discounted_price IS NULL OR discounted_price >= 0),
  
  -- Duration
  duration_minutes INTEGER NOT NULL CHECK (duration_minutes > 0),
  
  -- Images
  image_url TEXT,
  
  -- Status
  is_active BOOLEAN DEFAULT true,
  is_featured BOOLEAN DEFAULT false,
  
  -- Audit Trail (Compliance)
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  created_by UUID REFERENCES auth.users(id),
  updated_by UUID REFERENCES auth.users(id),
  deleted_at TIMESTAMPTZ,
  deleted_by UUID REFERENCES auth.users(id),
  
  -- Constraints
  CONSTRAINT valid_discount 
    CHECK (discounted_price IS NULL OR discounted_price < price)
);

-- Indexes for performance
CREATE INDEX idx_service_categories_active ON service_categories(is_active, display_order);

CREATE INDEX idx_services_salon_id ON services(salon_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_services_category_id ON services(category_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_services_active ON services(is_active) WHERE deleted_at IS NULL;
CREATE INDEX idx_services_featured ON services(is_featured) WHERE is_featured = true AND deleted_at IS NULL;
CREATE INDEX idx_services_price ON services(price) WHERE is_active = true AND deleted_at IS NULL;
CREATE INDEX idx_services_deleted_at ON services(deleted_at);

-- Enable RLS
ALTER TABLE service_categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE services ENABLE ROW LEVEL SECURITY;

-- Updated timestamp triggers
CREATE TRIGGER set_updated_at
  BEFORE UPDATE ON service_categories
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER set_updated_at
  BEFORE UPDATE ON services
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

-- Table comments
COMMENT ON TABLE service_categories IS 'Service categories (Hair, Spa, Nails, Makeup, etc.)';
COMMENT ON TABLE services IS 'Services offered by salons with pricing and duration';
COMMENT ON COLUMN services.price IS 'Regular price (paid at salon)';
COMMENT ON COLUMN services.discounted_price IS 'Discounted price (if any). Must be less than regular price';
COMMENT ON COLUMN services.duration_minutes IS 'Estimated service duration in minutes';
COMMENT ON COLUMN services.deleted_at IS 'Soft delete timestamp (NULL = active)';
