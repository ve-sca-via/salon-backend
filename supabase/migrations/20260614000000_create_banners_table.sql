-- =====================================================
-- Migration: Create Banners Table
-- Purpose: Admin-managed home-screen carousel banners for the mobile app.
--          Replaces the previously hardcoded hero image so marketing can
--          add/reorder/disable promotional banners without an app release.
-- =====================================================

-- Banners table
CREATE TABLE IF NOT EXISTS banners (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title       TEXT,                                   -- Optional caption / alt text / admin label
    image_url   TEXT NOT NULL,                          -- Cloudinary URL (same delivery as product images)
    link_url    TEXT,                                   -- Optional tap target (deep link or external URL)
    sort_order  INTEGER NOT NULL DEFAULT 0,             -- Ascending display order in the carousel
    is_active   BOOLEAN NOT NULL DEFAULT true,          -- Soft on/off without deleting
    starts_at   TIMESTAMPTZ,                            -- Optional schedule window start (NULL = always)
    ends_at     TIMESTAMPTZ,                            -- Optional schedule window end   (NULL = never expires)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for the public carousel query (active, ordered) and admin listing
CREATE INDEX IF NOT EXISTS idx_banners_is_active ON banners(is_active);
CREATE INDEX IF NOT EXISTS idx_banners_sort_order ON banners(sort_order ASC);
CREATE INDEX IF NOT EXISTS idx_banners_created_at ON banners(created_at DESC);

-- Auto-update updated_at on row modification (same pattern as products)
CREATE OR REPLACE FUNCTION update_banners_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_banners_updated_at ON banners;
CREATE TRIGGER trigger_banners_updated_at
    BEFORE UPDATE ON banners
    FOR EACH ROW
    EXECUTE FUNCTION update_banners_updated_at();

-- RLS enabled with a service-role full-access policy (service_role architecture,
-- same as products/activity_logs/etc. — the backend uses the service_role key).
ALTER TABLE banners ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role has full access to banners"
    ON banners
    FOR ALL
    USING (true)
    WITH CHECK (true);
