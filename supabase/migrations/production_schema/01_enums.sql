-- ============================================================================
-- 01_ENUMS.SQL - ALL ENUM TYPES
-- ============================================================================
-- Production-ready enum definitions for type safety

-- Booking status lifecycle
CREATE TYPE booking_status AS ENUM (
  'pending',      -- Initial state after booking created
  'confirmed',    -- Salon confirmed the booking
  'cancelled',    -- Customer or salon cancelled
  'completed',    -- Service completed successfully
  'no_show'       -- Customer didn't show up
);

-- Payment status (Razorpay flow)
CREATE TYPE payment_status AS ENUM (
  'pending',      -- Order created, awaiting payment
  'success',      -- Payment successful and verified
  'failed',       -- Payment failed
  'refunded'      -- Payment refunded to customer
);

-- Payment type classification
CREATE TYPE payment_type AS ENUM (
  'registration_fee',    -- Vendor one-time registration
  'convenience_fee',     -- Platform fee (paid online)
  'service_payment'      -- Service cost (paid at salon)
);

-- Vendor request status
CREATE TYPE request_status AS ENUM (
  'draft',        -- Vendor started but not submitted
  'pending',      -- Submitted, awaiting review
  'approved',     -- Approved by admin/RM
  'rejected'      -- Rejected with reason
);

-- User roles (for JWT claims)
CREATE TYPE user_role AS ENUM (
  'admin',                -- Platform admin (full access)
  'relationship_manager', -- RM (manage vendors in territory)
  'vendor',              -- Salon owner
  'customer'             -- End user
);

COMMENT ON TYPE booking_status IS 'Booking lifecycle states from creation to completion';
COMMENT ON TYPE payment_status IS 'Razorpay payment states (pending→success/failed→refunded)';
COMMENT ON TYPE payment_type IS 'Classification of payment types in the platform';
COMMENT ON TYPE request_status IS 'Vendor join request workflow states';
COMMENT ON TYPE user_role IS 'User role for authorization (stored in JWT claims)';
