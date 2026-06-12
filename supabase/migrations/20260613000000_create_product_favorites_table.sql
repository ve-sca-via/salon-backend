-- Create product_favorites table
-- Mirrors the salon `favorites` table but for the product catalog, powering the
-- "Saved" tab (saved salons + saved products) in the mobile app.

CREATE TABLE IF NOT EXISTS product_favorites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, product_id)
);

-- Indexes for the common lookups (a user's saved products; a product's fans)
CREATE INDEX IF NOT EXISTS idx_product_favorites_user_id ON product_favorites(user_id);
CREATE INDEX IF NOT EXISTS idx_product_favorites_product_id ON product_favorites(product_id);
CREATE INDEX IF NOT EXISTS idx_product_favorites_created_at ON product_favorites(created_at DESC);

-- Grants (match the existing favorites table)
GRANT ALL ON TABLE product_favorites TO anon;
GRANT ALL ON TABLE product_favorites TO authenticated;
GRANT ALL ON TABLE product_favorites TO service_role;

-- RLS disabled: backend enforces auth via FastAPI + service_role key,
-- consistent with the rest of the schema (see favorites, cart_items, etc.).
ALTER TABLE product_favorites DISABLE ROW LEVEL SECURITY;

COMMENT ON TABLE product_favorites IS 'RLS disabled - backend uses service_role with FastAPI auth';
