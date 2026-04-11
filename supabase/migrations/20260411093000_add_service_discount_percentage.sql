-- Migration: Add discount percentage support for vendor services
-- Date: 2026-04-11
-- Purpose:
--   1) Allow vendors to set percentage-based discounts (0-100)
--   2) Keep discounted_price as computed persisted value

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'services'
          AND column_name = 'discount_percentage'
    ) THEN
        ALTER TABLE public.services
        ADD COLUMN discount_percentage NUMERIC(5,2);

        COMMENT ON COLUMN public.services.discount_percentage
            IS 'Optional percentage discount for this service. Range: 0 to 100.';
    END IF;
END $$;

-- Ensure discount percentage is always between 0 and 100 when provided
ALTER TABLE public.services
    DROP CONSTRAINT IF EXISTS services_discount_percentage_check;

ALTER TABLE public.services
    ADD CONSTRAINT services_discount_percentage_check
    CHECK (
        discount_percentage IS NULL
        OR (discount_percentage >= 0 AND discount_percentage <= 100)
    );

-- Keep discounted fields in sync at constraint level (best-effort guard)
ALTER TABLE public.services
    DROP CONSTRAINT IF EXISTS services_discount_fields_consistency_check;

ALTER TABLE public.services
    ADD CONSTRAINT services_discount_fields_consistency_check
    CHECK (
        (discount_percentage IS NULL AND discounted_price IS NULL)
        OR (discount_percentage IS NOT NULL AND discounted_price IS NOT NULL)
    );
