-- =====================================================
-- Migration: Add B2B Discount Pricing to Products
-- Purpose: Support wholesale pricing for vendors and regular buyers
-- =====================================================

-- 1. Add B2B pricing columns to products table
ALTER TABLE public.products 
ADD COLUMN IF NOT EXISTS b2b_discount_price NUMERIC(10,2) CHECK (b2b_discount_price IS NULL OR b2b_discount_price >= 0),
ADD COLUMN IF NOT EXISTS b2b_discount_percentage NUMERIC(5,2) CHECK (b2b_discount_percentage IS NULL OR (b2b_discount_percentage >= 0 AND b2b_discount_percentage <= 100));

-- 2. Add comments for documentation
COMMENT ON COLUMN public.products.b2b_discount_price IS 'Wholesale discounted price for Vendors and Regular Buyers';
COMMENT ON COLUMN public.products.b2b_discount_percentage IS 'Calculated discount percentage for B2B pricing';
