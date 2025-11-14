-- ============================================
-- Career Applications Migration
-- ============================================
-- Creates table and storage for RM job applications
-- Stores applicant data and document references

-- Create career_applications table
CREATE TABLE IF NOT EXISTS public.career_applications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Personal Information
  full_name VARCHAR(255) NOT NULL,
  email VARCHAR(255) NOT NULL,
  phone VARCHAR(20) NOT NULL,
  current_city VARCHAR(100),
  current_address TEXT,
  willing_to_relocate BOOLEAN DEFAULT false,
  
  -- Job Details
  position VARCHAR(100) DEFAULT 'Relationship Manager' NOT NULL,
  experience_years INTEGER DEFAULT 0,
  previous_company VARCHAR(255),
  current_salary DECIMAL(10,2),
  expected_salary DECIMAL(10,2),
  notice_period_days INTEGER,
  
  -- Educational Background
  highest_qualification VARCHAR(100),
  university_name VARCHAR(255),
  graduation_year INTEGER,
  
  -- Document URLs (stored in Supabase Storage)
  resume_url TEXT NOT NULL,
  aadhaar_url TEXT NOT NULL,
  pan_url TEXT NOT NULL,
  photo_url TEXT NOT NULL,
  address_proof_url TEXT NOT NULL,
  educational_certificates_url TEXT[],
  experience_letter_url TEXT,
  salary_slip_url TEXT,
  
  -- Application Status & Review
  status VARCHAR(50) DEFAULT 'pending' NOT NULL,
  reviewed_by UUID,
  reviewed_at TIMESTAMP WITH TIME ZONE,
  admin_notes TEXT,
  rejection_reason TEXT,
  
  -- Interview Details (if shortlisted)
  interview_scheduled_at TIMESTAMP WITH TIME ZONE,
  interview_location TEXT,
  interview_feedback TEXT,
  
  -- Additional Info
  cover_letter TEXT,
  linkedin_url TEXT,
  portfolio_url TEXT,
  reference_contacts TEXT,
  
  -- Metadata
  source VARCHAR(100) DEFAULT 'website',
  ip_address INET,
  user_agent TEXT,
  
  -- Timestamps
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE public.career_applications ENABLE ROW LEVEL SECURITY;

-- RLS Policies
-- Authenticated users can view all applications (for admin panel)
CREATE POLICY "Authenticated users can view career applications"
  ON public.career_applications
  FOR SELECT
  TO authenticated
  USING (true);

-- Authenticated users can update applications
CREATE POLICY "Authenticated users can update career applications"
  ON public.career_applications
  FOR UPDATE
  TO authenticated
  USING (true)
  WITH CHECK (true);

-- Public can insert (anyone can apply without account)
CREATE POLICY "Anyone can submit career applications"
  ON public.career_applications
  FOR INSERT
  TO public
  WITH CHECK (true);

-- Create indexes for better query performance
CREATE INDEX idx_career_applications_status ON public.career_applications(status);
CREATE INDEX idx_career_applications_email ON public.career_applications(email);
CREATE INDEX idx_career_applications_position ON public.career_applications(position);
CREATE INDEX idx_career_applications_created_at ON public.career_applications(created_at DESC);
CREATE INDEX idx_career_applications_reviewed_by ON public.career_applications(reviewed_by);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_career_applications_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to automatically update updated_at
CREATE TRIGGER set_career_applications_updated_at
  BEFORE UPDATE ON public.career_applications
  FOR EACH ROW
  EXECUTE FUNCTION update_career_applications_updated_at();

-- ============================================
-- Storage Bucket Setup
-- ============================================

-- Create storage bucket for career documents (private)
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'career-documents',
  'career-documents',
  false, -- Private bucket (not publicly accessible)
  5242880, -- 5MB limit per file
  ARRAY[
    'application/pdf',
    'image/jpeg',
    'image/jpg',
    'image/png',
    'image/webp'
  ]
)
ON CONFLICT (id) DO NOTHING;

-- Storage RLS Policies
-- Anyone can upload career documents (public insert)
CREATE POLICY "Anyone can upload career documents"
  ON storage.objects
  FOR INSERT
  TO public
  WITH CHECK (bucket_id = 'career-documents');

-- Authenticated users can view career documents
CREATE POLICY "Authenticated users can view career documents"
  ON storage.objects
  FOR SELECT
  TO authenticated
  USING (bucket_id = 'career-documents');

-- Authenticated users can delete career documents
CREATE POLICY "Authenticated users can delete career documents"
  ON storage.objects
  FOR DELETE
  TO authenticated
  USING (bucket_id = 'career-documents');

-- ============================================
-- Comments
-- ============================================

COMMENT ON TABLE public.career_applications IS 'Stores career applications for RM and other positions';
COMMENT ON COLUMN public.career_applications.status IS 'Application status: pending, under_review, shortlisted, interview_scheduled, rejected, hired';
COMMENT ON COLUMN public.career_applications.educational_certificates_url IS 'Array of URLs for multiple educational certificates';
COMMENT ON COLUMN public.career_applications.reviewed_by IS 'RM or admin who reviewed the application';
