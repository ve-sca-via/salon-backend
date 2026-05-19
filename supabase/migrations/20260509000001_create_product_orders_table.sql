-- product_orders
CREATE TABLE product_orders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id),
    order_number    TEXT UNIQUE NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending', -- pending, paid, shipped, delivered, cancelled
    subtotal        NUMERIC(10,2) NOT NULL,
    discount_total  NUMERIC(10,2) DEFAULT 0,
    total_amount    NUMERIC(10,2) NOT NULL,
    shipping_address JSONB,
    razorpay_order_id TEXT,
    razorpay_payment_id TEXT,
    payment_status  TEXT DEFAULT 'pending',
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- product_order_items
CREATE TABLE product_order_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id        UUID NOT NULL REFERENCES product_orders(id) ON DELETE CASCADE,
    product_id      UUID NOT NULL REFERENCES products(id),
    product_name    TEXT NOT NULL,         -- snapshot at purchase time
    quantity        INTEGER NOT NULL DEFAULT 1,
    unit_price      NUMERIC(10,2) NOT NULL,
    total_price     NUMERIC(10,2) NOT NULL,
    image_url       TEXT
);

-- RLS policies for product_orders
ALTER TABLE product_orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own orders"
    ON product_orders FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own orders"
    ON product_orders FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own orders"
    ON product_orders FOR UPDATE
    USING (auth.uid() = user_id);

-- RLS policies for product_order_items
ALTER TABLE product_order_items ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own order items"
    ON product_order_items FOR SELECT
    USING (EXISTS (
        SELECT 1 FROM product_orders
        WHERE product_orders.id = product_order_items.order_id
        AND product_orders.user_id = auth.uid()
    ));

CREATE POLICY "Users can insert their own order items"
    ON product_order_items FOR INSERT
    WITH CHECK (EXISTS (
        SELECT 1 FROM product_orders
        WHERE product_orders.id = product_order_items.order_id
        AND product_orders.user_id = auth.uid()
    ));
