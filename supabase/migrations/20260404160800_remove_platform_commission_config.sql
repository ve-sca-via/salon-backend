-- =====================================================
-- REMOVE PLATFORM COMMISSION FROM SYSTEM CONFIG
-- =====================================================
-- System has pivoted strictly to using convenience_fee_percentage,
-- and platform_commission is no longer used in business logic.
-- Removing any active configurations related to this to clean up.
-- =====================================================

DELETE FROM public.system_config 
WHERE config_key IN ('platform_commission', 'platform_commission_percentage');
