-- =====================================================
-- Migration: Add Regular Buyer Role and B2B Pricing
-- Purpose: Support B2B customers with discounted pricing
-- =====================================================

-- 1. Add 'regular_buyer' to user_role enum
-- Note: ALTER TYPE ... ADD VALUE cannot be executed in a transaction block in some Postgres versions.
-- Supabase migrations handle this appropriately.
ALTER TYPE public.user_role ADD VALUE IF NOT EXISTS 'regular_buyer';

-- 2. Update products table for B2B pricing
ALTER TABLE public.products 
ADD COLUMN IF NOT EXISTS b2b_discount_price NUMERIC(10,2) CHECK (b2b_discount_price IS NULL OR b2b_discount_price >= 0),
ADD COLUMN IF NOT EXISTS b2b_discount_percentage NUMERIC(5,2) CHECK (b2b_discount_percentage IS NULL OR (b2b_discount_percentage >= 0 AND b2b_discount_percentage <= 100));

-- 3. Update vendor_join_requests for request type
-- Distinguishes between a full Salon/Vendor request and a Regular Buyer request
ALTER TABLE public.vendor_join_requests
ADD COLUMN IF NOT EXISTS request_type TEXT DEFAULT 'salon' CHECK (request_type IN ('salon', 'regular_buyer'));

-- 4. Update salons table for salon type
-- 'regular_buyer' type salons will be hidden from public salon discovery
ALTER TABLE public.salons
ADD COLUMN IF NOT EXISTS salon_type TEXT DEFAULT 'salon' CHECK (salon_type IN ('salon', 'regular_buyer'));

-- 5. Update product_orders to track user type at time of purchase
ALTER TABLE public.product_orders
ADD COLUMN IF NOT EXISTS user_type TEXT DEFAULT 'customer';

-- 6. Add comment for documentation
COMMENT ON COLUMN public.products.b2b_discount_price IS 'Discounted price for vendors and regular buyers';
COMMENT ON COLUMN public.salons.salon_type IS 'Distinguishes between service-providing salons and product-only regular buyers';
