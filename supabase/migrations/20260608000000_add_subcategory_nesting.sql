-- =====================================================
-- Migration: Add a third taxonomy level via subcategory self-nesting
-- Purpose: Allow a subcategory to optionally nest under another subcategory,
--          giving a 3-level taxonomy:
--          Category (Hair) -> Subcategory (Haircut) -> Sub-subcategory (Spanish Haircut)
--
--          A node with parent_subcategory_id IS NULL is a level-2 subcategory
--          (directly under its parent_category). A node with parent_subcategory_id
--          set is a level-3 sub-subcategory. The priced services.subcategory_id
--          continues to point at the DEEPEST node the vendor selected; no change
--          to the services table is required.
-- =====================================================

-- 1. Self-referencing parent for nested subcategories (nullable = top-level subcategory).
--    ON DELETE CASCADE so deleting a subcategory removes its sub-subcategories too.
ALTER TABLE service_subcategories
    ADD COLUMN IF NOT EXISTS parent_subcategory_id UUID
    REFERENCES service_subcategories(id) ON DELETE CASCADE;

-- 2. Index for fast child lookups by parent subcategory.
CREATE INDEX IF NOT EXISTS idx_service_subcategories_parent_subcategory_id
    ON service_subcategories(parent_subcategory_id);

-- 3. A node cannot be its own parent (cheap guard; deeper cycle prevention is
--    enforced in application logic, which also caps depth at 3).
ALTER TABLE service_subcategories
    DROP CONSTRAINT IF EXISTS service_subcategories_no_self_parent;
ALTER TABLE service_subcategories
    ADD CONSTRAINT service_subcategories_no_self_parent
    CHECK (parent_subcategory_id IS NULL OR parent_subcategory_id <> id);

COMMENT ON COLUMN service_subcategories.parent_subcategory_id IS
    'Optional parent subcategory. NULL = level-2 (under parent_category_id); set = level-3 sub-subcategory.';
