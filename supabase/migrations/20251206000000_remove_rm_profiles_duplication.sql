-- Migration: Remove duplicate columns from rm_profiles table
-- Date: 2025-12-06
-- Purpose: Remove full_name, email, phone, is_active from rm_profiles as they're already in profiles table
-- This eliminates data duplication and maintains single source of truth

-- Step 1: Add any missing RM-specific columns that should be in rm_profiles
ALTER TABLE public.rm_profiles 
ADD COLUMN IF NOT EXISTS employee_id VARCHAR UNIQUE,
ADD COLUMN IF NOT EXISTS total_salons_added INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS total_approved_salons INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS joining_date DATE DEFAULT CURRENT_DATE,
ADD COLUMN IF NOT EXISTS manager_notes TEXT;

-- Step 1.5: Remove NOT NULL constraint from phone columns before cleaning
ALTER TABLE public.profiles ALTER COLUMN phone DROP NOT NULL;
ALTER TABLE public.rm_profiles ALTER COLUMN phone DROP NOT NULL;

-- Step 1.6: Clean up invalid phone numbers before migration
-- Set invalid phones to NULL to avoid constraint violations
UPDATE public.profiles
SET phone = NULL
WHERE phone IS NOT NULL 
AND (
    phone = '0000000000' OR
    phone = '' OR
    LENGTH(phone) < 10 OR
    phone !~ '^\+?[1-9][0-9]{9,14}$'
);

UPDATE public.rm_profiles
SET phone = NULL
WHERE phone IS NOT NULL 
AND (
    phone = '0000000000' OR
    phone = '' OR
    LENGTH(phone) < 10 OR
    phone !~ '^\+?[1-9][0-9]{9,14}$'
);

-- Step 2: Migrate any existing data before dropping columns
-- Update profiles table with any data from rm_profiles that might be more current
UPDATE public.profiles p
SET 
    full_name = COALESCE(rm.full_name, p.full_name),
    email = COALESCE(rm.email, p.email),
    phone = COALESCE(rm.phone, p.phone),
    is_active = COALESCE(rm.is_active, p.is_active),
    updated_at = NOW()
FROM public.rm_profiles rm
WHERE p.id = rm.id
AND (
    p.full_name IS DISTINCT FROM rm.full_name OR
    p.email IS DISTINCT FROM rm.email OR
    p.phone IS DISTINCT FROM rm.phone OR
    p.is_active IS DISTINCT FROM rm.is_active
);

-- Step 3: Drop the duplicate columns from rm_profiles
ALTER TABLE public.rm_profiles 
DROP COLUMN IF EXISTS full_name,
DROP COLUMN IF EXISTS email,
DROP COLUMN IF EXISTS phone,
DROP COLUMN IF EXISTS is_active;

-- Step 4: Ensure foreign key constraint exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'rm_profiles_id_profiles_fkey'
    ) THEN
        ALTER TABLE public.rm_profiles
        ADD CONSTRAINT rm_profiles_id_profiles_fkey
        FOREIGN KEY (id) REFERENCES public.profiles(id) ON DELETE CASCADE;
    END IF;
END $$;

-- Step 5: Update table comment to reflect the change
COMMENT ON TABLE public.rm_profiles IS 'Relationship Manager specific data. User data (name, email, phone) stored in profiles table.';

-- Step 6: Create a view for convenience (optional - provides backward compatibility)
CREATE OR REPLACE VIEW public.rm_profiles_with_user_data AS
SELECT 
    rm.id,
    rm.employee_id,
    rm.assigned_territories,
    rm.performance_score,
    rm.total_salons_added,
    rm.total_approved_salons,
    rm.joining_date,
    rm.manager_notes,
    rm.created_at,
    rm.updated_at,
    p.full_name,
    p.email,
    p.phone,
    p.is_active,
    p.user_role,
    p.avatar_url,
    p.phone_verified
FROM public.rm_profiles rm
JOIN public.profiles p ON rm.id = p.id;

COMMENT ON VIEW public.rm_profiles_with_user_data IS 'Convenience view combining RM-specific data with user profile data';

-- Step 7: Grant appropriate permissions on the view
GRANT SELECT ON public.rm_profiles_with_user_data TO authenticated;
GRANT SELECT ON public.rm_profiles_with_user_data TO service_role;
