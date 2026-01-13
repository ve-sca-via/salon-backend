-- =====================================================
-- ADD RAZORPAY PAYMENT GATEWAY CONFIGURATIONS
-- =====================================================
-- Adds Razorpay API credentials to system_config table
-- These configs will be encrypted automatically by backend
-- (see SENSITIVE_CONFIG_KEYS in app/services/config_service.py)
--
-- Purpose: Move payment gateway credentials from environment 
-- variables to database for easier management by admins
-- =====================================================

-- Insert Razorpay Key ID (will be encrypted by backend)
INSERT INTO system_config (
    config_key,
    config_value,
    config_type,
    description,
    is_active
)
VALUES (
    'razorpay_key_id',
    'rzp_test_placeholder',  -- Replace via Admin Panel with actual key
    'string',
    'Razorpay API Key ID for payment processing (auto-encrypted)',
    true
)
ON CONFLICT (config_key) DO UPDATE
SET 
    description = EXCLUDED.description,
    updated_at = now();

-- Insert Razorpay Key Secret (will be encrypted by backend)
INSERT INTO system_config (
    config_key,
    config_value,
    config_type,
    description,
    is_active
)
VALUES (
    'razorpay_key_secret',
    'placeholder_secret_replace_via_admin',  -- Replace via Admin Panel with actual secret
    'string',
    'Razorpay API Secret Key for payment processing (auto-encrypted, sensitive)',
    true
)
ON CONFLICT (config_key) DO UPDATE
SET 
    description = EXCLUDED.description,
    updated_at = now();

-- Insert Razorpay Webhook Secret (will be encrypted by backend)
INSERT INTO system_config (
    config_key,
    config_value,
    config_type,
    description,
    is_active
)
VALUES (
    'razorpay_webhook_secret',
    'placeholder_webhook_secret',  -- Replace via Admin Panel with actual webhook secret
    'string',
    'Razorpay Webhook Secret for payment verification (auto-encrypted, sensitive)',
    true
)
ON CONFLICT (config_key) DO UPDATE
SET 
    description = EXCLUDED.description,
    updated_at = now();

-- Clean up any unused configs that might have been created from old seed script
-- These are NOT IMPLEMENTED in code and should be removed if they exist
-- Safe to delete as these were never properly implemented or used
DELETE FROM system_config 
WHERE config_key IN (
    'platform_convenience_fee',          -- DEPRECATED: use convenience_fee_percentage
    'rm_commission_rate',                -- NOT IMPLEMENTED
    'rm_score_per_booking',              -- NOT IMPLEMENTED
    'rm_score_per_salon',                -- NOT IMPLEMENTED
    'max_bookings_per_day',              -- NOT IMPLEMENTED
    'booking_cancellation_window',       -- NOT IMPLEMENTED (use cancellation_window_hours)
    'enable_sms_notifications',          -- NOT IMPLEMENTED
    'enable_email_notifications',        -- NOT IMPLEMENTED
    'min_advance_booking_hours'          -- NOT IMPLEMENTED
);

-- Verify all active configs
SELECT 
    config_key,
    CASE 
        WHEN config_key IN ('razorpay_key_secret', 'razorpay_key_id', 'razorpay_webhook_secret') 
        THEN '[ENCRYPTED - will be encrypted by backend]'
        ELSE config_value
    END as display_value,
    config_type,
    description,
    is_active,
    created_at
FROM system_config
WHERE is_active = true
ORDER BY 
    CASE 
        WHEN config_key LIKE 'razorpay%' THEN 1
        WHEN config_key LIKE 'rm_%' THEN 2
        WHEN config_key LIKE '%fee%' THEN 3
        ELSE 4
    END,
    config_key;

-- Add helpful comments
COMMENT ON COLUMN system_config.config_value IS 'Configuration value stored as text (parse based on config_type). Sensitive values are encrypted by backend.';

-- Log migration success
DO $$
BEGIN
    RAISE NOTICE '✓ Migration completed: Razorpay configs added to system_config';
    RAISE NOTICE '⚠ IMPORTANT: Update actual Razorpay credentials via Admin Panel';
    RAISE NOTICE '  1. Login to Admin Panel';
    RAISE NOTICE '  2. Go to System Config';
    RAISE NOTICE '  3. Update razorpay_key_id with your actual key';
    RAISE NOTICE '  4. Update razorpay_key_secret with your actual secret';
    RAISE NOTICE '  5. Update razorpay_webhook_secret with your webhook secret';
END $$;
