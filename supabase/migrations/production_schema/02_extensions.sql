-- ============================================================================
-- 02_EXTENSIONS.SQL - POSTGRESQL EXTENSIONS
-- ============================================================================
-- Enable required extensions for geospatial, UUID, and security features

-- PostGIS for location-based features (nearby salons)
CREATE EXTENSION IF NOT EXISTS postgis;
COMMENT ON EXTENSION postgis IS 'Geospatial data types and functions for location queries';

-- UUID generation for primary keys
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
COMMENT ON EXTENSION "uuid-ossp" IS 'UUID generation functions';

-- pgcrypto for password hashing (OTP codes)
CREATE EXTENSION IF NOT EXISTS pgcrypto;
COMMENT ON EXTENSION pgcrypto IS 'Cryptographic functions for secure password/OTP hashing';
