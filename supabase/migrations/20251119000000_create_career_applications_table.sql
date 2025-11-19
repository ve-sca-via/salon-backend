-- Create career_applications table
CREATE TABLE IF NOT EXISTS public.career_applications (
    -- Primary Key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Personal Information
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT NOT NULL,
    current_city TEXT,
    current_address TEXT,
    willing_to_relocate BOOLEAN DEFAULT FALSE,
    
    -- Job Details
    position TEXT NOT NULL DEFAULT 'Relationship Manager',
    experience_years INTEGER DEFAULT 0,
    previous_company TEXT,
    current_salary NUMERIC(10, 2),
    expected_salary NUMERIC(10, 2),
    notice_period_days INTEGER,
    
    -- Educational Background
    highest_qualification TEXT,
    university_name TEXT,
    graduation_year INTEGER,
    
    -- Additional Information
    cover_letter TEXT,
    linkedin_url TEXT,
    portfolio_url TEXT,
    
    -- Document URLs
    resume_url TEXT NOT NULL,
    aadhaar_url TEXT NOT NULL,
    pan_url TEXT NOT NULL,
    photo_url TEXT NOT NULL,
    address_proof_url TEXT NOT NULL,
    educational_certificates_url JSONB, -- Array of URLs
    experience_letter_url TEXT,
    salary_slip_url TEXT,
    
    -- Application Status
    status TEXT NOT NULL DEFAULT 'pending',
    admin_notes TEXT,
    rejection_reason TEXT,
    interview_scheduled_at TIMESTAMPTZ,
    interview_location TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add indexes for common queries
CREATE INDEX IF NOT EXISTS idx_career_applications_status ON public.career_applications(status);
CREATE INDEX IF NOT EXISTS idx_career_applications_position ON public.career_applications(position);
CREATE INDEX IF NOT EXISTS idx_career_applications_email ON public.career_applications(email);
CREATE INDEX IF NOT EXISTS idx_career_applications_created_at ON public.career_applications(created_at DESC);

-- Add constraint for valid status values
ALTER TABLE public.career_applications 
ADD CONSTRAINT valid_status CHECK (
    status IN ('pending', 'under_review', 'shortlisted', 'interview_scheduled', 'rejected', 'hired')
);

-- Create updated_at trigger
CREATE OR REPLACE FUNCTION update_career_applications_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_career_applications_updated_at
    BEFORE UPDATE ON public.career_applications
    FOR EACH ROW
    EXECUTE FUNCTION update_career_applications_updated_at();

-- Enable Row Level Security (RLS)
ALTER TABLE public.career_applications ENABLE ROW LEVEL SECURITY;

-- Policy: Allow public to insert (submit applications)
CREATE POLICY "Anyone can submit career applications"
    ON public.career_applications
    FOR INSERT
    TO public
    WITH CHECK (true);

-- Policy: Allow admins to view all applications
CREATE POLICY "Admins can view all career applications"
    ON public.career_applications
    FOR SELECT
    TO authenticated
    USING (
        auth.jwt() ->> 'role' = 'admin'
    );

-- Policy: Allow admins to update applications
CREATE POLICY "Admins can update career applications"
    ON public.career_applications
    FOR UPDATE
    TO authenticated
    USING (
        auth.jwt() ->> 'role' = 'admin'
    );

-- Policy: Allow admins to delete applications
CREATE POLICY "Admins can delete career applications"
    ON public.career_applications
    FOR DELETE
    TO authenticated
    USING (
        auth.jwt() ->> 'role' = 'admin'
    );

-- Add comment
COMMENT ON TABLE public.career_applications IS 'Stores career job applications for RM and other positions';
