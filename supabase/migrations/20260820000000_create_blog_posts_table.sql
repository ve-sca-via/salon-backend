-- =====================================================
-- Migration: Create Blog Posts Table
-- Purpose: Admin-managed blog for SEO. Marketing authors keyword-targeted
--          articles in the admin panel; the public site server-renders them
--          at /blog and /blog/:slug so crawlers receive real HTML.
--
-- SCHEDULING NOTE: there is no separate 'scheduled' status. A post is
--   scheduled by setting status='published' with a future published_at.
--   Every public read filters `status='published' AND published_at <= now()`,
--   so a post goes live on its own with no cron job flipping states.
--   The admin UI derives the "Scheduled" label from that same condition.
-- =====================================================

CREATE TABLE IF NOT EXISTS blog_posts (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identity / routing
    slug              TEXT NOT NULL UNIQUE,             -- URL segment: /blog/{slug}
    title             TEXT NOT NULL,
    excerpt           TEXT,                             -- Listing-card summary

    -- Body (sanitised HTML produced by the admin TipTap editor)
    content           TEXT NOT NULL DEFAULT '',

    -- Cover image (Cloudinary, same delivery path as banners/products)
    cover_image_url   TEXT,
    cover_image_alt   TEXT,                             -- Required by the API when a cover is set

    -- SEO fields: explicit values the author controls, NOT derived from the body
    meta_title        TEXT,                             -- Falls back to title
    meta_description  TEXT,                             -- Falls back to excerpt
    focus_keyword     TEXT,                             -- The term this article targets

    -- Taxonomy & attribution
    tags              TEXT[] NOT NULL DEFAULT '{}',
    author_name       TEXT,                             -- Display byline only

    -- Publication state
    status            TEXT NOT NULL DEFAULT 'draft'
                          CHECK (status IN ('draft', 'published', 'archived')),
    published_at      TIMESTAMPTZ,                      -- Future value = scheduled

    -- Derived
    reading_minutes   INTEGER NOT NULL DEFAULT 1,       -- Computed on write from the body text

    -- Audit
    created_by        UUID REFERENCES profiles(id) ON DELETE SET NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Public listing: status + published_at is the hot path for every reader query.
CREATE INDEX IF NOT EXISTS idx_blog_posts_status_published_at
    ON blog_posts(status, published_at DESC);

-- Single-post lookup by slug (UNIQUE already indexes this, kept explicit for clarity
-- of the query plan on the public detail route).
CREATE INDEX IF NOT EXISTS idx_blog_posts_slug ON blog_posts(slug);

-- Tag filtering on the blog index page.
CREATE INDEX IF NOT EXISTS idx_blog_posts_tags ON blog_posts USING GIN(tags);

-- Admin listing default order.
CREATE INDEX IF NOT EXISTS idx_blog_posts_created_at ON blog_posts(created_at DESC);

-- Auto-update updated_at on row modification (same pattern as banners/products).
CREATE OR REPLACE FUNCTION update_blog_posts_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_blog_posts_updated_at ON blog_posts;
CREATE TRIGGER trigger_blog_posts_updated_at
    BEFORE UPDATE ON blog_posts
    FOR EACH ROW
    EXECUTE FUNCTION update_blog_posts_updated_at();

-- RLS enabled with a service-role full-access policy (service_role architecture,
-- same as banners/products — the backend uses the service_role key and enforces
-- the published/draft split in BlogService, not in RLS).
ALTER TABLE blog_posts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role has full access to blog_posts"
    ON blog_posts
    FOR ALL
    USING (true)
    WITH CHECK (true);
