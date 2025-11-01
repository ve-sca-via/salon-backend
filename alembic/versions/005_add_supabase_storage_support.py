"""Add Supabase Storage support and PostGIS function

Revision ID: 005
Revises: 004
Create Date: 2025-10-28

This migration adds:
1. PostGIS function for efficient nearby salon queries
2. Helper functions for geospatial queries
3. Comments documenting Supabase Storage usage

Storage buckets need to be created manually in Supabase Dashboard:
- salon-images (public)
- salon-receipts (private)
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    # ========================================
    # POSTGIS FUNCTION FOR NEARBY SALONS
    # ========================================
    
    # Create efficient distance calculation function
    op.execute("""
        CREATE OR REPLACE FUNCTION nearby_salons(
            user_lat float,
            user_lon float,
            radius_km float DEFAULT 10.0,
            max_results int DEFAULT 50
        )
        RETURNS TABLE (
            id int,
            name text,
            description text,
            email text,
            phone text,
            address_line1 text,
            address_line2 text,
            city text,
            state text,
            pincode text,
            latitude numeric,
            longitude numeric,
            business_hours jsonb,
            cover_image text,
            logo text,
            images jsonb,
            rating numeric,
            total_reviews int,
            amenities jsonb,
            specialties jsonb,
            distance_km float
        ) AS $$
        BEGIN
            RETURN QUERY
            SELECT
                s.id,
                s.name,
                s.description,
                s.email,
                s.phone,
                s.address_line1,
                s.address_line2,
                s.city,
                s.state,
                s.pincode,
                s.latitude,
                s.longitude,
                s.business_hours,
                s.cover_image,
                s.logo,
                s.images,
                s.rating,
                s.total_reviews,
                s.amenities,
                s.specialties,
                (
                    -- Haversine formula for distance calculation
                    6371 * acos(
                        cos(radians(user_lat)) *
                        cos(radians(s.latitude::float)) *
                        cos(radians(s.longitude::float) - radians(user_lon)) +
                        sin(radians(user_lat)) *
                        sin(radians(s.latitude::float))
                    )
                ) as distance_km
            FROM salons s
            WHERE s.status = 'approved'
            AND s.latitude IS NOT NULL
            AND s.longitude IS NOT NULL
            -- Rough bounding box filter for performance
            AND s.latitude BETWEEN user_lat - (radius_km / 111.0) AND user_lat + (radius_km / 111.0)
            AND s.longitude BETWEEN user_lon - (radius_km / (111.0 * cos(radians(user_lat)))) 
                                  AND user_lon + (radius_km / (111.0 * cos(radians(user_lat))))
            ORDER BY distance_km
            LIMIT max_results;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # Add function comment
    op.execute("""
        COMMENT ON FUNCTION nearby_salons IS 
        'Find salons within radius using Haversine formula. Optimized with bounding box filter.';
    """)
    
    # ========================================
    # SALON SEARCH FUNCTION
    # ========================================
    
    op.execute("""
        CREATE OR REPLACE FUNCTION search_salons(
            search_query text,
            city_filter text DEFAULT NULL,
            min_rating numeric DEFAULT 0.0,
            max_results int DEFAULT 50
        )
        RETURNS TABLE (
            id int,
            name text,
            description text,
            city text,
            state text,
            latitude numeric,
            longitude numeric,
            rating numeric,
            total_reviews int,
            cover_image text,
            relevance_score float
        ) AS $$
        BEGIN
            RETURN QUERY
            SELECT
                s.id,
                s.name,
                s.description,
                s.city,
                s.state,
                s.latitude,
                s.longitude,
                s.rating,
                s.total_reviews,
                s.cover_image,
                -- Simple relevance scoring based on name/description match
                CASE 
                    WHEN s.name ILIKE '%' || search_query || '%' THEN 10.0
                    WHEN s.description ILIKE '%' || search_query || '%' THEN 5.0
                    ELSE 1.0
                END as relevance_score
            FROM salons s
            WHERE s.status = 'approved'
            AND s.rating >= min_rating
            AND (
                s.name ILIKE '%' || search_query || '%'
                OR s.description ILIKE '%' || search_query || '%'
                OR s.city ILIKE '%' || search_query || '%'
            )
            AND (city_filter IS NULL OR s.city ILIKE city_filter)
            ORDER BY relevance_score DESC, s.rating DESC
            LIMIT max_results;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    op.execute("""
        COMMENT ON FUNCTION search_salons IS 
        'Search salons by name, description, or city with relevance scoring.';
    """)
    
    # ========================================
    # ADD COLUMN COMMENTS FOR SUPABASE STORAGE
    # ========================================
    
    op.execute("""
        COMMENT ON COLUMN salons.cover_image IS 
        'URL from Supabase Storage bucket: salon-images. Format: salons/{salon_id}/cover.jpg';
    """)
    
    op.execute("""
        COMMENT ON COLUMN salons.logo IS 
        'URL from Supabase Storage bucket: salon-images. Format: salons/{salon_id}/logo.jpg';
    """)
    
    op.execute("""
        COMMENT ON COLUMN salons.images IS 
        'Array of URLs from Supabase Storage bucket: salon-images. Format: salons/{salon_id}/gallery/{index}.jpg';
    """)


def downgrade():
    # Drop functions
    op.execute("DROP FUNCTION IF EXISTS nearby_salons(float, float, float, int);")
    op.execute("DROP FUNCTION IF EXISTS search_salons(text, text, numeric, int);")
    
    # Remove column comments
    op.execute("COMMENT ON COLUMN salons.cover_image IS NULL;")
    op.execute("COMMENT ON COLUMN salons.logo IS NULL;")
    op.execute("COMMENT ON COLUMN salons.images IS NULL;")


