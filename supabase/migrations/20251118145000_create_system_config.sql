-- =====================================================
-- CREATE SYSTEM_CONFIG TABLE
-- =====================================================
-- Central configuration table for system-wide settings
-- Managed by admins via API, used for dynamic configuration
-- =====================================================

CREATE TABLE IF NOT EXISTS public.system_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    config_key VARCHAR(255) NOT NULL UNIQUE,
    config_value TEXT NOT NULL,
    config_type VARCHAR(50) NOT NULL, -- 'string', 'number', 'boolean', 'json'
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by UUID REFERENCES auth.users(id)
);

-- Indexes
CREATE INDEX idx_system_config_key ON system_config(config_key) WHERE is_active = true;
CREATE INDEX idx_system_config_active ON system_config(is_active);

-- Updated trigger
CREATE TRIGGER set_system_config_updated_at
    BEFORE UPDATE ON system_config
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- RLS Policies
ALTER TABLE system_config ENABLE ROW LEVEL SECURITY;

-- Anyone can read active configs
CREATE POLICY "Public can read active configs"
    ON system_config FOR SELECT
    USING (is_active = true);

-- Only admins can manage configs
CREATE POLICY "Admins can manage configs"
    ON system_config FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM profiles
            WHERE id = auth.uid() AND user_role = 'admin'
        )
    );

-- Comments
COMMENT ON TABLE system_config IS 'System-wide configuration for fees, limits, and scoring (managed by admins)';
COMMENT ON COLUMN system_config.config_key IS 'Unique configuration key (e.g., rm_score_per_approval)';
COMMENT ON COLUMN system_config.config_value IS 'Configuration value stored as text (parse based on config_type)';
COMMENT ON COLUMN system_config.config_type IS 'Data type: string, number, boolean, json';
COMMENT ON COLUMN system_config.is_active IS 'Whether this config is currently active';

-- Seed essential configs
INSERT INTO system_config (config_key, config_value, config_type, description, is_active) VALUES
    ('rm_score_per_approval', '10', 'number', 'RM score points awarded when vendor request is approved', true),
    ('registration_fee_amount', '5000', 'number', 'One-time vendor registration fee (INR)', true),
    ('convenience_fee_percentage', '5', 'number', 'Platform convenience fee percentage on bookings', true),
    ('booking_fee_percentage', '10', 'number', 'Booking convenience fee percentage (default 10%)', true),
    ('platform_commission', '10', 'number', 'Platform commission percentage on salon revenue', true),
    ('max_booking_advance_days', '30', 'number', 'Maximum days in advance a customer can book', true),
    ('cancellation_window_hours', '24', 'number', 'Hours before appointment that cancellation is allowed', true)
ON CONFLICT (config_key) DO NOTHING;

-- Verify
SELECT config_key, config_value, config_type, description 
FROM system_config 
ORDER BY config_key;
