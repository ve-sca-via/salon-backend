"""
Request Pydantic schemas for Blog endpoints.
Validation for the admin-managed, SEO-targeted blog.

SEO note: meta_title / meta_description are length-capped to what search engines
actually render (70 / 160 chars). The admin editor shows live counters against
these same limits, so the API and the UI agree on what "too long" means.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# Search engines truncate beyond roughly these lengths.
META_TITLE_MAX = 70
META_DESCRIPTION_MAX = 160

# FAQ entries render as a collapsible list at the bottom of the article and
# feed a FAQPage JSON-LD block, so they are capped well short of what would
# make either the accordion or the rich-snippet unreadable.
FAQ_QUESTION_MAX = 300
FAQ_ANSWER_MAX = 2000
FAQS_MAX_ITEMS = 20

VALID_STATUSES = {"draft", "published", "archived"}


class FaqItem(BaseModel):
    """One collapsible question/answer pair. Plain text — no HTML allowed."""
    question: str = Field(..., min_length=1, max_length=FAQ_QUESTION_MAX)
    answer: str = Field(..., min_length=1, max_length=FAQ_ANSWER_MAX)

    @field_validator("question", "answer")
    @classmethod
    def strip_and_require(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("Each FAQ needs both a question and an answer")
        return v


def _clean_tags(tags: Optional[List[str]]) -> Optional[List[str]]:
    """Lowercase, trim, drop blanks, and de-duplicate while preserving order."""
    if tags is None:
        return None
    seen = set()
    cleaned = []
    for tag in tags:
        normalized = (tag or "").strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            cleaned.append(normalized)
    return cleaned


class BlogPostCreate(BaseModel):
    """Schema for creating a blog post."""
    title: str = Field(..., min_length=1, max_length=300, description="Article headline")
    slug: Optional[str] = Field(
        None,
        max_length=200,
        description="URL segment. Auto-generated from the title when omitted; uniqueness is enforced server-side",
    )
    excerpt: Optional[str] = Field(None, max_length=500, description="Listing-card summary")
    content: str = Field(default="", description="Article body as HTML from the editor (sanitised server-side)")

    cover_image_url: Optional[str] = Field(None, max_length=1000, description="Cover image URL from the upload endpoint")
    cover_image_alt: Optional[str] = Field(None, max_length=300, description="Cover image alt text (required when a cover is set)")

    meta_title: Optional[str] = Field(None, max_length=META_TITLE_MAX, description="Search-result title; falls back to title")
    meta_description: Optional[str] = Field(None, max_length=META_DESCRIPTION_MAX, description="Search-result snippet; falls back to excerpt")
    focus_keyword: Optional[str] = Field(None, max_length=200, description="The term this article targets")

    tags: Optional[List[str]] = Field(default=None, description="Flat taxonomy; normalized to lowercase")
    author_name: Optional[str] = Field(None, max_length=150, description="Display byline")

    faqs: Optional[List[FaqItem]] = Field(
        default=None,
        max_length=FAQS_MAX_ITEMS,
        description="Collapsible FAQ entries shown at the bottom of the article",
    )

    status: str = Field(default="draft", description="draft | published | archived")
    published_at: Optional[datetime] = Field(
        None,
        description="Publication timestamp. A future value schedules the post; defaults to now when publishing",
    )

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v):
        if v is None:
            return v
        v = v.strip().lower()
        if not v:
            return None
        if not all(c.isalnum() or c == "-" for c in v):
            raise ValueError("slug may only contain letters, numbers and hyphens")
        return v.strip("-")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v not in VALID_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(VALID_STATUSES))}")
        return v

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, v):
        return _clean_tags(v)

    @model_validator(mode="after")
    def validate_publishable(self):
        # An image with no alt text is an accessibility and SEO defect; catch it
        # at the API boundary rather than trusting the editor to have enforced it.
        if self.cover_image_url and not (self.cover_image_alt or "").strip():
            raise ValueError("cover_image_alt is required when cover_image_url is set")
        if self.status == "published" and not (self.content or "").strip():
            raise ValueError("Cannot publish a post with empty content")
        return self


class BlogPostUpdate(BaseModel):
    """Schema for updating a blog post (all fields optional)."""
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    slug: Optional[str] = Field(None, max_length=200)
    excerpt: Optional[str] = Field(None, max_length=500)
    content: Optional[str] = None

    cover_image_url: Optional[str] = Field(None, max_length=1000)
    cover_image_alt: Optional[str] = Field(None, max_length=300)

    meta_title: Optional[str] = Field(None, max_length=META_TITLE_MAX)
    meta_description: Optional[str] = Field(None, max_length=META_DESCRIPTION_MAX)
    focus_keyword: Optional[str] = Field(None, max_length=200)

    tags: Optional[List[str]] = None
    author_name: Optional[str] = Field(None, max_length=150)

    faqs: Optional[List[FaqItem]] = Field(default=None, max_length=FAQS_MAX_ITEMS)

    status: Optional[str] = None
    published_at: Optional[datetime] = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v):
        if v is None:
            return v
        v = v.strip().lower()
        if not v:
            return None
        if not all(c.isalnum() or c == "-" for c in v):
            raise ValueError("slug may only contain letters, numbers and hyphens")
        return v.strip("-")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v is not None and v not in VALID_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(VALID_STATUSES))}")
        return v

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, v):
        return _clean_tags(v)

    @model_validator(mode="after")
    def validate_cover_alt(self):
        if self.cover_image_url and self.cover_image_alt is not None and not self.cover_image_alt.strip():
            raise ValueError("cover_image_alt cannot be blank when cover_image_url is set")
        return self
