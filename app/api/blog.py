"""
Blog API Endpoints

Public endpoints (consumed by the website's server-rendering function):
    GET  /blog                    — Paginated list of live posts
    GET  /blog/tags               — Distinct tags for the index filter bar
    GET  /blog/sitemap-data       — Slug + timestamp feed for sitemap.xml
    GET  /blog/{slug}             — Single live post (+ related posts)

Admin endpoints (require admin role + the 'blog' feature entitlement):
    GET    /blog/admin/all        — List all posts including drafts
    GET    /blog/admin/{post_id}  — Fetch any post for editing
    POST   /blog                  — Create post
    PUT    /blog/{post_id}        — Update post
    DELETE /blog/{post_id}        — Archive post (hard=true to purge)

IMPORTANT: Static path segments (/tags, /sitemap-data, /admin) MUST be defined
before the catch-all /{slug} route, or "tags" would be read as a post slug.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from supabase import Client

from app.core.database import get_db_client
from app.core.auth import RequireFeature, TokenData
from app.services.blog_service import BlogService
from app.schemas.request.blog import BlogPostCreate, BlogPostUpdate
from app.schemas.response.blog import (
    BlogPostListResponse,
    BlogPostOperationResponse,
    BlogPostDeleteResponse,
    BlogSitemapResponse,
    BlogTagsResponse,
)

router = APIRouter(prefix="/blog", tags=["blog"])

# Admin blog routes require the 'blog' entitlement on top of the admin role.
# While the flag sits at 'internal' these 404 for the client's admins and stay
# open to internal staff, so blog content can be published in production before
# the feature is sold. The public routes below are ungated — published posts
# must render for readers and crawlers either way.
require_blog = RequireFeature("blog")


# ========================================
# DEPENDENCY INJECTION
# ========================================

def get_blog_service(db: Client = Depends(get_db_client)) -> BlogService:
    """Dependency injection for BlogService."""
    return BlogService(db_client=db)


# ========================================
# PUBLIC ENDPOINTS
# ========================================

@router.get("", response_model=BlogPostListResponse)
async def list_blog_posts(
    tag: Optional[str] = Query(None, description="Filter to posts carrying this tag"),
    search: Optional[str] = Query(None, description="Search title, excerpt and focus keyword"),
    limit: int = Query(12, ge=1, le=50, description="Maximum results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    blog_service: BlogService = Depends(get_blog_service),
):
    """
    List published blog posts, newest first.

    **Public endpoint** — no auth required. Returns only posts that are
    published and whose publish date has passed, so scheduled posts stay hidden
    until their time. Article bodies are omitted; use the detail route for those.
    """
    result = await blog_service.list_posts(tag=tag, search=search, limit=limit, offset=offset)
    return {"success": True, **result}


@router.get("/tags", response_model=BlogTagsResponse)
async def list_blog_tags(
    blog_service: BlogService = Depends(get_blog_service),
):
    """
    Distinct tags across all live posts.

    **Public endpoint** — drives the filter bar on the blog index page.
    """
    tags = await blog_service.get_tags()
    return {"success": True, "tags": tags, "count": len(tags)}


@router.get("/sitemap-data", response_model=BlogSitemapResponse)
async def blog_sitemap_data(
    blog_service: BlogService = Depends(get_blog_service),
):
    """
    Slug and timestamp feed for every live post.

    **Public endpoint** — consumed by the website's `sitemap.xml` serverless
    function. Kept separate from the list endpoint so the sitemap is not
    constrained by pagination.
    """
    entries = await blog_service.get_sitemap_entries()
    return {"success": True, "entries": entries, "count": len(entries)}


# ========================================
# ADMIN ENDPOINTS (static paths before catch-all)
# ========================================

@router.get("/admin/all", response_model=BlogPostListResponse)
async def admin_list_all_posts(
    status_filter: Optional[str] = Query(
        None, alias="status", description="Narrow to draft, published or archived"
    ),
    search: Optional[str] = Query(None, description="Search title, excerpt and focus keyword"),
    limit: int = Query(25, ge=1, le=100, description="Maximum results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: TokenData = Depends(require_blog),
    blog_service: BlogService = Depends(get_blog_service),
):
    """
    List ALL posts including drafts, scheduled and archived.

    **Admin only** — for the blog management table.
    """
    result = await blog_service.list_posts(
        search=search,
        limit=limit,
        offset=offset,
        include_unpublished=True,
        status_filter=status_filter,
    )
    return {"success": True, **result}


@router.get("/admin/{post_id}", response_model=BlogPostOperationResponse)
async def admin_get_post(
    post_id: str,
    current_user: TokenData = Depends(require_blog),
    blog_service: BlogService = Depends(get_blog_service),
):
    """
    Fetch any post by UUID regardless of status, for the editor screen.

    **Admin only.** The public `/blog/{slug}` route 404s on drafts, so the
    editor needs this id-based route to load work in progress.
    """
    post = await blog_service.get_post_by_id(post_id)
    return {"success": True, "message": "Blog post retrieved", "post": post}


@router.post("", response_model=BlogPostOperationResponse)
async def create_blog_post(
    payload: BlogPostCreate,
    current_user: TokenData = Depends(require_blog),
    blog_service: BlogService = Depends(get_blog_service),
):
    """
    Create a blog post.

    **Admin only.** The slug is generated from the title when omitted, the body
    is sanitised against the editor allowlist, and read time is computed on save.
    `cover_image_url` should come from `/upload/cloudinary-blog-image`.
    """
    post = await blog_service.create_post(
        payload.model_dump(exclude_none=True),
        created_by=current_user.user_id,
    )
    return {"success": True, "message": "Blog post created successfully", "post": post}


# ========================================
# CATCH-ALL PARAMETRIC ROUTES (must be last)
# ========================================

@router.put("/{post_id}", response_model=BlogPostOperationResponse)
async def update_blog_post(
    post_id: str,
    payload: BlogPostUpdate,
    current_user: TokenData = Depends(require_blog),
    blog_service: BlogService = Depends(get_blog_service),
):
    """
    Update an existing post.

    **Admin only.** Only provided (non-None) fields are updated. Changing a
    published post's slug breaks any link search engines have already indexed —
    the admin UI warns before allowing it.
    """
    post = await blog_service.update_post(post_id, payload.model_dump(exclude_none=True))
    return {"success": True, "message": "Blog post updated successfully", "post": post}


@router.delete("/{post_id}", response_model=BlogPostDeleteResponse)
async def delete_blog_post(
    post_id: str,
    hard: bool = Query(False, description="If true, permanently delete instead of archiving"),
    current_user: TokenData = Depends(require_blog),
    blog_service: BlogService = Depends(get_blog_service),
):
    """
    Delete a post.

    **Admin only.** Default archives the post (`status='archived'`), which keeps
    the slug reserved so an indexed URL is never reused by a different article.
    `hard=true` removes the row permanently.
    """
    result = await blog_service.delete_post(post_id, hard_delete=hard)
    return {"success": True, "message": result["message"], "post_id": result["post_id"]}


@router.get("/{slug}", response_model=BlogPostOperationResponse)
async def get_blog_post(
    slug: str,
    blog_service: BlogService = Depends(get_blog_service),
):
    """
    Get a single published post by slug, with up to three related posts.

    **Public endpoint** — this is what the website's server-rendering function
    calls to build the article HTML, meta tags and structured data. Drafts and
    scheduled posts return 404, indistinguishable from a nonexistent slug.
    """
    post = await blog_service.get_post_by_slug(slug)
    post["related_posts"] = await blog_service.get_related_posts(
        slug=slug, tags=post.get("tags") or []
    )
    return {"success": True, "message": "Blog post retrieved", "post": post}
