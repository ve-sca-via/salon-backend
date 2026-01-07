-- Migration: Create get_popular_cities function for efficient city aggregation
-- This replaces client-side aggregation with database-level computation
-- Benefits:
--   1. Reduces data transfer (returns aggregated counts instead of full salon data)
--   2. Scales efficiently (works with 10K+ salons)
--   3. Case-insensitive city matching (Mumbai = mumbai = MUMBAI)
--   4. Automatic trimming of whitespace

-- =====================================================
-- Function: get_popular_cities
-- =====================================================
-- Returns top cities by salon count with proper normalization
-- Only includes active, verified salons that have paid registration fee

CREATE OR REPLACE FUNCTION get_popular_cities(result_limit INT DEFAULT 8)
RETURNS TABLE(
  city TEXT,
  salon_count BIGINT
) AS $$
BEGIN
  RETURN QUERY
  SELECT 
    LOWER(TRIM(s.city)) as city,
    COUNT(*)::BIGINT as salon_count
  FROM salons s
  WHERE s.is_active = true 
    AND s.is_verified = true 
    AND s.registration_fee_paid = true
    AND s.city IS NOT NULL
    AND TRIM(s.city) != ''
  GROUP BY LOWER(TRIM(s.city))
  ORDER BY salon_count DESC, city ASC
  LIMIT result_limit;
END;
$$ LANGUAGE plpgsql STABLE;

-- Add comment for documentation
COMMENT ON FUNCTION get_popular_cities(INT) IS 
'Returns top cities by salon count. Only includes active, verified salons. Case-insensitive city matching.';

-- Create index to optimize the query (if not exists)
CREATE INDEX IF NOT EXISTS idx_salons_city_lower 
ON salons (LOWER(TRIM(city))) 
WHERE is_active = true 
  AND is_verified = true 
  AND registration_fee_paid = true;

-- Grant execute permission to anon and authenticated roles
GRANT EXECUTE ON FUNCTION get_popular_cities(INT) TO anon;
GRANT EXECUTE ON FUNCTION get_popular_cities(INT) TO authenticated;
