-- ============================================================================
-- STORAGE BUCKETS & POLICIES
-- ============================================================================
-- Create storage buckets for salon images

-- Create salon-images bucket (public access for salon photos)
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'salon-images',
  'salon-images',
  true,  -- Public bucket so images are accessible via URL
  5242880,  -- 5MB file size limit
  ARRAY['image/jpeg', 'image/png', 'image/webp', 'image/jpg']
)
ON CONFLICT (id) DO NOTHING;

-- Allow anyone to read images (public bucket)
CREATE POLICY "Public Access"
ON storage.objects FOR SELECT
USING (bucket_id = 'salon-images');

-- Only service role can upload (backend uses service_role_key)
CREATE POLICY "Service role can upload"
ON storage.objects FOR INSERT
WITH CHECK (
  bucket_id = 'salon-images'
  AND auth.role() = 'service_role'
);

-- Only service role can update
CREATE POLICY "Service role can update"
ON storage.objects FOR UPDATE
USING (
  bucket_id = 'salon-images'
  AND auth.role() = 'service_role'
)
WITH CHECK (
  bucket_id = 'salon-images'
  AND auth.role() = 'service_role'
);

-- Only service role can delete
CREATE POLICY "Service role can delete"
ON storage.objects FOR DELETE
USING (
  bucket_id = 'salon-images'
  AND auth.role() = 'service_role'
);
