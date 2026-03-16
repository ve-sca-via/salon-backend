-- Migration: Add outlet and isGST columns to vendor_join_requests and salons tables
-- Created: 2026-03-16

-- Create enum type for outlet options
CREATE TYPE outlet_type AS ENUM ('franchisee', 'Company owned');

-- Add columns to vendor_join_requests table
ALTER TABLE public.vendor_join_requests
    ADD COLUMN outlet outlet_type,
    ADD COLUMN is_gst BOOLEAN DEFAULT false;

-- Add columns to salons table
ALTER TABLE public.salons
    ADD COLUMN outlet outlet_type,
    ADD COLUMN is_gst BOOLEAN DEFAULT false;

-- Add comments for documentation
COMMENT ON COLUMN public.vendor_join_requests.outlet IS 'Type of outlet: franchisee or Company owned';
COMMENT ON COLUMN public.vendor_join_requests.is_gst IS 'Whether the business has GST registration';
COMMENT ON COLUMN public.salons.outlet IS 'Type of outlet: franchisee or Company owned';
COMMENT ON COLUMN public.salons.is_gst IS 'Whether the salon has GST registration';
