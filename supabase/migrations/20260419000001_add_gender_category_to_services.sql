-- Add gender_category to services table
ALTER TABLE public.services
ADD COLUMN gender_category VARCHAR(10) DEFAULT 'both' CHECK (gender_category IN ('male', 'female', 'both'));

COMMENT ON COLUMN public.services.gender_category IS 'Designates the target gender for the service: male, female, or both (unisex).';
