"""
Response Pydantic schemas for Blog endpoints.
Defines the response contracts for the blog API.
"""
from typing import List, Optional

from pydantic import BaseModel


class BlogPostResponse(BaseModel):
    """Single blog post response."""
    success: bool = True
    post: dict


class BlogPostListResponse(BaseModel):
    """Paginated blog post list response."""
    success: bool = True
    posts: List[dict]
    count: int
    offset: int
    limit: int
    total: int


class BlogPostOperationResponse(BaseModel):
    """Generic create/update acknowledgement."""
    success: bool = True
    message: str
    post: Optional[dict] = None


class BlogPostDeleteResponse(BaseModel):
    """Blog post deletion response."""
    success: bool = True
    message: str
    post_id: str


class BlogSitemapEntry(BaseModel):
    """One URL entry for sitemap.xml generation."""
    slug: str
    updated_at: Optional[str] = None
    published_at: Optional[str] = None


class BlogSitemapResponse(BaseModel):
    """Slug + timestamp feed consumed by the website's sitemap.xml function."""
    success: bool = True
    entries: List[BlogSitemapEntry]
    count: int


class BlogTagsResponse(BaseModel):
    """Distinct tags across published posts, for the blog index filter bar."""
    success: bool = True
    tags: List[str]
    count: int
