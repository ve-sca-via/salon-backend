-- Add time_slots column to bookings table for multiple time slot support
-- Allows customers to select up to 3 time slots for their booking

ALTER TABLE public.bookings 
ADD COLUMN time_slots JSONB DEFAULT '[]'::jsonb;

COMMENT ON COLUMN public.bookings.time_slots IS 'Array of time slots (max 3) for the booking. JSON array of time strings.';

-- Create index for querying bookings by time slots
CREATE INDEX idx_bookings_time_slots ON public.bookings USING GIN (time_slots);

COMMENT ON INDEX idx_bookings_time_slots IS 'GIN index for efficient time slot queries';

-- Add constraint to ensure time_slots is an array
ALTER TABLE public.bookings 
ADD CONSTRAINT time_slots_is_array CHECK (jsonb_typeof(time_slots) = 'array');

-- Add constraint to limit maximum 3 time slots
ALTER TABLE public.bookings 
ADD CONSTRAINT time_slots_max_3 CHECK (jsonb_array_length(time_slots) <= 3);
