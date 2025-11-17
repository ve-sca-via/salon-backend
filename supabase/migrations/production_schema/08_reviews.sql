-- ============================================================================
-- 08_REVIEWS.SQL - REVIEWS & RATINGS TABLE
-- ============================================================================
-- Production-ready review system with moderation

CREATE TABLE reviews (
  -- Primary Key
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Relationships
  salon_id UUID NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
  customer_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  booking_id UUID REFERENCES bookings(id) ON DELETE SET NULL,
  
  -- Review Content
  rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
  title VARCHAR(255),
  review_text TEXT,
  
  -- Images
  images TEXT[] DEFAULT ARRAY[]::TEXT[],
  
  -- Moderation
  is_visible BOOLEAN DEFAULT true,
  is_verified_purchase BOOLEAN DEFAULT false, -- Based on booking_id
  flagged_inappropriate BOOLEAN DEFAULT false,
  moderated_at TIMESTAMPTZ,
  moderated_by UUID REFERENCES auth.users(id),
  moderation_notes TEXT,
  
  -- Salon Response
  salon_response TEXT,
  responded_at TIMESTAMPTZ,
  
  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

-- Prevent duplicate reviews per booking
CREATE UNIQUE INDEX idx_reviews_one_per_booking 
  ON reviews(booking_id) 
  WHERE booking_id IS NOT NULL;

-- Performance Indexes
CREATE INDEX idx_reviews_salon_id ON reviews(salon_id);
CREATE INDEX idx_reviews_customer_id ON reviews(customer_id);
CREATE INDEX idx_reviews_visible_salon ON reviews(salon_id, is_visible) WHERE is_visible = true;
CREATE INDEX idx_reviews_rating ON reviews(rating);
CREATE INDEX idx_reviews_created_at ON reviews(created_at DESC);

-- Enable RLS
ALTER TABLE reviews ENABLE ROW LEVEL SECURITY;

-- Auto-update salon rating when review changes
CREATE OR REPLACE FUNCTION update_salon_rating()
RETURNS TRIGGER AS $$
DECLARE
  new_avg DECIMAL(3, 2);
  new_count INTEGER;
BEGIN
  SELECT 
    COALESCE(AVG(rating), 0)::DECIMAL(3, 2),
    COUNT(*)
  INTO new_avg, new_count
  FROM reviews
  WHERE salon_id = COALESCE(NEW.salon_id, OLD.salon_id)
    AND is_visible = true;
  
  UPDATE salons
  SET 
    average_rating = new_avg,
    total_reviews = new_count
  WHERE id = COALESCE(NEW.salon_id, OLD.salon_id);
  
  RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_salon_rating_trigger
  AFTER INSERT OR UPDATE OR DELETE ON reviews
  FOR EACH ROW
  EXECUTE FUNCTION update_salon_rating();

-- Table comments
COMMENT ON TABLE reviews IS 'Customer reviews and ratings for salons. Auto-updates salon average_rating.';
COMMENT ON COLUMN reviews.is_verified_purchase IS 'Whether review is from a confirmed booking (more trustworthy)';
COMMENT ON COLUMN reviews.is_visible IS 'Whether review is visible to public (for moderation)';
