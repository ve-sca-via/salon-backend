"""
Integration tests for the blog module against a real local Supabase stack.

These exist because the mocked suite (tests/test_blog_mocked.py) talks to a
hand-rolled fake, and a fake can drift from the real client. Two bugs got
through the mocks and were only caught here:

  * `.or_()` does not exist on postgrest 0.13.2 (pinned by supabase 2.0.3) —
    the search filter raised AttributeError and every search 500'd.
  * the array-overlap operator is `.ov()`, not `.overlaps()` — related posts
    threw, and because that failure is deliberately swallowed to protect the
    article page, the feature silently returned an empty list forever.

So the emphasis here is deliberately on the things only a real database and a
real client can prove: PostgREST filter grammar, array columns, the status
CHECK constraint, and the published/scheduled visibility split.

Requires a running local Supabase stack (`supabase start`); skipped otherwise.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.services.blog_service import BlogService

API = settings.API_PREFIX

# Every row this module creates carries this prefix so cleanup can find them
# even if an assertion fails part-way through.
PREFIX = "itest-blog"


@pytest.fixture()
def blog(service_client):
    """BlogService on the live stack, with cleanup of anything it created."""
    svc = BlogService(db_client=service_client)
    created: list[str] = []

    def make(**fields):
        fields.setdefault("title", f"{PREFIX} {uuid.uuid4().hex[:8]}")
        fields.setdefault("content", "<p>Body copy for the integration test.</p>")
        return fields

    svc.make = make
    svc.created = created
    yield svc

    for row in service_client.table("blog_posts").select("id").like("slug", f"{PREFIX}%").execute().data or []:
        service_client.table("blog_posts").delete().eq("id", row["id"]).execute()


async def _create(blog, **fields):
    post = await blog.create_post(blog.make(**fields))
    blog.created.append(post["id"])
    return post


# =====================================================================
# Filter grammar — the part the fake cannot prove
# =====================================================================
@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_filter_is_valid_postgrest_grammar(blog):
    """Regression: `.or_()` is absent on this client; search must still work."""
    await _create(blog, title=f"{PREFIX} Bridal Makeup Guide",
                  status="published", focus_keyword="bridal makeup")

    hit = await blog.list_posts(search="Bridal Makeup")
    assert hit["total"] >= 1

    # Punctuation must not corrupt the `or=(...)` expression.
    punct = await blog.list_posts(search="bridal, makeup (2026)")
    assert isinstance(punct["total"], int)

    assert (await blog.list_posts(search="zzz-no-such-term"))["total"] == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_matches_the_focus_keyword_column(blog):
    await _create(blog, title=f"{PREFIX} Untitled", status="published",
                  focus_keyword="keratin treatment cost")
    assert (await blog.list_posts(search="keratin treatment"))["total"] >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tag_array_round_trips_and_filters(blog):
    """text[] columns and the `contains` operator against real Postgres."""
    post = await _create(blog, status="published", tags=["hair spa", "delhi"])
    assert post["tags"] == ["hair spa", "delhi"]

    hit = await blog.list_posts(tag="delhi")
    assert post["slug"] in [p["slug"] for p in hit["posts"]]

    miss = await blog.list_posts(tag="no-such-tag")
    assert miss["total"] == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_related_posts_actually_match_on_tag_overlap(blog):
    """
    Regression: `.ov()` vs `.overlaps()`. Asserts a NON-EMPTY result — an empty
    list would pass vacuously, which is how the original bug stayed hidden.
    """
    main = await _create(blog, status="published", tags=["hair spa", "delhi"])
    sibling = await _create(blog, status="published", tags=["hair spa", "care"])
    await _create(blog, status="published", tags=["nails"])

    related = await blog.get_related_posts(main["slug"], ["hair spa"])
    slugs = [r["slug"] for r in related]

    assert sibling["slug"] in slugs, "tag-overlap query returned no sibling"
    assert main["slug"] not in slugs
    assert await blog.get_related_posts(main["slug"], []) == []


# =====================================================================
# Publication state against real timestamps
# =====================================================================
@pytest.mark.integration
@pytest.mark.asyncio
async def test_scheduled_post_is_invisible_until_its_date(blog):
    future = datetime.now(timezone.utc) + timedelta(days=7)
    post = await _create(blog, status="published", published_at=future)

    listed = [p["slug"] for p in (await blog.list_posts())["posts"]]
    assert post["slug"] not in listed

    with pytest.raises(Exception) as exc:
        await blog.get_post_by_slug(post["slug"])
    assert getattr(exc.value, "status_code", None) == 404

    sitemap = [e["slug"] for e in await blog.get_sitemap_entries()]
    assert post["slug"] not in sitemap


@pytest.mark.integration
@pytest.mark.asyncio
async def test_draft_is_invisible_and_publishing_stamps_a_date(blog):
    post = await _create(blog, status="draft")
    assert post["published_at"] is None

    with pytest.raises(Exception):
        await blog.get_post_by_slug(post["slug"])

    published = await blog.update_post(post["id"], {"status": "published"})
    assert published["published_at"] is not None
    assert (await blog.get_post_by_slug(post["slug"]))["slug"] == post["slug"]


# =====================================================================
# Constraints and data integrity
# =====================================================================
@pytest.mark.integration
@pytest.mark.asyncio
async def test_slug_uniqueness_is_enforced_by_the_database(blog, service_client):
    post = await _create(blog, status="published")

    with pytest.raises(Exception):
        service_client.table("blog_posts").insert({
            "slug": post["slug"], "title": "duplicate", "content": "<p>x</p>",
        }).execute()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_status_check_constraint_rejects_unknown_values(blog, service_client):
    post = await _create(blog)

    with pytest.raises(Exception):
        service_client.table("blog_posts").update(
            {"status": "scheduled"}   # deliberately not a valid status
        ).eq("id", post["id"]).execute()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_archiving_keeps_the_slug_reserved(blog):
    """An indexed URL must never be reusable by a different article."""
    post = await _create(blog, status="published")
    await blog.delete_post(post["id"])

    reuse = await _create(blog, title=post["title"], status="published")
    assert reuse["slug"] != post["slug"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_content_is_sanitised_on_the_way_into_the_database(blog, service_client):
    """Verify against what is STORED, not just what the call returned."""
    post = await _create(blog, content=(
        '<h2>Heading</h2><script>alert(1)</script>'
        '<p onclick="x()">Text</p><a href="javascript:bad()">link</a>'
    ))

    stored = service_client.table("blog_posts").select("content").eq(
        "id", post["id"]
    ).single().execute().data["content"]

    assert "<h2>Heading</h2>" in stored
    for vector in ("script", "onclick", "javascript:"):
        assert vector not in stored.lower()


# =====================================================================
# HTTP surface
# =====================================================================
@pytest.mark.integration
def test_public_blog_routes_need_no_auth(integration_client):
    for path in ("", "/tags", "/sitemap-data"):
        resp = integration_client.get(f"{API}/blog{path}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True


@pytest.mark.integration
def test_admin_blog_routes_reject_anonymous_callers(integration_client):
    assert integration_client.get(f"{API}/blog/admin/all").status_code in (401, 403)
    assert integration_client.post(f"{API}/blog", json={"title": "x"}).status_code in (401, 403)


@pytest.mark.integration
def test_static_segments_are_not_captured_by_the_slug_route(integration_client):
    """`/blog/tags` must return the tag list, never a 404 post lookup."""
    body = integration_client.get(f"{API}/blog/tags").json()
    assert "tags" in body and isinstance(body["tags"], list)
