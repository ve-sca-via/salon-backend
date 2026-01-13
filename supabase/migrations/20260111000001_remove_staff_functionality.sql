-- Migration: Remove all staff-related functionality
-- Created: 2026-01-11
-- Description: Drops staff_availability and salon_staff tables, removes staff_count from vendor_join_requests

-- Drop foreign key constraints first (to avoid dependency issues)
ALTER TABLE IF EXISTS "public"."staff_availability" 
    DROP CONSTRAINT IF EXISTS "staff_availability_staff_id_fkey";

-- Drop indexes related to staff tables
DROP INDEX IF EXISTS "public"."idx_salon_staff_salon_id";
DROP INDEX IF EXISTS "public"."idx_salon_staff_user_id";

-- Drop staff_availability table (dependent on salon_staff)
DROP TABLE IF EXISTS "public"."staff_availability";

-- Drop salon_staff table
DROP TABLE IF EXISTS "public"."salon_staff";

-- Remove staff_count column from vendor_join_requests
ALTER TABLE "public"."vendor_join_requests" 
    DROP COLUMN IF EXISTS "staff_count";

-- Add comment documenting the removal
COMMENT ON TABLE "public"."vendor_join_requests" IS 'RLS disabled - backend uses service_role with FastAPI auth. Staff management removed as of 2026-01-11.';
