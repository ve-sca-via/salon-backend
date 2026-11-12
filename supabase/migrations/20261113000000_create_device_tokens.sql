-- =====================================================
-- Migration: Create device_tokens
-- Purpose: Expo push tokens for the phones a user is signed in on, so the
--          backend can push to them (new-booking alerts for vendors first;
--          admin campaigns later). See docs/NOTIFICATIONS_FEATURE_PLAN.md.
-- =====================================================

CREATE TABLE IF NOT EXISTS device_tokens (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    expo_push_token  TEXT NOT NULL UNIQUE,              -- one row per physical install; reassigned on login
    platform         VARCHAR(10) NOT NULL CHECK (platform IN ('android', 'ios')),
    app              VARCHAR(20) NOT NULL CHECK (app IN ('partner-app', 'customer-app')),
    device_id        TEXT,
    is_active        BOOLEAN NOT NULL DEFAULT true,     -- false once Expo reports DeviceNotRegistered
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- "All active phones for this user" is the hot query (every booking).
CREATE INDEX IF NOT EXISTS idx_device_tokens_user_active
    ON device_tokens(user_id) WHERE is_active;

CREATE OR REPLACE FUNCTION update_device_tokens_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_device_tokens_updated_at ON device_tokens;
CREATE TRIGGER trigger_device_tokens_updated_at
    BEFORE UPDATE ON device_tokens
    FOR EACH ROW
    EXECUTE FUNCTION update_device_tokens_updated_at();

-- service_role architecture, same as banners: the backend is the only client.
ALTER TABLE device_tokens ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role has full access to device_tokens"
    ON device_tokens
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
