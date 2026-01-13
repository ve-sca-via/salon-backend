-- Add age and gender columns to profiles table
-- Migration: 20260113000000_add_age_gender_to_profiles

-- Add age column (integer with reasonable constraints) - REQUIRED
ALTER TABLE public.profiles 
ADD COLUMN age INTEGER NOT NULL DEFAULT 18;

-- Add gender column (varchar with constraint) - REQUIRED
ALTER TABLE public.profiles 
ADD COLUMN gender VARCHAR(20) NOT NULL DEFAULT 'other';

-- Remove defaults after adding columns (since we want them required for new signups)
ALTER TABLE public.profiles 
ALTER COLUMN age DROP DEFAULT;

ALTER TABLE public.profiles 
ALTER COLUMN gender DROP DEFAULT;

-- Add check constraint for age (must be between 13 and 120)
ALTER TABLE public.profiles 
ADD CONSTRAINT valid_age_range 
CHECK (age >= 13 AND age <= 120);

-- Add check constraint for gender (must be 'male', 'female', or 'other')
ALTER TABLE public.profiles 
ADD CONSTRAINT valid_gender_value 
CHECK (gender IN ('male', 'female', 'other'));

-- Add comments for documentation
COMMENT ON COLUMN public.profiles.age IS 'User age (13-120 years, required)';
COMMENT ON COLUMN public.profiles.gender IS 'User gender: male, female, or other (required)';

-- Create index on gender for potential filtering
CREATE INDEX idx_profiles_gender ON public.profiles(gender) 
WHERE gender IS NOT NULL AND deleted_at IS NULL;
