-- Regular buyers (salon_type = 'regular_buyer') currently share the same global
-- registration_fee_amount as vendors. This adds:
--   1. A separate global default fee for regular buyers.
--   2. A per-account override so admins can negotiate a one-off price for any
--      vendor or regular buyer, which takes precedence over whichever global
--      default would otherwise apply.

ALTER TABLE public.salons
    ADD COLUMN IF NOT EXISTS custom_registration_fee_amount numeric(10,2);

ALTER TABLE public.salons
    ADD CONSTRAINT salons_custom_registration_fee_amount_check
    CHECK (custom_registration_fee_amount IS NULL OR custom_registration_fee_amount >= 0);

COMMENT ON COLUMN public.salons.custom_registration_fee_amount IS
    'Admin-set override for this account''s one-time registration fee. NULL means '
    'fall back to the salon_type-specific system_config default '
    '(registration_fee_amount for salons, regular_buyer_registration_fee_amount for '
    'regular buyers). 0 is a valid override for a waived fee.';

-- Seed the regular-buyer default from whatever the vendor fee is currently set
-- to, so existing regular-buyer behavior does not change until an admin edits
-- the new config key.
INSERT INTO public.system_config (config_key, config_value, config_type, description, is_active)
SELECT
    'regular_buyer_registration_fee_amount',
    config_value,
    config_type,
    'One-time registration fee charged to regular buyers (B2B product-only accounts) to unlock their dashboard.',
    is_active
FROM public.system_config
WHERE config_key = 'registration_fee_amount'
ON CONFLICT (config_key) DO NOTHING;
