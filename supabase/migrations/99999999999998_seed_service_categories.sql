-- ============================================================================
-- SEED SERVICE CATEGORIES
-- ============================================================================
-- Insert common salon service categories

INSERT INTO service_categories (name, description, icon_url, display_order, is_active) VALUES
  ('Hair Care', 'Haircuts, styling, coloring, and treatments', NULL, 1, true),
  ('Skin & Spa', 'Facials, skin treatments, and spa therapies', NULL, 2, true),
  ('Nail Care', 'Manicures, pedicures, and nail art', NULL, 3, true),
  ('Makeup', 'Bridal, party, and professional makeup services', NULL, 4, true),
  ('Hair Removal', 'Waxing, threading, and laser hair removal', NULL, 5, true),
  ('Massage', 'Body massage and relaxation therapies', NULL, 6, true),
  ('Beard & Grooming', 'Beard trimming, shaving, and men''s grooming', NULL, 7, true),
  ('Bridal Services', 'Complete bridal packages and pre-wedding treatments', NULL, 8, true),
  ('Body Treatments', 'Body scrubs, wraps, and polishing', NULL, 9, true),
  ('Eyebrow & Lashes', 'Eyebrow shaping, tinting, and lash extensions', NULL, 10, true)
ON CONFLICT (name) DO NOTHING;
