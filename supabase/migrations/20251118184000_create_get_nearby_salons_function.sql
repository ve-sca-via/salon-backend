-- Create function to get nearby salons using PostGIS
-- This function finds salons within a specified radius using location coordinates

CREATE OR REPLACE FUNCTION public.get_nearby_salons(
    user_lat DOUBLE PRECISION,
    user_lon DOUBLE PRECISION,
    radius_km DOUBLE PRECISION DEFAULT 10.0,
    max_results INTEGER DEFAULT 50
)
RETURNS TABLE (
    id UUID,
    business_name VARCHAR,
    description TEXT,
    address TEXT,
    city VARCHAR,
    state VARCHAR,
    pincode VARCHAR,
    phone VARCHAR,
    email VARCHAR,
    latitude NUMERIC,
    longitude NUMERIC,
    location GEOGRAPHY,
    average_rating NUMERIC,
    total_reviews INTEGER,
    logo_url TEXT,
    cover_images TEXT[],
    opening_time TIME,
    closing_time TIME,
    working_days VARCHAR[],
    is_active BOOLEAN,
    is_verified BOOLEAN,
    registration_fee_paid BOOLEAN,
    vendor_id UUID,
    assigned_rm UUID,
    distance_km DOUBLE PRECISION,
    created_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.id,
        s.business_name,
        s.description,
        s.address,
        s.city,
        s.state,
        s.pincode,
        s.phone,
        s.email,
        s.latitude,
        s.longitude,
        s.location,
        s.average_rating,
        s.total_reviews,
        s.logo_url,
        s.cover_images,
        s.opening_time,
        s.closing_time,
        s.working_days,
        s.is_active,
        s.is_verified,
        s.registration_fee_paid,
        s.vendor_id,
        s.assigned_rm,
        -- Calculate distance in kilometers using PostGIS
        ST_Distance(
            s.location::geography,
            ST_SetSRID(ST_MakePoint(user_lon, user_lat), 4326)::geography
        ) / 1000.0 AS distance_km,
        s.created_at
    FROM 
        salons s
    WHERE 
        s.is_active = true
        AND s.is_verified = true
        AND s.registration_fee_paid = true
        AND s.deleted_at IS NULL
        AND s.location IS NOT NULL
        -- Filter by radius using PostGIS distance function
        AND ST_DWithin(
            s.location::geography,
            ST_SetSRID(ST_MakePoint(user_lon, user_lat), 4326)::geography,
            radius_km * 1000  -- Convert km to meters
        )
    ORDER BY 
        distance_km ASC
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql STABLE;

-- Add comment
COMMENT ON FUNCTION public.get_nearby_salons IS 'Find salons within a radius using PostGIS spatial queries';
