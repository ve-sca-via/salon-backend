-- =====================================================
-- Fix storage signed-URL access (correct the policy ROLE)
-- =====================================================
-- Symptom: GET /upload/agreement-document/signed-url returned
--   {'statusCode': 400, 'error': 'not_found', 'message': 'Object not found'}
-- for objects that DO exist in the salon-agreement bucket.
--
-- Root cause: create_signed_url requires SELECT on storage.objects. The earlier
-- policy (20260221120000) granted SELECT TO service_role on the assumption that
-- the backend's service_role key would match. It does not: even with a correct
-- service_role key, the Storage API evaluates the signing query as the
-- `authenticated` role, so a `TO service_role` policy never applied and RLS
-- masked the denial as "Object not found". (A real service_role/BYPASSRLS path
-- would need no policy at all.)
--
-- Fix: scope the SELECT policy to `authenticated, service_role`. This is the
-- minimum that lets the backend sign URLs while keeping the bucket private from
-- the public anon / publishable key (anon is NOT included).
--
-- Idempotent: safe to re-run. Apply in EVERY environment (the original drift
-- came from this being a hand-run, un-versioned change).
-- =====================================================

-- Remove the prior SELECT policy variants that did not match the signing role.
DROP POLICY IF EXISTS "Service role can select all objects" ON storage.objects;
DROP POLICY IF EXISTS "temp diag select all" ON storage.objects;

CREATE POLICY "Backend can sign storage objects"
ON storage.objects
FOR SELECT
TO authenticated, service_role
USING (true);

-- NOTE: INSERT/UPDATE/DELETE policies from 20260221120000 are intentionally left
-- as-is. New document uploads now go to Cloudinary, and salon images use a public
-- bucket, so the write path is not exercised through these policies today. If a
-- Supabase upload/delete ever fails with a masked "not found"/permission error,
-- re-scope those policies to `authenticated, service_role` the same way.

-- Verify
SELECT policyname, cmd, roles
FROM pg_policies
WHERE schemaname = 'storage' AND tablename = 'objects'
ORDER BY policyname;
