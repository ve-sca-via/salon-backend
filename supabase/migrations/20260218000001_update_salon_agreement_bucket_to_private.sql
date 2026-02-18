-- =====================================================
-- UPDATE SALON-AGREEMENT BUCKET TO PRIVATE
-- =====================================================
-- Updates the salon-agreement bucket to be private for security
-- Documents will be accessed via signed URLs only
-- =====================================================

-- Update bucket to private
UPDATE storage.buckets 
SET public = false 
WHERE id = 'salon-agreement';
