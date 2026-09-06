-- =====================================================
-- Migration: Add FAQ entries to blog_posts
-- Purpose: Client-requested collapsible FAQ section at the bottom of an
--          article. Stored as structured data (not HTML) so it can be
--          validated, rendered as an accordion with no risk of injected
--          markup, and fed straight into a FAQPage JSON-LD block for SEO
--          rich snippets.
--
-- Shape: [{"question": "...", "answer": "..."}, ...] — order in the array is
-- display order. Sanitised and validated in app/services/blog_service.py /
-- app/schemas/request/blog.py; nothing here enforces shape beyond "is JSON".
-- =====================================================

ALTER TABLE blog_posts
    ADD COLUMN IF NOT EXISTS faqs JSONB NOT NULL DEFAULT '[]';
