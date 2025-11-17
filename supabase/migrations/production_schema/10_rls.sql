--10_RLS_POLICIES.SQL - ROW LEVEL SECURITY POLICIES
-- ============================================================================
-- Production-ready RLS policies for all tables

-- ============================================================================
-- PROFILES
-- ============================================================================
-- Users can read all profiles
CREATE POLICY "Public profiles are viewable by everyone"
  ON profiles FOR SELECT
  USING (deleted_at IS NULL);

-- Users can insert their own profile
CREATE POLICY "Users can insert own profile"
  ON profiles FOR INSERT
  WITH CHECK (auth.uid() = id);

-- Users can update their own profile
CREATE POLICY "Users can update own profile"
  ON profiles FOR UPDATE
  USING (auth.uid() = id)
  WITH CHECK (auth.uid() = id);

-- Admins can manage all profiles
CREATE POLICY "Admins can manage all profiles"
  ON profiles FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE id = auth.uid() AND user_role = 'admin'
    )
  );

-- ============================================================================
-- SALONS
-- ============================================================================
-- Anyone can view active verified salons
CREATE POLICY "Active salons are viewable by everyone"
  ON salons FOR SELECT
  USING (is_verified = true AND is_active = true AND deleted_at IS NULL);

-- Vendors can insert their own salon
CREATE POLICY "Vendors can create salon"
  ON salons FOR INSERT
  WITH CHECK (
    vendor_id = auth.uid() AND
    EXISTS (
      SELECT 1 FROM profiles
      WHERE id = auth.uid() AND user_role = 'vendor'
    )
  );

-- Vendors can update their own salon
CREATE POLICY "Vendors can update own salon"
  ON salons FOR UPDATE
  USING (vendor_id = auth.uid())
  WITH CHECK (vendor_id = auth.uid());

-- Admins/RMs can manage all salons
CREATE POLICY "Admins and RMs can manage salons"
  ON salons FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE id = auth.uid() AND user_role IN ('admin', 'relationship_manager')
    )
  );

-- ============================================================================
-- SERVICE CATEGORIES
-- ============================================================================
-- Anyone can view active categories
CREATE POLICY "Active categories viewable by everyone"
  ON service_categories FOR SELECT
  USING (is_active = true);

-- Admins can manage categories
CREATE POLICY "Admins can manage categories"
  ON service_categories FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE id = auth.uid() AND user_role = 'admin'
    )
  );

-- ============================================================================
-- SERVICES
-- ============================================================================
-- Anyone can view active services
CREATE POLICY "Active services viewable by everyone"
  ON services FOR SELECT
  USING (is_active = true AND deleted_at IS NULL);

-- Vendors can manage their salon's services
CREATE POLICY "Vendors can manage own salon services"
  ON services FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM salons
      WHERE salons.id = services.salon_id
        AND salons.vendor_id = auth.uid()
    )
  );

-- Admins can manage all services
CREATE POLICY "Admins can manage all services"
  ON services FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE id = auth.uid() AND user_role = 'admin'
    )
  );

-- ============================================================================
-- BOOKINGS
-- ============================================================================
-- Customers can view their own bookings
CREATE POLICY "Customers can view own bookings"
  ON bookings FOR SELECT
  USING (
    customer_id = auth.uid() AND deleted_at IS NULL
  );

-- Vendors can view their salon's bookings
CREATE POLICY "Vendors can view salon bookings"
  ON bookings FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM salons
      WHERE salons.id = bookings.salon_id
        AND salons.vendor_id = auth.uid()
    ) AND deleted_at IS NULL
  );

-- Customers can create bookings
CREATE POLICY "Customers can create bookings"
  ON bookings FOR INSERT
  WITH CHECK (
    customer_id = auth.uid() AND
    EXISTS (
      SELECT 1 FROM profiles
      WHERE id = auth.uid() AND user_role = 'customer'
    )
  );

-- Customers can update their own bookings (before confirmation)
CREATE POLICY "Customers can update own bookings"
  ON bookings FOR UPDATE
  USING (customer_id = auth.uid() AND status = 'pending')
  WITH CHECK (customer_id = auth.uid());

-- Vendors can update their salon's bookings
CREATE POLICY "Vendors can update salon bookings"
  ON bookings FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM salons
      WHERE salons.id = bookings.salon_id
        AND salons.vendor_id = auth.uid()
    )
  );

