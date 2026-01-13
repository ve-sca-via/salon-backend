-- Create service-category-icons storage bucket
-- Migration: Setup storage for service category icon uploads

-- Create bucket if not exists
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'service-category-icons',
    'service-category-icons',
    true,  -- Public bucket so icons can be accessed without auth
    5242880,  -- 5MB limit
    ARRAY['image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/svg+xml']
)
ON CONFLICT (id) DO NOTHING;

-- Drop existing policies if any
DROP POLICY IF EXISTS "Authenticated admins can upload service category icons" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated admins can update service category icons" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated admins can delete service category icons" ON storage.objects;
DROP POLICY IF EXISTS "Public users can read service category icons" ON storage.objects;

-- Create RLS policies for service-category-icons bucket

-- Allow authenticated users (admins) to upload icons
CREATE POLICY "Authenticated admins can upload service category icons"
ON storage.objects FOR INSERT TO authenticated
WITH CHECK (bucket_id = 'service-category-icons');

-- Allow authenticated users (admins) to update icons
CREATE POLICY "Authenticated admins can update service category icons"
ON storage.objects FOR UPDATE TO authenticated
USING (bucket_id = 'service-category-icons');

-- Allow authenticated users (admins) to delete icons
CREATE POLICY "Authenticated admins can delete service category icons"
ON storage.objects FOR DELETE TO authenticated
USING (bucket_id = 'service-category-icons');

-- Allow public read access to icons (so they can be displayed in apps)
CREATE POLICY "Public users can read service category icons"
ON storage.objects FOR SELECT TO public
USING (bucket_id = 'service-category-icons');
