-- =====================================================
-- REMOVE BOOKING FEE PERCENTAGE FROM SYSTEM CONFIG
-- =====================================================
-- The platform strictly uses `convenience_fee_percentage` for 
-- customer checkout fees. The `booking_fee_percentage` key 
-- is an unused duplicate and removes confusion.
-- =====================================================

DELETE FROM public.system_config 
WHERE config_key = 'booking_fee_percentage';
