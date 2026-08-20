-- =====================================================
-- Migration: Feature Entitlements (feature_flags + profiles.is_internal)
-- Purpose: Let features ship to production before the client has paid for
--          them. A feature sits at status='internal' where only internal
--          staff can reach it; flipping it to 'enabled' hands it to the
--          client with no deploy, no migration, no branch merge.
--
-- WHY NOT A NEW user_role: 'admin' is hardcoded in require_admin, in the
--   other role dependencies, and in ~10 RLS policies in schema.sql. Adding a
--   'developer' enum value would lock that account out of all of them. Staff
--   stay user_role='admin' and carry an orthogonal is_internal flag instead.
-- =====================================================


-- =====================================================
-- 1. profiles.is_internal — WHO you are
-- =====================================================
-- Purely an entitlement bypass. It grants no permission of its own: an
-- internal user still has to pass require_admin like anybody else.
ALTER TABLE profiles
    ADD COLUMN IF NOT EXISTS is_internal BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN profiles.is_internal IS
    'Internal staff (developer/agency). Bypasses feature entitlement gates. Grants no role permissions on its own.';

-- Partial index: the set is tiny (a handful of rows) and every users-list
-- query filters it out, so only index the true side.
CREATE INDEX IF NOT EXISTS idx_profiles_is_internal
    ON profiles(is_internal) WHERE is_internal = true;


-- =====================================================
-- 2. feature_flags — WHAT is sold
-- =====================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'feature_status') THEN
        CREATE TYPE feature_status AS ENUM ('internal', 'enabled', 'disabled');
    END IF;
END
$$;

COMMENT ON TYPE feature_status IS
    'internal = built but unsold (staff only) | enabled = client has it | disabled = kill switch, off for everyone';

CREATE TABLE IF NOT EXISTS feature_flags (
    key          VARCHAR(64) PRIMARY KEY,          -- Stable code identifier: 'blog'
    name         VARCHAR(120) NOT NULL,            -- Display label: 'Blog & SEO'
    description  TEXT,                             -- Shown on the internal flags screen

    status       feature_status NOT NULL DEFAULT 'internal',

    -- Audit trail for billing conversations: when did the client actually get this?
    enabled_at   TIMESTAMPTZ,
    enabled_by   UUID REFERENCES profiles(id) ON DELETE SET NULL,

    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE feature_flags IS
    'Sellable-feature registry. One row per gateable feature; new features default to internal.';

-- Auto-update updated_at (same trigger pattern as blog_posts/banners/products).
CREATE OR REPLACE FUNCTION update_feature_flags_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();

    -- Stamp enabled_at the first time a feature is handed to the client, and
    -- clear it if it is ever pulled back, so the column always answers
    -- "since when has the client had this?"
    IF NEW.status = 'enabled' AND OLD.status <> 'enabled' THEN
        NEW.enabled_at = now();
    ELSIF NEW.status <> 'enabled' THEN
        NEW.enabled_at = NULL;
        NEW.enabled_by = NULL;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_feature_flags_updated_at ON feature_flags;
CREATE TRIGGER trigger_feature_flags_updated_at
    BEFORE UPDATE ON feature_flags
    FOR EACH ROW
    EXECUTE FUNCTION update_feature_flags_updated_at();


-- =====================================================
-- 3. Seed
-- =====================================================
-- ON CONFLICT DO NOTHING so re-running never resets a feature the client has
-- already paid for back to 'internal'.
INSERT INTO feature_flags (key, name, description, status) VALUES
    ('blog', 'Blog & SEO',
     'Admin-managed blog with SEO metadata; server-rendered at /blog on the public website.',
     'internal')
ON CONFLICT (key) DO NOTHING;


-- =====================================================
-- 4. RLS (service_role architecture, same as blog_posts/banners)
-- =====================================================
ALTER TABLE feature_flags ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role has full access to feature_flags" ON feature_flags;
CREATE POLICY "Service role has full access to feature_flags"
    ON feature_flags
    FOR ALL
    USING (true)
    WITH CHECK (true);
