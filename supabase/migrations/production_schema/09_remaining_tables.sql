-- ============================================================================
-- 09_REMAINING_TABLES.SQL - All Remaining Tables
-- ============================================================================
-- Cart, Favorites, Staff, RM System, Phone OTP, Token Blacklist

-- ============================================================================
-- CART SYSTEM
-- ============================================================================
CREATE TABLE cart_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  salon_id UUID NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
  service_id UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
  quantity INTEGER DEFAULT 1 CHECK (quantity > 0),
  metadata JSONB DEFAULT '{}'::jsonb, -- For any extra cart data
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  UNIQUE(user_id, service_id)
);

CREATE INDEX idx_cart_items_user_id ON cart_items(user_id);
CREATE INDEX idx_cart_items_salon_id ON cart_items(salon_id);
ALTER TABLE cart_items ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE cart_items IS 'Shopping cart items (normalized - no denormalization)';

-- ============================================================================
-- FAVORITES
-- ============================================================================
CREATE TABLE favorites (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  salon_id UUID NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  UNIQUE(user_id, salon_id)
);

CREATE INDEX idx_favorites_user_id ON favorites(user_id);
CREATE INDEX idx_favorites_salon_id ON favorites(salon_id);
CREATE INDEX idx_favorites_created_at ON favorites(created_at DESC);
ALTER TABLE favorites ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE favorites IS 'User favorite salons';

-- ============================================================================
-- SALON STAFF
-- ============================================================================
CREATE TABLE salon_staff (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  salon_id UUID NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
  user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  name VARCHAR(255) NOT NULL,
  phone VARCHAR(20),
  email VARCHAR(255),
  role VARCHAR(100), -- 'stylist', 'barber', 'manager', etc.
  specialization TEXT[],
  profile_image TEXT,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

CREATE INDEX idx_salon_staff_salon_id ON salon_staff(salon_id);
CREATE INDEX idx_salon_staff_user_id ON salon_staff(user_id) WHERE user_id IS NOT NULL;
ALTER TABLE salon_staff ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE salon_staff IS 'Staff members working at salons';

-- ============================================================================
-- STAFF AVAILABILITY
-- ============================================================================
CREATE TABLE staff_availability (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  staff_id UUID NOT NULL REFERENCES salon_staff(id) ON DELETE CASCADE,
  day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6), -- 0 = Sunday
  start_time TIME NOT NULL,
  end_time TIME NOT NULL,
  is_available BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  UNIQUE(staff_id, day_of_week)
);

CREATE INDEX idx_staff_availability_staff_id ON staff_availability(staff_id);
ALTER TABLE staff_availability ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE staff_availability IS 'Staff weekly availability schedule';

-- ============================================================================
-- RELATIONSHIP MANAGER SYSTEM
-- ============================================================================
CREATE TABLE rm_profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  full_name VARCHAR(255) NOT NULL,
  phone VARCHAR(20) NOT NULL,
  email VARCHAR(255) NOT NULL,
  assigned_territories TEXT[], -- ['Mumbai', 'Pune']
  performance_score INTEGER DEFAULT 0,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

CREATE INDEX idx_rm_profiles_active ON rm_profiles(is_active);
ALTER TABLE rm_profiles ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE rm_profiles IS 'Relationship Manager profiles for vendor management';

CREATE TABLE rm_score_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  rm_id UUID NOT NULL REFERENCES rm_profiles(id) ON DELETE CASCADE,
  action VARCHAR(100) NOT NULL,
  points INTEGER NOT NULL,
  description TEXT,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

CREATE INDEX idx_rm_score_history_rm_id ON rm_score_history(rm_id);
CREATE INDEX idx_rm_score_history_created_at ON rm_score_history(created_at DESC);
ALTER TABLE rm_score_history ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE rm_score_history IS 'RM performance score history and tracking';

-- ============================================================================
-- VENDOR JOIN REQUESTS
-- ============================================================================
CREATE TABLE vendor_join_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  business_name VARCHAR(255) NOT NULL,
  email VARCHAR(255) NOT NULL,
  phone VARCHAR(20) NOT NULL,
  city VARCHAR(100) NOT NULL,
  state VARCHAR(100) NOT NULL,
  pincode VARCHAR(6) NOT NULL,
  gst_number VARCHAR(15),
  status request_status DEFAULT 'pending' NOT NULL,
  submitted_at TIMESTAMPTZ DEFAULT now(),
  reviewed_at TIMESTAMPTZ,
  reviewed_by UUID REFERENCES auth.users(id),
  rejection_reason TEXT,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  
  CONSTRAINT valid_pincode_format CHECK (pincode ~ '^\d{6}$')
);

