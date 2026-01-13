-- Migration: Add application_number column to career_applications table
-- Date: 2026-01-12
-- Purpose: Store application number in DB for querying and tracking

-- Add application_number column (only if it doesn't exist)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'career_applications' 
        AND column_name = 'application_number'
    ) THEN
        ALTER TABLE "public"."career_applications" 
        ADD COLUMN "application_number" "text" UNIQUE;
    END IF;
END $$;

-- Create index for fast lookups by application number (only if it doesn't exist)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE schemaname = 'public' 
        AND tablename = 'career_applications' 
        AND indexname = 'idx_career_applications_application_number'
    ) THEN
        CREATE INDEX "idx_career_applications_application_number" 
        ON "public"."career_applications" USING "btree" ("application_number");
    END IF;
END $$;

-- Add comment explaining the column
COMMENT ON COLUMN "public"."career_applications"."application_number" 
IS 'Unique application number in format CA-YYYYMMDD-XXXXXXXX for applicant reference';

-- Backfill existing records with application numbers
-- Generate application numbers for existing records based on their created_at and id
UPDATE "public"."career_applications"
SET "application_number" = CONCAT(
    'CA-',
    TO_CHAR("created_at", 'YYYYMMDD'),
    '-',
    UPPER(SUBSTRING("id"::text, 1, 8))
)
WHERE "application_number" IS NULL;

-- Make column NOT NULL after backfill (only if not already NOT NULL)
DO $$ 
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'career_applications' 
        AND column_name = 'application_number'
        AND is_nullable = 'YES'
    ) THEN
        ALTER TABLE "public"."career_applications" 
        ALTER COLUMN "application_number" SET NOT NULL;
    END IF;
END $$;
