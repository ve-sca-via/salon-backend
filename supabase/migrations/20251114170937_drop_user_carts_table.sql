-- Drop unused user_carts table
-- This table was replaced by the normalized cart_items table
-- and is not referenced anywhere in the application code

-- Drop the table (CASCADE will handle all constraints and indexes)
DROP TABLE IF EXISTS public.user_carts CASCADE;
