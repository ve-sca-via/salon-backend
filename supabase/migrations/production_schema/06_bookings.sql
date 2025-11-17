-- ============================================================================
-- 06_BOOKINGS.SQL - BOOKINGS TABLE
-- ============================================================================
-- Production-ready bookings with split payment tracking

CREATE TABLE bookings (
  -- Primary Key
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Booking Number (Human-readable)
  booking_number VARCHAR(50) NOT NULL UNIQUE,
  
  -- Relationships
  customer_id UUID NOT NULL REFERENCES profiles(id) ON DELETE RESTRICT,
  salon_id UUID NOT NULL REFERENCES salons(id) ON DELETE RESTRICT,
  service_id UUID NOT NULL REFERENCES services(id) ON DELETE RESTRICT,
  staff_id UUID REFERENCES salon_staff(id), -- Added via staff.sql migration
  
  -- Booking Details
  booking_date DATE NOT NULL,
  booking_time TIME NOT NULL,
  duration_minutes INTEGER NOT NULL CHECK (duration_minutes > 0),
  
  -- Payment Breakdown (Split Payment Model)
  service_price NUMERIC(10, 2) NOT NULL CHECK (service_price >= 0),
  convenience_fee NUMERIC(10, 2) NOT NULL DEFAULT 0 CHECK (convenience_fee >= 0),
  total_amount NUMERIC(10, 2) NOT NULL CHECK (total_amount >= 0),
  
  -- Payment Status Tracking
  convenience_fee_paid BOOLEAN DEFAULT false, -- Paid ONLINE via Razorpay
  service_paid BOOLEAN DEFAULT false,         -- Paid AT SALON (cash/card)
  payment_completed_at TIMESTAMPTZ,
  
  -- Booking Status
  status booking_status DEFAULT 'pending' NOT NULL,
  
  -- Cancellation
  cancelled_at TIMESTAMPTZ,
  cancelled_by UUID REFERENCES auth.users(id),
  cancellation_reason TEXT,
  
  -- Notes
  customer_notes TEXT,
  salon_notes TEXT,
  
  -- Audit Trail (Compliance)
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  created_by UUID REFERENCES auth.users(id),
  updated_by UUID REFERENCES auth.users(id),
  deleted_at TIMESTAMPTZ,
  deleted_by UUID REFERENCES auth.users(id),
  
  -- Constraints
  CONSTRAINT valid_booking_date 
    CHECK (booking_date >= CURRENT_DATE),
  
  CONSTRAINT bookings_total_amount_check 
    CHECK (total_amount = service_price + convenience_fee)
);

-- Generate booking number automatically
CREATE OR REPLACE FUNCTION generate_booking_number()
RETURNS TRIGGER AS $$
BEGIN
  NEW.booking_number := 'BKG' || TO_CHAR(now(), 'YYYYMMDD') || LPAD(nextval('booking_number_seq')::TEXT, 6, '0');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE SEQUENCE IF NOT EXISTS booking_number_seq;

CREATE TRIGGER set_booking_number
  BEFORE INSERT ON bookings
  FOR EACH ROW
  WHEN (NEW.booking_number IS NULL)
  EXECUTE FUNCTION generate_booking_number();

-- Performance Indexes
CREATE INDEX idx_bookings_customer_id ON bookings(customer_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_bookings_salon_id ON bookings(salon_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_bookings_service_id ON bookings(service_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_bookings_date_time_salon ON bookings(salon_id, booking_date, booking_time) WHERE deleted_at IS NULL;
CREATE INDEX idx_bookings_status ON bookings(status) WHERE deleted_at IS NULL;
CREATE INDEX idx_bookings_booking_date ON bookings(booking_date DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_bookings_deleted_at ON bookings(deleted_at);
CREATE INDEX idx_bookings_payment_status ON bookings(convenience_fee_paid, service_paid) WHERE deleted_at IS NULL;

-- Prevent double-booking same slot
CREATE UNIQUE INDEX idx_bookings_no_double_booking 
  ON bookings(salon_id, booking_date, booking_time) 
  WHERE status NOT IN ('cancelled') AND deleted_at IS NULL;

-- Enable RLS
ALTER TABLE bookings ENABLE ROW LEVEL SECURITY;

-- Updated timestamp trigger
CREATE TRIGGER set_updated_at
  BEFORE UPDATE ON bookings
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

-- Table comments
COMMENT ON TABLE bookings IS 'Customer bookings for salon services. Split payment: convenience_fee (online) + service_price (at salon)';
COMMENT ON COLUMN bookings.booking_number IS 'Human-readable booking reference (e.g., BKG20251115000001)';
COMMENT ON COLUMN bookings.convenience_fee IS 'Platform fee paid ONLINE during booking (via Razorpay)';
COMMENT ON COLUMN bookings.service_price IS 'Service cost paid AT SALON after completion (cash/card to vendor)';
COMMENT ON COLUMN bookings.total_amount IS 'Total cost: service_price + convenience_fee (enforced by constraint)';
COMMENT ON COLUMN bookings.convenience_fee_paid IS 'Whether customer paid online convenience fee';
COMMENT ON COLUMN bookings.service_paid IS 'Whether customer paid service amount at salon';
COMMENT ON COLUMN bookings.deleted_at IS 'Soft delete timestamp (NULL = active)';
