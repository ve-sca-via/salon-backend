-- =====================================================
-- Migration: Create Products Table
-- Purpose: E-commerce product catalog for the salon platform
-- =====================================================

-- Products table
CREATE TABLE IF NOT EXISTS products (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    slug                TEXT UNIQUE NOT NULL,
    description         TEXT,
    short_description   TEXT,
    price               NUMERIC(10,2) NOT NULL CHECK (price >= 0),
    discount_price      NUMERIC(10,2) CHECK (discount_price IS NULL OR discount_price >= 0),
    discount_percentage NUMERIC(5,2) CHECK (discount_percentage IS NULL OR (discount_percentage >= 0 AND discount_percentage <= 100)),
    sku                 TEXT UNIQUE,
    category            TEXT NOT NULL DEFAULT 'general',
    brand               TEXT,
    image_urls          TEXT[] NOT NULL DEFAULT '{}',
    stock_quantity      INTEGER NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
    is_active           BOOLEAN NOT NULL DEFAULT true,
    is_featured         BOOLEAN NOT NULL DEFAULT false,
    tags                TEXT[] DEFAULT '{}',
    weight              TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_products_is_active ON products(is_active);
CREATE INDEX IF NOT EXISTS idx_products_is_featured ON products(is_featured);
CREATE INDEX IF NOT EXISTS idx_products_slug ON products(slug);
CREATE INDEX IF NOT EXISTS idx_products_created_at ON products(created_at DESC);

-- Auto-update updated_at on row modification
CREATE OR REPLACE FUNCTION update_products_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_products_updated_at ON products;
CREATE TRIGGER trigger_products_updated_at
    BEFORE UPDATE ON products
    FOR EACH ROW
    EXECUTE FUNCTION update_products_updated_at();

-- RLS is disabled (service_role architecture, same as other tables)
ALTER TABLE products ENABLE ROW LEVEL SECURITY;

-- Allow service_role full access (backend uses service_role key)
CREATE POLICY "Service role has full access to products"
    ON products
    FOR ALL
    USING (true)
    WITH CHECK (true);
