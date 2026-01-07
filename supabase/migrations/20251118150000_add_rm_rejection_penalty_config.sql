-- =====================================================
-- ADD RM REJECTION PENALTY CONFIGURATION
-- =====================================================
-- Adds system config for automatic RM score penalty when requests are rejected
-- Production scoring system: Reward approvals (+10), Penalize rejections (-5)

-- Insert RM rejection penalty config (if not exists)
INSERT INTO system_config (
    config_key,
    config_value,
    config_type,
    description,
    is_active
)
VALUES (
    'rm_rejection_penalty',
    '-5',
    'number',
    'RM score penalty when vendor request is rejected (negative number). Incentivizes quality submissions.',
    true
)
ON CONFLICT (config_key) DO UPDATE
SET 
    description = EXCLUDED.description,
    updated_at = now();

-- Verify config exists
SELECT 
    config_key,
    config_value,
    config_type,
    description,
    is_active,
    created_at
FROM system_config
WHERE config_key IN ('rm_score_per_approval', 'rm_rejection_penalty')
ORDER BY config_key;

COMMENT ON TABLE system_config IS 'System-wide configuration for fees, limits, and scoring (managed by admins)';
