-- ============================================================================
-- 07_PAYMENTS.SQL - PAYMENT TABLES (Razorpay Integration)
-- ============================================================================
-- Production-ready payment tracking with PCI-DSS compliance

-- Booking Payments (Online convenience fee payments)
CREATE TABLE booking_payments (
  -- Primary Key
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Relationships
  booking_id UUID NOT NULL REFERENCES bookings(id) ON DELETE RESTRICT,
  customer_id UUID NOT NULL REFERENCES profiles(id) ON DELETE RESTRICT,
  
  -- Razorpay Integration
  razorpay_order_id VARCHAR(100) UNIQUE,
  razorpay_payment_id VARCHAR(100) UNIQUE,
  razorpay_signature VARCHAR(255),
  
  -- Payment Details
  amount NUMERIC(10, 2) NOT NULL CHECK (amount >= 0),
  convenience_fee NUMERIC(10, 2) NOT NULL CHECK (convenience_fee >= 0),
  service_amount NUMERIC(10, 2) NOT NULL CHECK (service_amount >= 0), -- For reference
  currency VARCHAR(3) DEFAULT 'INR' NOT NULL,
  
  -- Payment Status
  status payment_status DEFAULT 'pending' NOT NULL,
  payment_method VARCHAR(50), -- 'card', 'upi', 'netbanking', 'wallet'
  
  -- Timestamps
  paid_at TIMESTAMPTZ,
  failed_at TIMESTAMPTZ,
  refunded_at TIMESTAMPTZ,
  
  -- Metadata
  payment_metadata JSONB DEFAULT '{}'::jsonb,
  error_code VARCHAR(100),
  error_description TEXT,
  
  -- Audit Trail (Compliance)
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  created_by UUID REFERENCES auth.users(id),
  updated_by UUID REFERENCES auth.users(id),
  deleted_at TIMESTAMPTZ,
  deleted_by UUID REFERENCES auth.users(id),
  
  -- Constraints
  CONSTRAINT payment_completion_requires_id 
    CHECK (
      (status != 'success') OR 
      (razorpay_payment_id IS NOT NULL AND razorpay_signature IS NOT NULL)
    )
);

-- Vendor Registration Payments (One-time platform registration)
CREATE TABLE vendor_registration_payments (
  -- Primary Key
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Relationships
  vendor_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
  salon_id UUID REFERENCES salons(id) ON DELETE SET NULL,
  
  -- Razorpay Integration
  razorpay_order_id VARCHAR(100) UNIQUE,
  razorpay_payment_id VARCHAR(100) UNIQUE,
  razorpay_signature VARCHAR(255),
  
  -- Payment Details
  amount NUMERIC(10, 2) NOT NULL CHECK (amount >= 0),
  currency VARCHAR(3) DEFAULT 'INR' NOT NULL,
  
  -- Payment Status
  status payment_status DEFAULT 'pending' NOT NULL,
  payment_method VARCHAR(50),
  
  -- Timestamps
  paid_at TIMESTAMPTZ,
  failed_at TIMESTAMPTZ,
  refunded_at TIMESTAMPTZ,
  
  -- Metadata
  payment_metadata JSONB DEFAULT '{}'::jsonb,
  error_code VARCHAR(100),
  error_description TEXT,
  
  -- Audit Trail (Compliance)
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  created_by UUID REFERENCES auth.users(id),
  updated_by UUID REFERENCES auth.users(id),
  deleted_at TIMESTAMPTZ,
  deleted_by UUID REFERENCES auth.users(id)
);

-- Performance Indexes
CREATE INDEX idx_booking_payments_booking_id ON booking_payments(booking_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_booking_payments_customer_id ON booking_payments(customer_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_booking_payments_razorpay_order ON booking_payments(razorpay_order_id) WHERE razorpay_order_id IS NOT NULL;
CREATE INDEX idx_booking_payments_razorpay_payment ON booking_payments(razorpay_payment_id) WHERE razorpay_payment_id IS NOT NULL;
CREATE INDEX idx_booking_payments_status ON booking_payments(status) WHERE deleted_at IS NULL;
CREATE INDEX idx_booking_payments_paid_at ON booking_payments(paid_at) WHERE status = 'success';
CREATE INDEX idx_booking_payments_deleted_at ON booking_payments(deleted_at);

CREATE INDEX idx_vendor_reg_payments_vendor_id ON vendor_registration_payments(vendor_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_vendor_reg_payments_salon_id ON vendor_registration_payments(salon_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_vendor_reg_payments_razorpay_order ON vendor_registration_payments(razorpay_order_id) WHERE razorpay_order_id IS NOT NULL;
CREATE INDEX idx_vendor_reg_payments_razorpay_payment ON vendor_registration_payments(razorpay_payment_id) WHERE razorpay_payment_id IS NOT NULL;
CREATE INDEX idx_vendor_reg_payments_status ON vendor_registration_payments(status) WHERE deleted_at IS NULL;
CREATE INDEX idx_vendor_reg_payments_paid_at ON vendor_registration_payments(paid_at) WHERE status = 'success';
CREATE INDEX idx_vendor_reg_payments_deleted_at ON vendor_registration_payments(deleted_at);

-- Enable RLS
ALTER TABLE booking_payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE vendor_registration_payments ENABLE ROW LEVEL SECURITY;

-- Updated timestamp triggers
CREATE TRIGGER set_updated_at
  BEFORE UPDATE ON booking_payments
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER set_updated_at
  BEFORE UPDATE ON vendor_registration_payments
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

-- Add FK to salons table (circular reference)
ALTER TABLE salons
  ADD CONSTRAINT salons_registration_payment_fkey
  FOREIGN KEY (registration_payment_id) 
  REFERENCES vendor_registration_payments(id) 
  ON DELETE SET NULL;

-- Table comments
COMMENT ON TABLE booking_payments IS 'Online payment records for booking convenience fees via Razorpay. Does NOT include service payments (paid at salon).';
COMMENT ON TABLE vendor_registration_payments IS 'One-time registration fee payments from vendors joining the platform';
COMMENT ON COLUMN booking_payments.amount IS 'Amount charged online via Razorpay (typically equals convenience_fee)';
COMMENT ON COLUMN booking_payments.service_amount IS 'Service cost customer will pay at salon (for reference only, not charged online)';
COMMENT ON COLUMN booking_payments.convenience_fee IS 'Platform fee charged for this booking (goes to platform)';
COMMENT ON COLUMN booking_payments.razorpay_payment_id IS 'Razorpay payment ID after successful payment (immutable)';
COMMENT ON COLUMN booking_payments.razorpay_signature IS 'Razorpay signature for payment verification (immutable)';
COMMENT ON COLUMN booking_payments.deleted_at IS 'Soft delete timestamp (NULL = active)';
