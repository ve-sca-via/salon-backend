-- =====================================================
-- Migration: Create service_subcategories table
-- Purpose: Introduce a second level of categorization
--          Category 1 (service_categories) → Category 2 (service_subcategories) → Services
-- =====================================================

-- 1. Create the service_subcategories table
CREATE TABLE IF NOT EXISTS service_subcategories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_category_id UUID NOT NULL REFERENCES service_categories(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    icon_url TEXT,
    display_order INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Add index on parent_category_id for fast lookups
CREATE INDEX IF NOT EXISTS idx_service_subcategories_parent_category_id 
    ON service_subcategories(parent_category_id);

-- 3. Add index for active subcategories ordered by display_order
CREATE INDEX IF NOT EXISTS idx_service_subcategories_active_order 
    ON service_subcategories(is_active, display_order);

-- 4. Add subcategory_id column to services table (nullable for backward compatibility)
ALTER TABLE services ADD COLUMN IF NOT EXISTS subcategory_id UUID REFERENCES service_subcategories(id) ON DELETE SET NULL;

-- 5. Add index on services.subcategory_id
CREATE INDEX IF NOT EXISTS idx_services_subcategory_id ON services(subcategory_id);

-- 6. Add updated_at trigger for service_subcategories
CREATE OR REPLACE FUNCTION update_service_subcategories_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_service_subcategories_updated_at ON service_subcategories;
CREATE TRIGGER trigger_update_service_subcategories_updated_at
    BEFORE UPDATE ON service_subcategories
    FOR EACH ROW
    EXECUTE FUNCTION update_service_subcategories_updated_at();

-- 7. Disable RLS on service_subcategories (consistent with other tables in this project)
ALTER TABLE service_subcategories DISABLE ROW LEVEL SECURITY;