CREATE INDEX idx_vendor_join_requests_status ON vendor_join_requests(status);
CREATE INDEX idx_vendor_join_requests_user_id ON vendor_join_requests(user_id);

COMMENT ON TABLE vendor_join_requests IS 'Vendor onboarding requests awaiting approval';

-- ============================================================================
-- TOKEN BLACKLIST (Logout tracking)
-- ============================================================================
CREATE TABLE token_blacklist (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  token_jti VARCHAR(255) NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

CREATE INDEX idx_token_blacklist_user_id ON token_blacklist(user_id);
CREATE INDEX idx_token_blacklist_jti ON token_blacklist(token_jti);
CREATE INDEX idx_token_blacklist_expires ON token_blacklist(expires_at);
ALTER TABLE token_blacklist ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE token_blacklist IS 'Blacklisted JWT tokens (for logout tracking)';

-- ============================================================================
-- PHONE OTP VERIFICATION
-- ============================================================================
CREATE TABLE phone_verification_codes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone VARCHAR(20) NOT NULL,
  country_code VARCHAR(5) NOT NULL DEFAULT '+91',
  otp_code VARCHAR(6) NOT NULL,
  otp_hash VARCHAR(255) NOT NULL, -- Bcrypt hash for security
  purpose VARCHAR(50) NOT NULL CHECK (purpose IN ('signup', 'login', 'phone_verification', 'password_reset')),
  verified BOOLEAN DEFAULT false,
  verified_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ NOT NULL,
  attempts INTEGER DEFAULT 0,
  max_attempts INTEGER DEFAULT 3,
  ip_address INET,
  user_agent TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  
  CONSTRAINT otp_rate_limit CHECK (created_at > now() - interval '1 hour')
);

CREATE INDEX idx_phone_otp_phone ON phone_verification_codes(phone) WHERE verified = false;
CREATE INDEX idx_phone_otp_expires ON phone_verification_codes(expires_at) WHERE verified = false;
CREATE INDEX idx_phone_otp_created ON phone_verification_codes(created_at);

COMMENT ON TABLE phone_verification_codes IS 'OTP codes for phone verification. Rate-limited to prevent abuse (max 5/hour).';

-- ============================================================================
-- AUDIT LOGS
-- ============================================================================
CREATE TABLE audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  table_name VARCHAR(100) NOT NULL,
  record_id UUID NOT NULL,
  action VARCHAR(20) NOT NULL CHECK (action IN ('INSERT', 'UPDATE', 'DELETE', 'SOFT_DELETE')),
  old_data JSONB,
  new_data JSONB,
  changed_fields TEXT[],
  user_id UUID REFERENCES auth.users(id),
  ip_address INET,
  user_agent TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_audit_logs_table_record ON audit_logs(table_name, record_id);
CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at DESC);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);

COMMENT ON TABLE audit_logs IS 'Audit trail for all data modifications. Required for Indian IT Act 2000 and DPDP Act 2023 compliance.';

-- ============================================================================
-- SALON SUBSCRIPTIONS (Future use)
-- ============================================================================
CREATE TABLE salon_subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  salon_id UUID NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
  plan_name VARCHAR(100) NOT NULL,
  plan_type VARCHAR(50) NOT NULL DEFAULT 'monthly',
  status VARCHAR(50) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'expired', 'cancelled', 'suspended')),
  start_date TIMESTAMPTZ NOT NULL,
  end_date TIMESTAMPTZ NOT NULL,
  amount NUMERIC(10,2) NOT NULL CHECK (amount >= 0),
  payment_id UUID,
  auto_renew BOOLEAN DEFAULT true,
  cancelled_at TIMESTAMPTZ,
  cancellation_reason TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  created_by UUID REFERENCES auth.users(id),
  updated_by UUID REFERENCES auth.users(id),
  deleted_at TIMESTAMPTZ,
  deleted_by UUID REFERENCES auth.users(id)
);

CREATE INDEX idx_salon_subscriptions_salon_id ON salon_subscriptions(salon_id);
CREATE INDEX idx_salon_subscriptions_status ON salon_subscriptions(status);
CREATE INDEX idx_salon_subscriptions_end_date ON salon_subscriptions(end_date) WHERE status = 'active';

COMMENT ON TABLE salon_subscriptions IS 'Subscription plans for salons (future use - currently one-time registration only)';