-- Admins can manage all bookings
CREATE POLICY "Admins can manage all bookings"
  ON bookings FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE id = auth.uid() AND user_role = 'admin'
    )
  );

-- ============================================================================
-- BOOKING PAYMENTS
-- ============================================================================
-- Customers can view their own payments
CREATE POLICY "Customers can view own payments"
  ON booking_payments FOR SELECT
  USING (customer_id = auth.uid() AND deleted_at IS NULL);

-- Vendors can view their salon's payments
CREATE POLICY "Vendors can view salon payments"
  ON booking_payments FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM bookings
      JOIN salons ON salons.id = bookings.salon_id
      WHERE bookings.id = booking_payments.booking_id
        AND salons.vendor_id = auth.uid()
    ) AND deleted_at IS NULL
  );

-- System can create payments
CREATE POLICY "System can create payments"
  ON booking_payments FOR INSERT
  WITH CHECK (true); -- Backend controls this via service role

-- System can update payments
CREATE POLICY "System can update payments"
  ON booking_payments FOR UPDATE
  USING (true); -- Backend controls this via service role

-- Admins can manage all payments
CREATE POLICY "Admins can manage all payments"
  ON booking_payments FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE id = auth.uid() AND user_role = 'admin'
    )
  );

-- ============================================================================
-- VENDOR REGISTRATION PAYMENTS
-- ============================================================================
-- Vendors can view their own registration payments
CREATE POLICY "Vendors can view own registration payments"
  ON vendor_registration_payments FOR SELECT
  USING (vendor_id = auth.uid());

-- System can create registration payments
CREATE POLICY "System can create registration payments"
  ON vendor_registration_payments FOR INSERT
  WITH CHECK (true); -- Backend controls this

-- System can update registration payments
CREATE POLICY "System can update registration payments"
  ON vendor_registration_payments FOR UPDATE
  USING (true); -- Backend controls this

-- Admins can manage all registration payments
CREATE POLICY "Admins can manage registration payments"
  ON vendor_registration_payments FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE id = auth.uid() AND user_role = 'admin'
    )
  );

-- ============================================================================
-- REVIEWS
-- ============================================================================
-- Anyone can view non-hidden reviews
CREATE POLICY "Public can view reviews"
  ON reviews FOR SELECT
  USING (is_hidden = false AND deleted_at IS NULL);

-- Customers can create reviews for their completed bookings
CREATE POLICY "Customers can create reviews"
  ON reviews FOR INSERT
  WITH CHECK (
    customer_id = auth.uid() AND
    EXISTS (
      SELECT 1 FROM bookings
      WHERE bookings.id = reviews.booking_id
        AND bookings.customer_id = auth.uid()
        AND bookings.status = 'completed'
    )
  );

-- Customers can update their own reviews
CREATE POLICY "Customers can update own reviews"
  ON reviews FOR UPDATE
  USING (customer_id = auth.uid())
  WITH CHECK (customer_id = auth.uid());

-- Vendors can respond to their salon's reviews
CREATE POLICY "Vendors can respond to reviews"
  ON reviews FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM salons
      WHERE salons.id = reviews.salon_id
        AND salons.vendor_id = auth.uid()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM salons
      WHERE salons.id = reviews.salon_id
        AND salons.vendor_id = auth.uid()
    )
  );

-- Admins can manage all reviews
CREATE POLICY "Admins can manage all reviews"
  ON reviews FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE id = auth.uid() AND user_role = 'admin'
    )
  );

-- ============================================================================
-- CART ITEMS
-- ============================================================================
CREATE POLICY "Users can manage own cart"
  ON cart_items FOR ALL
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- ============================================================================
-- FAVORITES
-- ============================================================================
CREATE POLICY "Users can manage own favorites"
  ON favorites FOR ALL
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- ============================================================================
-- SALON STAFF
-- ============================================================================
-- Anyone can view active staff
CREATE POLICY "Active staff viewable by everyone"
  ON salon_staff FOR SELECT
  USING (is_active = true);

-- Vendors can manage their salon's staff
CREATE POLICY "Vendors can manage salon staff"
  ON salon_staff FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM salons
      WHERE salons.id = salon_staff.salon_id
        AND salons.vendor_id = auth.uid()
    )
  );

