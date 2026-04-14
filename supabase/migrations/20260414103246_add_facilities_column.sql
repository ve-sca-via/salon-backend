-- Add facilities JSONB column to vendor_join_requests table
ALTER TABLE public.vendor_join_requests 
ADD COLUMN IF NOT EXISTS facilities JSONB DEFAULT '{}'::jsonb;

-- Add facilities JSONB column to salons table
ALTER TABLE public.salons 
ADD COLUMN IF NOT EXISTS facilities JSONB DEFAULT '{}'::jsonb;
