-- Migration: Update career_applications schema
-- Date: 2026-04-10
-- Purpose:
--   1. ADD missing columns that the frontend form sends (age, permanent_address)
--   2. DROP deprecated columns that are no longer collected by the application form
--      and serve no purpose in the current system

-- ============================================================
-- SECTION 1: ADD MISSING COLUMNS
-- ============================================================

-- Add 'age' column (applicant age, 18-70 for career applications)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'career_applications'
          AND column_name  = 'age'
    ) THEN
        ALTER TABLE public.career_applications
        ADD COLUMN age INTEGER;

        -- Sensible check constraint for job applicants
        ALTER TABLE public.career_applications
        ADD CONSTRAINT career_applications_valid_age
            CHECK (age IS NULL OR (age >= 18 AND age <= 70));

        COMMENT ON COLUMN public.career_applications.age
            IS 'Applicant age (18-70 years, optional)';
    END IF;
END $$;

-- Add 'permanent_address' column (collected in the form alongside current_address)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'career_applications'
          AND column_name  = 'permanent_address'
    ) THEN
        ALTER TABLE public.career_applications
        ADD COLUMN permanent_address TEXT;

        COMMENT ON COLUMN public.career_applications.permanent_address
            IS 'Applicant permanent/home address';
    END IF;
END $$;


-- ============================================================
-- SECTION 2: DROP UNUSED / DEPRECATED COLUMNS
-- These columns are no longer collected by the frontend form
-- and are not consumed anywhere in the backend service layer.
-- ============================================================

-- current_city  →  replaced by current_address (full address field)
ALTER TABLE public.career_applications
    DROP COLUMN IF EXISTS current_city;

-- willing_to_relocate  →  removed from the application form
ALTER TABLE public.career_applications
    DROP COLUMN IF EXISTS willing_to_relocate;

-- Job-detail columns no longer collected in the simplified form
ALTER TABLE public.career_applications
    DROP COLUMN IF EXISTS previous_company;

ALTER TABLE public.career_applications
    DROP COLUMN IF EXISTS current_salary;

ALTER TABLE public.career_applications
    DROP COLUMN IF EXISTS expected_salary;

ALTER TABLE public.career_applications
    DROP COLUMN IF EXISTS notice_period_days;

-- Education-detail columns no longer collected
ALTER TABLE public.career_applications
    DROP COLUMN IF EXISTS university_name;

ALTER TABLE public.career_applications
    DROP COLUMN IF EXISTS graduation_year;

-- Social / portfolio links no longer collected
ALTER TABLE public.career_applications
    DROP COLUMN IF EXISTS linkedin_url;

ALTER TABLE public.career_applications
    DROP COLUMN IF EXISTS portfolio_url;

-- Document columns for files that are no longer required in the form
-- pan_url  →  PAN card upload removed from frontend
ALTER TABLE public.career_applications
    DROP COLUMN IF EXISTS pan_url;

-- address_proof_url  →  address proof upload removed from frontend
ALTER TABLE public.career_applications
    DROP COLUMN IF EXISTS address_proof_url;

-- Educational certificates upload removed from frontend
ALTER TABLE public.career_applications
    DROP COLUMN IF EXISTS educational_certificates_url;

-- Optional experience letter upload removed from frontend
ALTER TABLE public.career_applications
    DROP COLUMN IF EXISTS experience_letter_url;

-- Optional salary slip upload removed from frontend
ALTER TABLE public.career_applications
    DROP COLUMN IF EXISTS salary_slip_url;