-- Admins can manage all staff
CREATE POLICY "Admins can manage all staff"
  ON salon_staff FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE id = auth.uid() AND user_role = 'admin'
    )
  );

-- ============================================================================
-- STAFF AVAILABILITY
-- ============================================================================
-- Anyone can view staff availability
CREATE POLICY "Staff availability viewable by everyone"
  ON staff_availability FOR SELECT
  USING (is_available = true);

-- Vendors can manage their staff's availability
CREATE POLICY "Vendors can manage staff availability"
  ON staff_availability FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM salon_staff
      JOIN salons ON salons.id = salon_staff.salon_id
      WHERE salon_staff.id = staff_availability.staff_id
        AND salons.vendor_id = auth.uid()
    )
  );

-- ============================================================================
-- RM PROFILES
-- ============================================================================
-- Admins can view all RMs
CREATE POLICY "Admins can view RMs"
  ON rm_profiles FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE id = auth.uid() AND user_role IN ('admin', 'relationship_manager')
    )
  );

-- Admins can manage RMs
CREATE POLICY "Admins can manage RMs"
  ON rm_profiles FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE id = auth.uid() AND user_role = 'admin'
    )
  );

-- ============================================================================
-- RM SCORE HISTORY
-- ============================================================================
-- RMs can view their own score history
CREATE POLICY "RMs can view own score history"
  ON rm_score_history FOR SELECT
  USING (rm_id = auth.uid());

-- Admins can view all score history
CREATE POLICY "Admins can view all score history"
  ON rm_score_history FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE id = auth.uid() AND user_role = 'admin'
    )
  );

-- System can insert score history
CREATE POLICY "System can insert score history"
  ON rm_score_history FOR INSERT
  WITH CHECK (true); -- Backend controls this

-- ============================================================================
-- VENDOR JOIN REQUESTS
-- ============================================================================
-- Users can view their own requests
CREATE POLICY "Users can view own join requests"
  ON vendor_join_requests FOR SELECT
  USING (user_id = auth.uid());

-- Users can create join requests
CREATE POLICY "Users can create join requests"
  ON vendor_join_requests FOR INSERT
  WITH CHECK (user_id = auth.uid());

-- Admins and RMs can view all requests
CREATE POLICY "Admins and RMs can view join requests"
  ON vendor_join_requests FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE id = auth.uid() AND user_role IN ('admin', 'relationship_manager')
    )
  );

-- Admins and RMs can update requests
CREATE POLICY "Admins and RMs can update join requests"
  ON vendor_join_requests FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE id = auth.uid() AND user_role IN ('admin', 'relationship_manager')
    )
  );

-- ============================================================================
-- TOKEN BLACKLIST
-- ============================================================================
-- Users can view their own blacklisted tokens
CREATE POLICY "Users can view own blacklisted tokens"
  ON token_blacklist FOR SELECT
  USING (user_id = auth.uid());

-- System can insert tokens
CREATE POLICY "System can insert blacklisted tokens"
  ON token_blacklist FOR INSERT
  WITH CHECK (true); -- Backend controls this

-- ============================================================================
-- PHONE VERIFICATION CODES
-- ============================================================================
-- No direct access - backend only via service role
-- Users verify via API endpoints only

-- ============================================================================
-- AUDIT LOGS
-- ============================================================================
-- Admins can view audit logs
CREATE POLICY "Admins can view audit logs"
  ON audit_logs FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE id = auth.uid() AND user_role = 'admin'
    )
  );

-- System can insert audit logs
CREATE POLICY "System can insert audit logs"
  ON audit_logs FOR INSERT
  WITH CHECK (true); -- Backend controls this

-- ============================================================================
-- SALON SUBSCRIPTIONS
-- ============================================================================
-- Vendors can view their own subscriptions
CREATE POLICY "Vendors can view own subscriptions"
  ON salon_subscriptions FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM salons
      WHERE salons.id = salon_subscriptions.salon_id
        AND salons.vendor_id = auth.uid()
    )
  );

-- Admins can manage all subscriptions
CREATE POLICY "Admins can manage subscriptions"
  ON salon_subscriptions FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE id = auth.uid() AND user_role = 'admin'
    )
  );