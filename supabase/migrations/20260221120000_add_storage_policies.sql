-- =====================================================
-- Storage RLS Policies for Signed URLs
-- 
-- Issue: create_signed_url() requires SELECT permission on storage.objects
-- This migration adds policies to allow service_role to create signed URLs
-- 
-- IMPORTANT: Run this in Supabase Dashboard SQL Editor (not via CLI)
-- The Dashboard has proper permissions to modify storage.objects
-- =====================================================

-- Note: RLS is already enabled on storage.objects by default in Supabase
-- Using DROP POLICY IF EXISTS to make this migration idempotent

-- =====================================================
-- POLICY 1: Allow service_role to SELECT objects
-- Required for: create_signed_url() operations
-- =====================================================

DROP POLICY IF EXISTS "Service role can select all objects" ON storage.objects;
CREATE POLICY "Service role can select all objects"
ON storage.objects
FOR SELECT
TO service_role
USING (true);

-- =====================================================
-- POLICY 2: Allow service_role to INSERT objects  
-- Required for: File uploads via backend
-- =====================================================

DROP POLICY IF EXISTS "Service role can insert all objects" ON storage.objects;
CREATE POLICY "Service role can insert all objects"
ON storage.objects
FOR INSERT
TO service_role
WITH CHECK (true);

-- =====================================================
-- POLICY 3: Allow service_role to UPDATE objects
-- Required for: File updates/overwrites
-- =====================================================

DROP POLICY IF EXISTS "Service role can update all objects" ON storage.objects;
CREATE POLICY "Service role can update all objects"
ON storage.objects
FOR UPDATE
TO service_role
USING (true)
WITH CHECK (true);

-- =====================================================
-- POLICY 4: Allow service_role to DELETE objects
-- Required for: File deletions
-- =====================================================

DROP POLICY IF EXISTS "Service role can delete all objects" ON storage.objects;
CREATE POLICY "Service role can delete all objects"
ON storage.objects
FOR DELETE
TO service_role
USING (true);

-- =====================================================
-- Optional: Allow authenticated users to view their own files
-- Uncomment if you want users to access files directly
-- =====================================================

-- CREATE POLICY "Users can view their own files"
-- ON storage.objects
-- FOR SELECT
-- TO authenticated
-- USING (
--   (select auth.jwt()->>'sub') = owner_id
-- );

-- =====================================================
-- Verification
-- =====================================================

-- Check that policies are created
SELECT 
  schemaname,
  tablename,
  policyname,
  permissive,
  roles,
  cmd
FROM pg_policies
WHERE tablename = 'objects'
  AND schemaname = 'storage'
ORDER BY policyname;
