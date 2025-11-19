-- =====================================================
-- MAKE VENDOR_ID NULLABLE IN SALONS TABLE
-- =====================================================
-- Vendor hasn't registered yet when admin approves request
-- vendor_id will be set later when vendor completes registration
-- =====================================================

ALTER TABLE salons 
ALTER COLUMN vendor_id DROP NOT NULL;

COMMENT ON COLUMN salons.vendor_id IS 'Vendor profile ID (NULL until vendor completes registration after approval)';
