-- Payment intents: our own record of what a Razorpay order was for.
--
-- Until now the authoritative snapshot of a cart payment (the pinned priced
-- breakdown and the cart contents) lived only in the Razorpay order's `notes`,
-- which meant:
--   * every cart checkout paid for an external `orders.fetch` round trip, inside
--     the request the customer waits on AFTER being charged (payment audit H-2);
--   * the snapshot was subject to Razorpay's notes limits (15 fields, 256 chars
--     per value) -- a cart of four or five services could silently truncate;
--   * nothing but the browser's success callback could turn a captured payment
--     into a booking, so a lost callback meant captured money and no booking,
--     with no record of it anywhere in our system (payment audit C-3).
--
-- Pinning the snapshot here fixes all three: checkout reads it in the same
-- round as its other queries, the values are unbounded jsonb, and the
-- `payment.captured` webhook can complete the booking with no browser involved.

CREATE TABLE IF NOT EXISTS public.payment_intents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- The Razorpay order this intent describes. Unique: one intent per order,
    -- and the lookup key for both checkout and the webhook.
    razorpay_order_id TEXT NOT NULL UNIQUE,

    -- What the money is for. Only cart checkout is stored here today; product
    -- orders and vendor registrations already have their own pre-payment rows.
    intent_type TEXT NOT NULL DEFAULT 'cart_checkout',

    customer_id UUID NOT NULL REFERENCES public.profiles(id),
    salon_id UUID REFERENCES public.salons(id),

    -- What we asked Razorpay to charge, in rupees.
    amount NUMERIC(10,2) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR',

    -- The authoritative pinned breakdown and cart contents (see
    -- PaymentService.create_cart_payment_order). jsonb, so no truncation.
    pricing JSONB NOT NULL,
    cart_snapshot JSONB NOT NULL,
    coupon_code TEXT,

    -- The appointment the customer had chosen when they paid. Needed only so
    -- the webhook can complete the booking without the browser; nullable
    -- because a client that does not send them still gets a working checkout
    -- (the browser callback carries them).
    booking_date DATE,
    time_slots JSONB,

    -- created -> completed (a booking exists) | failed (gateway reported
    -- payment.failed). `captured_at` is set when the webhook sees the money,
    -- which can happen before or after the booking is recorded.
    status TEXT NOT NULL DEFAULT 'created',
    razorpay_payment_id TEXT,
    booking_id UUID REFERENCES public.bookings(id),
    captured_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    failure_reason TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT payment_intents_valid_type CHECK (
        intent_type IN ('cart_checkout')
    ),
    CONSTRAINT payment_intents_valid_status CHECK (
        status IN ('created', 'completed', 'failed')
    ),
    CONSTRAINT payment_intents_time_slots_is_array CHECK (
        time_slots IS NULL OR jsonb_typeof(time_slots) = 'array'
    ),
    -- Mirrors bookings.time_slots_max_3, so an intent can never hold an
    -- appointment the bookings table would refuse.
    CONSTRAINT payment_intents_time_slots_max_3 CHECK (
        time_slots IS NULL OR jsonb_array_length(time_slots) <= 3
    )
);

-- The webhook and checkout both look an intent up by order id; the unique
-- constraint above already indexes that. These two serve reconciliation:
-- "captured but never completed" is the query that finds lost callbacks.
CREATE INDEX IF NOT EXISTS idx_payment_intents_status_created_at
    ON public.payment_intents(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_payment_intents_customer_id
    ON public.payment_intents(customer_id);
CREATE INDEX IF NOT EXISTS idx_payment_intents_payment_id
    ON public.payment_intents(razorpay_payment_id)
    WHERE razorpay_payment_id IS NOT NULL;

CREATE OR REPLACE FUNCTION update_payment_intents_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_payment_intents_updated_at ON public.payment_intents;
CREATE TRIGGER trigger_update_payment_intents_updated_at
    BEFORE UPDATE ON public.payment_intents
    FOR EACH ROW
    EXECUTE FUNCTION update_payment_intents_updated_at();

-- RLS on with no permissive policy: this table is written and read only by the
-- backend (service role, which bypasses RLS). Nothing in the client apps has
-- any business reading another customer's pinned prices, and no endpoint
-- exposes the table, so there is deliberately no policy to grant.
ALTER TABLE public.payment_intents ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.payment_intents IS
    'Pre-payment snapshot of a Razorpay cart order: pinned pricing, cart contents and chosen appointment. Read at checkout instead of fetching the Razorpay order, and used by the payment.captured webhook to complete a booking when the browser callback never arrives.';
COMMENT ON COLUMN public.payment_intents.pricing IS
    'Authoritative priced breakdown at order-create time. The booking records these exact amounts, so recorded == charged even if prices or coupons change in between.';
COMMENT ON COLUMN public.payment_intents.cart_snapshot IS
    'Cart contents (service_id, quantity, unit_price) at order-create time. Compared against the live cart at checkout to reject a cart modified after payment.';
COMMENT ON COLUMN public.payment_intents.status IS
    'created = order made, no booking yet. completed = a booking exists (booking_id set), whether the browser or the webhook got there first. failed = gateway reported payment.failed.';


-- =====================================================
-- Let a webhook-confirmed payment be recorded as success
-- =====================================================
-- `payment_online_requires_razorpay` demanded both razorpay_payment_id AND
-- razorpay_signature on a successful convenience_fee row. The browser callback
-- supplies both; a webhook supplies only the payment id, because its proof is an
-- HMAC over the webhook body rather than over the order|payment pair -- a
-- different signature with a different meaning, which does not belong in this
-- column.
--
-- The constraint's purpose is "never record an online platform fee as paid
-- without a gateway reference", and razorpay_payment_id alone satisfies that.
-- The signature was never read back after the in-process verification that
-- precedes the write (payment audit L-1), so requiring it bought nothing except
-- making webhook completion impossible.
ALTER TABLE public.payments
    DROP CONSTRAINT IF EXISTS payment_online_requires_razorpay;

ALTER TABLE public.payments
    ADD CONSTRAINT payment_online_requires_razorpay CHECK (
        payment_type::text <> 'convenience_fee'
        OR razorpay_payment_id IS NOT NULL
        OR status::text <> 'success'
    );

COMMENT ON CONSTRAINT payment_online_requires_razorpay ON public.payments IS
    'A successful convenience_fee payment must carry a Razorpay payment id. The signature is not required: a payment confirmed by the payment.captured webhook is proven by an HMAC over the webhook body, not by an order|payment signature.';
