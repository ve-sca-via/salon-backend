-- Add accepting_bookings column to salons table
-- This allows vendors to toggle whether their salon accepts new bookings

ALTER TABLE public.salons 
ADD COLUMN accepting_bookings BOOLEAN DEFAULT true NOT NULL;

COMMENT ON COLUMN public.salons.accepting_bookings IS 'Whether salon is currently accepting new bookings (vendor can toggle)';

-- Create index for faster queries when filtering by accepting_bookings
CREATE INDEX idx_salons_accepting_bookings ON public.salons(accepting_bookings) WHERE accepting_bookings = true AND is_active = true;

COMMENT ON INDEX idx_salons_accepting_bookings IS 'Optimize queries for active salons accepting bookings';
