"""
Blog Service - Business Logic Layer
Handles CRUD, slug management, HTML sanitisation and publication state for the
admin-managed SEO blog.

Follows the same service-layer pattern as BannerService/ProductService: a thin
class wrapping a Supabase client, raising HTTPException for API-facing errors.

SCHEDULING: there is no 'scheduled' status. A post is scheduled by publishing it
with a future `published_at`; every public read filters on
`status='published' AND published_at <= now()`, so posts go live on their own
without a cron job. See the table migration for the same note.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import nh3
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# Average adult reading speed, used for the "N min read" label on cards.
WORDS_PER_MINUTE = 200

# Columns returned for list views. `content` is deliberately excluded — article
# bodies are large and the index page never renders them.
LIST_COLUMNS = (
    "id,slug,title,excerpt,cover_image_url,cover_image_alt,focus_keyword,tags,"
    "author_name,status,published_at,reading_minutes,created_at,updated_at"
)

# Tags the editor can produce. Anything else is stripped on save — the stored
# HTML is injected directly into a server-rendered page, so the API must not
# trust the editor to have restricted its own output.
# `span` and `div` are deliberately absent. The editor cannot produce either;
# they only ever arrive from a Google Docs / Word paste, where they exist to
# carry a `style` attribute this allowlist strips anyway. nh3 keeps the text of
# a disallowed tag, so leaving them out simply unwraps them.
ALLOWED_TAGS = {
    "p", "br", "hr",
    "h2", "h3", "h4",
    "strong", "em", "b", "i", "u", "s", "code", "pre", "blockquote",
    "ul", "ol", "li",
    "a", "img", "figure", "figcaption",
    "table", "thead", "tbody", "tr", "th", "td",
}

# `class` is not allow-listed on anything: prose.css styles article content by
# element only, so a pasted class is dead weight at best and a way to reach into
# the host page's stylesheet at worst.
ALLOWED_ATTRIBUTES = {
    # `rel` is deliberately absent: nh3 sets it itself from `link_rel` below and
    # panics if the attribute is also allow-listed here.
    "a": {"href", "title", "target"},
    "img": {"src", "alt", "title", "width", "height", "loading"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
}


def _generate_slug(title: str) -> str:
    """
    Generate a URL-friendly slug from a post title.

    Mirrors ProductService._generate_slug so blog and product URLs read the same.
    e.g. "Best Hair Spa in Delhi (2026)" -> "best-hair-spa-in-delhi-2026"
    """
    slug = (title or "").lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)   # Drop punctuation, keep spaces/hyphens
    slug = re.sub(r"[\s_]+", "-", slug)    # Spaces/underscores -> hyphens
    slug = re.sub(r"-+", "-", slug)        # Collapse repeats
    slug = slug.strip("-")
    return slug or "post"


def _unwrap_redundant_heading_bold(match: "re.Match[str]") -> str:
    """
    Drop a <strong>/<b> that wraps a heading's entire text.

    prose.css already gives headings their weight, so the wrapper only makes one
    heading render heavier than the next one — which reads to the author as the
    font changing by itself. Left alone when the heading mixes bold with
    unbolded text, because that is a deliberate emphasis.
    """
    tag, inner = match.group(1), match.group(2)
    wrapper = re.fullmatch(r"\s*<(strong|b)>(.*)</\1>\s*", inner, re.S)
    if not wrapper:
        return match.group(0)
    body = wrapper.group(2)
    if re.search(r"</?(strong|b)\b", body):   # more than one bold run — leave it
        return match.group(0)
    return f"<{tag}>{body}</{tag}>"


def _normalize_structure(html: str) -> str:
    """
    Tidy the structural debris a paste leaves behind, after nh3 has run.

    These are the rewrites that are true regardless of what the author meant:
    a heading does not end in a line break, a heading does not need to be bolted
    into <strong>, and an empty paragraph is not content. Judgement calls that
    depend on intent — is this h3 really a paragraph? — are made at paste time in
    the editor (`salon-admin-panel/src/utils/pastedHtml.js`) where the author can
    see and undo the result, not silently on save.
    """
    # Trailing <br> before a heading closes — pure paste noise.
    html = re.sub(r"(?:<br\s*/?>\s*)+(</h[234]>)", r"\1", html)

    # Headings do not need to be wrapped in bold to look like headings.
    html = re.sub(r"<(h[234])>(.*?)</\1>", _unwrap_redundant_heading_bold, html, flags=re.S)

    # <p></p> / <p><br></p> left over from pressing Enter at the end.
    html = re.sub(r"<p>(?:\s|&nbsp;|<br\s*/?>)*</p>", "", html)

    return html.strip()


def _sanitize_html(html: Optional[str]) -> str:
    """
    Strip everything outside the editor's allowlist from an article body.

    nh3 removes disallowed tags/attributes and neutralises javascript: URLs, so
    a compromised admin account (or a paste from an untrusted source) cannot
    inject script into the server-rendered public page.

    The structural pass afterwards is presentation, not security: it keeps a
    pasted article from rendering in a different face every other block.
    """
    if not html:
        return ""
    cleaned = nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        link_rel="noopener noreferrer",
    )
    return _normalize_structure(cleaned)


def _strip_html(html: Optional[str]) -> str:
    """Plain text from an HTML body, for word counts and excerpt fallbacks."""
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def _reading_minutes(html: Optional[str]) -> int:
    """Estimated read time in whole minutes, floored at 1."""
    words = len(_strip_html(html).split())
    return max(1, round(words / WORDS_PER_MINUTE)) if words else 1


def _sanitize_search(term: str) -> str:
    """
    Strip characters that break PostgREST's `or=` filter grammar.

    Commas separate conditions and parentheses delimit the group, so a search
    for "spa, salon" would otherwise be parsed as two malformed conditions.
    `*` is ilike's wildcard in the URL form and is stripped so a caller cannot
    inject one into the pattern.

    Whitespace is collapsed afterwards: stripping punctuation out of
    "hair, spa" would otherwise leave a double space that matches nothing.

    Matching is plain substring ILIKE on the whole cleaned phrase, so
    "hair spa" finds "Best Hair Spa in Delhi" but "hair delhi" does not. That
    is adequate at blog scale; swap in postgrest's `plfts` if the archive grows
    enough to need real full-text ranking.
    """
    cleaned = re.sub(r"[,()*\\]", " ", term)
    return re.sub(r"\s+", " ", cleaned).strip()


class BlogService:
    """Service class for blog post operations."""

    def __init__(self, db_client):
        self.db = db_client

    # =====================================================
    # READ
    # =====================================================

    async def list_posts(
        self,
        tag: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 12,
        offset: int = 0,
        include_unpublished: bool = False,
        status_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List blog posts, newest published first.

        Public callers get only posts that are published AND whose publish date
        has passed. Admin callers (include_unpublished=True) get everything,
        newest-created first, optionally narrowed to a single status.
        """
        try:
            query = self.db.table("blog_posts").select(LIST_COLUMNS, count="exact")

            if include_unpublished:
                if status_filter:
                    query = query.eq("status", status_filter)
                query = query.order("created_at", desc=True)
            else:
                now_iso = datetime.now(timezone.utc).isoformat()
                query = (
                    query.eq("status", "published")
                    .lte("published_at", now_iso)
                    .order("published_at", desc=True)
                )

            if tag:
                query = query.contains("tags", [tag.strip().lower()])

            if search:
                cleaned = _sanitize_search(search)
                if cleaned:
                    # postgrest 0.13.2 (pinned by supabase 2.0.3) has no .or_()
                    # helper, so the `or=` param is added directly. Wildcards are
                    # `*` here, not `%` — that is the URL form of the operator.
                    query.params = query.params.add(
                        "or",
                        f"(title.ilike.*{cleaned}*,"
                        f"excerpt.ilike.*{cleaned}*,"
                        f"focus_keyword.ilike.*{cleaned}*)",
                    )

            query = query.range(offset, offset + limit)

            response = query.execute()
            posts = response.data or []
            total = response.count if response.count is not None else len(posts)

            logger.info(
                f"Listed {len(posts)} blog posts "
                f"(tag={tag}, search={search}, offset={offset}, admin={include_unpublished})"
            )

            return {
                "posts": posts,
                "count": len(posts),
                "offset": offset,
                "limit": limit,
                "total": total,
            }

        except Exception as e:
            logger.error(f"Error listing blog posts: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch blog posts",
            )

    async def get_post_by_slug(self, slug: str) -> Dict[str, Any]:
        """
        Get a single published post by slug, for the public article page.

        Unpublished and future-dated posts 404 here exactly as a missing post
        would — a draft URL must not be distinguishable from a nonexistent one.
        """
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            response = (
                self.db.table("blog_posts")
                .select("*")
                .eq("slug", slug)
                .eq("status", "published")
                .lte("published_at", now_iso)
                .maybe_single()
                .execute()
            )
            if not response or not response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Blog post not found: {slug}",
                )
            return response.data

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching blog post '{slug}': {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch blog post",
            )

    async def get_post_by_id(self, post_id: str) -> Dict[str, Any]:
        """Get any post by UUID regardless of status. Admin use. 404 if missing."""
        try:
            response = (
                self.db.table("blog_posts")
                .select("*")
                .eq("id", post_id)
                .maybe_single()
                .execute()
            )
            if not response or not response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Blog post not found: {post_id}",
                )
            return response.data

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching blog post {post_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch blog post",
            )

    async def get_related_posts(self, slug: str, tags: List[str], limit: int = 3) -> List[Dict[str, Any]]:
        """
        Published posts sharing at least one tag with the given post.

        Used by the article page's "Read next" section, which is what keeps a
        reader moving through the blog and on toward the salon pages.
        """
        try:
            if not tags:
                return []
            now_iso = datetime.now(timezone.utc).isoformat()
            response = (
                self.db.table("blog_posts")
                .select(LIST_COLUMNS)
                .eq("status", "published")
                .lte("published_at", now_iso)
                .neq("slug", slug)
                # `.ov()` is postgrest's array-overlap operator; there is no
                # `.overlaps()` alias on this client version.
                .ov("tags", tags)
                .order("published_at", desc=True)
                .limit(limit)
                .execute()
            )
            return response.data or []

        except Exception as e:
            # A failed "read next" block must never take down the article itself.
            logger.error(f"Error fetching related posts for '{slug}': {e}")
            return []

    async def get_sitemap_entries(self) -> List[Dict[str, Any]]:
        """Slug + timestamps for every live post, consumed by sitemap.xml."""
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            response = (
                self.db.table("blog_posts")
                .select("slug,updated_at,published_at")
                .eq("status", "published")
                .lte("published_at", now_iso)
                .order("published_at", desc=True)
                .execute()
            )
            return response.data or []

        except Exception as e:
            logger.error(f"Error building blog sitemap entries: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to build sitemap entries",
            )

    async def get_tags(self) -> List[str]:
        """Distinct tags across live posts, sorted, for the index filter bar."""
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            response = (
                self.db.table("blog_posts")
                .select("tags")
                .eq("status", "published")
                .lte("published_at", now_iso)
                .execute()
            )
            unique: set = set()
            for row in response.data or []:
                unique.update(row.get("tags") or [])
            return sorted(unique)

        except Exception as e:
            logger.error(f"Error fetching blog tags: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch blog tags",
            )

    # =====================================================
    # WRITE (Admin)
    # =====================================================

    async def create_post(self, post_data: Dict[str, Any], created_by: Optional[str] = None) -> Dict[str, Any]:
        """Create a post, generating a unique slug and derived fields."""
        try:
            payload = dict(post_data)

            base_slug = payload.get("slug") or _generate_slug(payload["title"])
            payload["slug"] = await self._ensure_unique_slug(base_slug)

            payload["content"] = _sanitize_html(payload.get("content"))
            payload["reading_minutes"] = _reading_minutes(payload["content"])

            if not payload.get("excerpt"):
                payload["excerpt"] = self._auto_excerpt(payload["content"])

            payload["published_at"] = self._resolve_published_at(
                payload.get("status", "draft"), payload.get("published_at")
            )

            if created_by:
                payload["created_by"] = created_by

            response = self.db.table("blog_posts").insert(self._serialize(payload)).execute()
            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create blog post",
                )

            created = response.data[0]
            logger.info(f"Blog post created: {created['id']} ({created['slug']})")
            return created

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating blog post: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create blog post",
            )

    async def update_post(self, post_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update a post. Only provided fields change.

        `status` and `published_at` are resolved against the post's *current*
        state so that publishing an existing draft stamps a publish date, while
        editing an already-live post leaves its original date alone.
        """
        try:
            existing = await self.get_post_by_id(post_id)

            payload = {k: v for k, v in updates.items() if v is not None}
            if not payload:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No fields provided for update",
                )
            payload.pop("id", None)
            payload.pop("created_at", None)
            payload.pop("created_by", None)

            if payload.get("slug") and payload["slug"] != existing["slug"]:
                payload["slug"] = await self._ensure_unique_slug(payload["slug"], exclude_id=post_id)

            if "content" in payload:
                payload["content"] = _sanitize_html(payload["content"])
                payload["reading_minutes"] = _reading_minutes(payload["content"])

            new_status = payload.get("status", existing.get("status"))
            if "status" in payload or "published_at" in payload:
                payload["published_at"] = self._resolve_published_at(
                    new_status,
                    payload.get("published_at") or existing.get("published_at"),
                )

            # Publishing must not push an empty article live, whether the body is
            # being changed in this request or was already empty on the row.
            if new_status == "published":
                body = payload.get("content", existing.get("content"))
                if not _strip_html(body):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Cannot publish a post with empty content",
                    )

            response = (
                self.db.table("blog_posts")
                .update(self._serialize(payload))
                .eq("id", post_id)
                .execute()
            )
            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Blog post not found: {post_id}",
                )

            updated = response.data[0]
            logger.info(f"Blog post updated: {post_id} (fields: {list(payload.keys())})")
            return updated

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating blog post {post_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update blog post",
            )

    async def delete_post(self, post_id: str, hard_delete: bool = False) -> Dict[str, Any]:
        """
        Delete a post. Soft-delete (status='archived') by default.

        Archiving rather than dropping the row keeps the slug reserved, so a URL
        that search engines have already indexed cannot later be reused by a
        different article.
        """
        try:
            if hard_delete:
                await self.get_post_by_id(post_id)  # 404 if missing
                self.db.table("blog_posts").delete().eq("id", post_id).execute()
                logger.warning(f"Blog post permanently deleted: {post_id}")
                return {"message": "Blog post permanently deleted", "post_id": post_id}

            response = (
                self.db.table("blog_posts")
                .update({"status": "archived"})
                .eq("id", post_id)
                .execute()
            )
            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Blog post not found: {post_id}",
                )
            logger.info(f"Blog post archived: {post_id}")
            return {"message": "Blog post archived", "post_id": post_id}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting blog post {post_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete blog post",
            )

    # =====================================================
    # HELPERS
    # =====================================================

    async def _ensure_unique_slug(self, base_slug: str, exclude_id: Optional[str] = None) -> str:
        """
        Return base_slug, or base-slug-2, base-slug-3 … if it is already taken.

        Mirrors ProductService slug handling. Not race-proof on its own — the
        UNIQUE constraint on blog_posts.slug is the real guarantee; this just
        avoids surfacing a constraint violation for the common case.
        """
        try:
            query = self.db.table("blog_posts").select("slug").like("slug", f"{base_slug}%")
            if exclude_id:
                query = query.neq("id", exclude_id)
            response = query.execute()
            taken = {row["slug"] for row in (response.data or [])}

            if base_slug not in taken:
                return base_slug

            suffix = 2
            while f"{base_slug}-{suffix}" in taken:
                suffix += 1
            return f"{base_slug}-{suffix}"

        except Exception as e:
            logger.error(f"Error checking slug uniqueness for '{base_slug}': {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to validate post slug",
            )

    @staticmethod
    def _resolve_published_at(post_status: str, published_at: Optional[Any]) -> Optional[Any]:
        """
        Stamp a publish date when a post goes live without one.

        A caller-supplied future date is preserved — that is how scheduling is
        expressed. Drafts and archived posts keep whatever they had, so
        unpublishing and republishing does not silently reset the date.
        """
        if post_status == "published" and not published_at:
            return datetime.now(timezone.utc)
        return published_at

    @staticmethod
    def _auto_excerpt(content: str, max_length: int = 200) -> str:
        """First ~200 characters of body text, cut on a word boundary."""
        text = _strip_html(content)
        if len(text) <= max_length:
            return text
        return text[:max_length].rsplit(" ", 1)[0] + "…"

    @staticmethod
    def _serialize(data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert datetime values to ISO strings so PostgREST/JSON accepts them."""
        return {
            k: (v.isoformat() if isinstance(v, datetime) else v)
            for k, v in data.items()
        }
