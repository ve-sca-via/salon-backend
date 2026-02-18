-- =====================================================
-- ADD AGREEMENT DOCUMENT SUPPORT
-- =====================================================
-- Adds agreement_document_url to salons table for storing salon agreement documents
-- Creates salon-agreement storage bucket for PDF/image documents
-- =====================================================

-- Step 1: Add agreement_document_url column to salons table
ALTER TABLE public.salons 
ADD COLUMN IF NOT EXISTS agreement_document_url TEXT;

-- Add comment for documentation
COMMENT ON COLUMN public.salons.agreement_document_url IS 'URL of the salon agreement document (PDF or image) submitted during registration';

-- Step 2: Create salon-agreement storage bucket
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'salon-agreement',
    'salon-agreement',
    false,  -- Private bucket for secure legal documents (access via signed URLs only)
    10485760,  -- 10MB file size limit
    ARRAY[
        'application/pdf',
        'image/jpeg',
        'image/jpg',
        'image/png',
        'image/webp'
    ]
)
ON CONFLICT (id) DO NOTHING;

-- Step 3: Setup Storage RLS Policies for salon-agreement bucket

-- Drop existing policies if any (for idempotency)
DROP POLICY IF EXISTS "RMs can upload salon agreements" ON storage.objects;
DROP POLICY IF EXISTS "RMs can view own salon agreements" ON storage.objects;
DROP POLICY IF EXISTS "Admins can view all salon agreements" ON storage.objects;
DROP POLICY IF EXISTS "Admins can manage salon agreements" ON storage.objects;
DROP POLICY IF EXISTS "Vendors can view their salon agreements" ON storage.objects;

-- Policy: RMs can upload salon agreement documents
CREATE POLICY "RMs can upload salon agreements"
ON storage.objects FOR INSERT TO authenticated
WITH CHECK (
    bucket_id = 'salon-agreement' AND
    EXISTS (
        SELECT 1 FROM public.profiles 
        WHERE profiles.id = auth.uid() 
        AND profiles.user_role = 'relationship_manager'::user_role
    )
);

-- Policy: RMs can view their uploaded salon agreements
CREATE POLICY "RMs can view own salon agreements"
ON storage.objects FOR SELECT TO authenticated
USING (
    bucket_id = 'salon-agreement' AND
    EXISTS (
        SELECT 1 FROM public.profiles 
        WHERE profiles.id = auth.uid() 
        AND profiles.user_role = 'relationship_manager'::user_role
    )
);

-- Policy: Admins can view all salon agreements
CREATE POLICY "Admins can view all salon agreements"
ON storage.objects FOR SELECT TO authenticated
USING (
    bucket_id = 'salon-agreement' AND
    EXISTS (
        SELECT 1 FROM public.profiles 
        WHERE profiles.id = auth.uid() 
        AND profiles.user_role = 'admin'::user_role
    )
);

-- Policy: Admins can manage (update/delete) salon agreements
CREATE POLICY "Admins can manage salon agreements"
ON storage.objects FOR DELETE TO authenticated
USING (
    bucket_id = 'salon-agreement' AND
    EXISTS (
        SELECT 1 FROM public.profiles 
        WHERE profiles.id = auth.uid() 
        AND profiles.user_role = 'admin'::user_role
    )
);

-- Policy: Vendors can view their own salon's agreement document
CREATE POLICY "Vendors can view their salon agreements"
ON storage.objects FOR SELECT TO authenticated
USING (
    bucket_id = 'salon-agreement' AND
    EXISTS (
        SELECT 1 FROM public.salons 
        WHERE salons.vendor_id = auth.uid() 
        AND salons.agreement_document_url IS NOT NULL
        AND storage.objects.name = substring(salons.agreement_document_url from '[^/]+$')
    )
);
