-- Add join_request_id to salons table
ALTER TABLE public.salons 
ADD COLUMN IF NOT EXISTS join_request_id UUID REFERENCES vendor_join_requests(id) ON DELETE SET NULL;

-- Add index for performance
CREATE INDEX IF NOT EXISTS idx_salons_join_request 
ON salons(join_request_id);

-- Add comment
COMMENT ON COLUMN public.salons.join_request_id IS 'Original vendor join request that led to this salon creation';
