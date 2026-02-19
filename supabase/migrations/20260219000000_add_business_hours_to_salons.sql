-- Add business_hours JSONB column to salons table for day-by-day schedule
-- This allows vendors to set different hours for each day of the week
-- Format: {"monday": "9:00 AM - 6:00 PM", "tuesday": "9:00 AM - 8:00 PM", "wednesday": "Closed", ...}

ALTER TABLE public.salons 
ADD COLUMN IF NOT EXISTS business_hours JSONB DEFAULT NULL;

COMMENT ON COLUMN public.salons.business_hours IS 'Day-wise business hours in JSONB format {monday: "9:00 AM - 6:00 PM", tuesday: "Closed", ...}';
