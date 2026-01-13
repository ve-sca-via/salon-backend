-- Create career-documents storage bucket for job application documents
-- This bucket will store resumes, ID proofs, certificates, and other career-related documents

-- Create bucket if not exists
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'career-documents',
    'career-documents',
    false,  -- Private bucket for sensitive documents
    5242880,  -- 5MB file size limit
    ARRAY[
        'application/pdf',
        'image/jpeg',
        'image/jpg',
        'image/png',
        'image/webp',
        'image/svg+xml',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    ]
)
ON CONFLICT (id) DO NOTHING;

-- Drop existing conflicting policies if any
DROP POLICY IF EXISTS "Anyone can upload career documents" ON storage.objects;
DROP POLICY IF EXISTS "Admins can read career documents" ON storage.objects;
DROP POLICY IF EXISTS "Admins can update career documents" ON storage.objects;
DROP POLICY IF EXISTS "Admins can delete career documents" ON storage.objects;

-- Policy: Allow anyone (including public/anonymous) to upload documents during application submission
CREATE POLICY "Anyone can upload career documents"
ON storage.objects FOR INSERT TO public
WITH CHECK (bucket_id = 'career-documents');

-- Policy: Allow admins to read career documents
CREATE POLICY "Admins can read career documents"
ON storage.objects FOR SELECT TO authenticated
USING (
    bucket_id = 'career-documents' AND
    (auth.jwt() ->> 'role' = 'admin' OR auth.jwt() ->> 'role' = 'relationship_manager')
);

-- Policy: Allow admins to update career documents
CREATE POLICY "Admins can update career documents"
ON storage.objects FOR UPDATE TO authenticated
USING (
    bucket_id = 'career-documents' AND
    auth.jwt() ->> 'role' = 'admin'
);

-- Policy: Allow admins to delete career documents
CREATE POLICY "Admins can delete career documents"
ON storage.objects FOR DELETE TO authenticated
USING (
    bucket_id = 'career-documents' AND
    auth.jwt() ->> 'role' = 'admin'
);
