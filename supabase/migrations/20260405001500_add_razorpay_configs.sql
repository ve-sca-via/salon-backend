-- =====================================================
-- Migration to seed Razorpay API Configuration entries
-- =====================================================
-- Seed essential Razorpay configs to the system_config table
-- The values are placeholders so that the application 
-- does not try to encrypt/decrypt non-fernet strings.
-- Replace them via the Admin Panel UI to encrypt them.

INSERT INTO system_config (config_key, config_value, config_type, description, is_active) VALUES
    ('razorpay_key_id', 'PLEASE_UPDATE_VIA_ADMIN_PANEL', 'string', 'Public Key ID for Razorpay payments. Sent to frontend.', true),
    ('razorpay_key_secret', 'PLEASE_UPDATE_VIA_ADMIN_PANEL', 'string', 'Private Key Secret for Razorpay signature verification. Protected and encrypted.', true)
ON CONFLICT (config_key) DO NOTHING;
