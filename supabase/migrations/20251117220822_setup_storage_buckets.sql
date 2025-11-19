-- Create bucket if not exists
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'salon-images',
    'salon-images',
    true,
    52428800,
    ARRAY['image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif']
)
ON CONFLICT (id) DO NOTHING;

-- Drop existing conflicting policies
DROP POLICY IF EXISTS "Authenticated users can upload salon images" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated users can update salon images" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated users can delete salon images" ON storage.objects;
DROP POLICY IF EXISTS "Public users can read salon images" ON storage.objects;

-- Recreate policies
CREATE POLICY "Authenticated users can upload salon images"
ON storage.objects FOR INSERT TO authenticated
WITH CHECK (bucket_id = 'salon-images');

CREATE POLICY "Authenticated users can update salon images"
ON storage.objects FOR UPDATE TO authenticated
USING (bucket_id = 'salon-images');

CREATE POLICY "Authenticated users can delete salon images"
ON storage.objects FOR DELETE TO authenticated
USING (bucket_id = 'salon-images');

CREATE POLICY "Public users can read salon images"
ON storage.objects FOR SELECT TO public
USING (bucket_id = 'salon-images');
