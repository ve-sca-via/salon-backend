-- Salon-wide discount promotions (vendor "Run Promo")
CREATE TABLE IF NOT EXISTS salon_discount_promotions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    salon_id UUID NOT NULL REFERENCES salons(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    discount_type VARCHAR(20) NOT NULL CHECK (discount_type IN ('percentage', 'flat_amount')),
    discount_value NUMERIC(10,2) NOT NULL CHECK (discount_value > 0),
    min_booking_amount NUMERIC(10,2) CHECK (min_booking_amount IS NULL OR min_booking_amount >= 0),
    max_discount_limit NUMERIC(10,2) CHECK (max_discount_limit IS NULL OR max_discount_limit >= 0),
    start_date DATE NOT NULL,
    end_date DATE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    CONSTRAINT salon_promo_valid_date_range CHECK (end_date IS NULL OR end_date >= start_date),
    CONSTRAINT salon_promo_percentage_cap CHECK (
        discount_type != 'percentage' OR (discount_value > 0 AND discount_value <= 100)
    )
);

CREATE INDEX IF NOT EXISTS idx_salon_discount_promotions_salon_active
    ON salon_discount_promotions(salon_id, is_active, start_date, end_date);

ALTER TABLE salon_discount_promotions DISABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION update_salon_discount_promotions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_salon_discount_promotions_updated_at ON salon_discount_promotions;
CREATE TRIGGER trigger_update_salon_discount_promotions_updated_at
    BEFORE UPDATE ON salon_discount_promotions
    FOR EACH ROW
    EXECUTE FUNCTION update_salon_discount_promotions_updated_at();
