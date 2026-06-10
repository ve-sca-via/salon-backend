-- Fix: update_salon_rating() recomputed average_rating but never updated total_reviews,
-- so salons showed "New (0 reviews)" on the client even when reviews existed.
-- This replaces the trigger function to also maintain total_reviews, and backfills
-- the counter for all existing salons.

CREATE OR REPLACE FUNCTION "public"."update_salon_rating"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  UPDATE salons
  SET
    average_rating = COALESCE((
      SELECT ROUND(AVG(rating)::numeric, 2)
      FROM reviews
      WHERE salon_id = COALESCE(NEW.salon_id, OLD.salon_id)
        AND deleted_at IS NULL
        AND is_hidden = false
    ), 0),
    total_reviews = (
      SELECT COUNT(*)
      FROM reviews
      WHERE salon_id = COALESCE(NEW.salon_id, OLD.salon_id)
        AND deleted_at IS NULL
        AND is_hidden = false
    ),
    updated_at = now()
  WHERE id = COALESCE(NEW.salon_id, OLD.salon_id);

  RETURN COALESCE(NEW, OLD);
END;
$$;

-- Backfill counters for existing salons whose reviews predate this fix.
UPDATE salons s
SET
  average_rating = COALESCE((
    SELECT ROUND(AVG(r.rating)::numeric, 2)
    FROM reviews r
    WHERE r.salon_id = s.id
      AND r.deleted_at IS NULL
      AND r.is_hidden = false
  ), 0),
  total_reviews = (
    SELECT COUNT(*)
    FROM reviews r
    WHERE r.salon_id = s.id
      AND r.deleted_at IS NULL
      AND r.is_hidden = false
  );
