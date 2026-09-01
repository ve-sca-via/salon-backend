"""
Mocked route tests for the blog module (app/api/blog.py +
app/services/blog_service.py).

Same approach as test_banner_mocked.py: the Supabase client is replaced with a
small in-memory fake and the admin blog gate (require_blog) is overridden. The
full HTTP path is exercised:

    HTTP -> FastAPI (auth dep overridden, rate limiter disabled) -> route ->
    BlogService -> FakeSupabase.

The fake is a superset of the banner one — blog queries additionally use
count="exact", lte/neq/like/contains/overlaps and or_.

Scope, weighted toward the things that would silently damage SEO if they broke:
the published/scheduled/draft visibility split, slug uniqueness and stability,
HTML sanitisation, and the sitemap feed.

No marker -> runs in the fast (no-stack) job alongside the smoke suite.
"""
import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db_client
from app.core.auth import TokenData
from app.api.blog import require_blog

API = settings.API_PREFIX
BLOG = f"{API}/blog"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


NOW = datetime.now(timezone.utc)
PAST = _iso(NOW - timedelta(days=2))
FUTURE = _iso(NOW + timedelta(days=7))


# =====================================================================
# In-memory fake Supabase client (covers the ops blog_service uses)
# =====================================================================
class _Resp:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


def _like_to_regex(pattern: str) -> re.Pattern:
    """Translate a SQL LIKE/ILIKE pattern into a compiled case-insensitive regex."""
    return re.compile("^" + re.escape(pattern).replace("%", ".*") + "$", re.IGNORECASE)


class _Params:
    """Minimal stand-in for postgrest's immutable params bag (only `or` is used)."""

    def __init__(self, query):
        self._query = query

    def add(self, key, value):
        if key == "or":
            self._query._or = value
        return self


class _Query:
    def __init__(self, table):
        self._table = table
        self._filters = []
        self._or = None
        self.params = _Params(self)
        self._op = ("select", "*")
        self._count = None
        self._cols = None
        self._maybe = False
        self._order = []
        self._range = None
        self._limit = None

    # -- op selection --
    def select(self, cols="*", count=None):
        self._op = ("select", cols)
        self._count = count
        # Column projection is honoured so tests can assert that list endpoints
        # really do leave `content` behind rather than the fake papering over it.
        self._cols = None if cols == "*" else [c.strip() for c in cols.split(",")]
        return self

    def insert(self, payload):
        self._op = ("insert", payload)
        return self

    def update(self, payload):
        self._op = ("update", payload)
        return self

    def delete(self):
        self._op = ("delete", None)
        return self

    # -- filters --
    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def neq(self, col, val):
        self._filters.append(("neq", col, val))
        return self

    def lte(self, col, val):
        self._filters.append(("lte", col, val))
        return self

    def like(self, col, val):
        self._filters.append(("like", col, val))
        return self

    def contains(self, col, val):
        self._filters.append(("contains", col, val))
        return self

    def ov(self, col, val):
        # postgrest 0.13.2 names the array-overlap operator `ov`; there is no
        # `.overlaps()` alias. The fake mirrors that so the tests cannot pass
        # against a method the real client does not have.
        self._filters.append(("overlaps", col, val))
        return self

    # -- shaping --
    def order(self, col, desc=False):
        self._order.append((col, desc))
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def maybe_single(self):
        self._maybe = True
        return self

    # -- matching --
    def _match(self, row):
        for op, c, v in self._filters:
            actual = row.get(c)
            if op == "eq" and actual != v:
                return False
            if op == "neq" and actual == v:
                return False
            if op == "lte":
                # NULL never satisfies a bound, matching SQL semantics.
                if actual is None or str(actual) > str(v):
                    return False
            if op == "like" and (actual is None or not _like_to_regex(v).match(str(actual))):
                return False
            if op == "contains" and not set(v).issubset(set(actual or [])):
                return False
            if op == "overlaps" and not (set(v) & set(actual or [])):
                return False
        return self._match_or(row)

    def _match_or(self, row):
        """
        Evaluate a PostgREST `or=` expression: `(col.ilike.*x*,col2.ilike.*y*)`.

        Wildcards are `*` in the URL form, so they are translated to `%` before
        being matched.
        """
        if not self._or:
            return True
        for clause in self._or.strip("()").split(","):
            parts = clause.strip().split(".", 2)
            if len(parts) != 3:
                continue
            col, op, val = parts
            actual = row.get(col)
            if op == "ilike" and actual is not None and                     _like_to_regex(val.replace("*", "%")).match(str(actual)):
                return True
        return False

    def execute(self):
        op, payload = self._op
        rows = self._table.rows

        if op == "select":
            matched = [dict(r) for r in rows if self._match(r)]
            total = len(matched)
            for col, desc in reversed(self._order):
                matched.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
            if self._range is not None:
                s, e = self._range
                matched = matched[s:e]
            if self._limit is not None:
                matched = matched[: self._limit]
            if self._cols is not None:
                matched = [{k: r[k] for k in self._cols if k in r} for r in matched]
            if self._maybe:
                return _Resp(matched[0] if matched else None)
            return _Resp(matched, count=total if self._count else None)

        if op == "insert":
            new_rows = payload if isinstance(payload, list) else [payload]
            added = []
            for nr in new_rows:
                row = dict(nr)
                row.setdefault("id", str(uuid.uuid4()))
                row.setdefault("created_at", _iso(datetime.now(timezone.utc)))
                row.setdefault("updated_at", _iso(datetime.now(timezone.utc)))
                row.setdefault("status", "draft")
                row.setdefault("tags", [])
                row.setdefault("published_at", None)
                rows.append(row)
                added.append(dict(row))
            return _Resp(added)

        if op == "update":
            updated = []
            for r in rows:
                if self._match(r):
                    r.update(payload)
                    updated.append(dict(r))
            return _Resp(updated)

        if op == "delete":
            removed = [dict(r) for r in rows if self._match(r)]
            rows[:] = [r for r in rows if not self._match(r)]
            return _Resp(removed)

        return _Resp(None)


class _Table:
    def __init__(self):
        self.rows = []

    def select(self, cols="*", count=None):
        return _Query(self).select(cols, count=count)

    def insert(self, payload):
        return _Query(self).insert(payload)

    def update(self, payload):
        return _Query(self).update(payload)

    def delete(self):
        return _Query(self).delete()


class FakeSupabase:
    def __init__(self):
        self._tables = {}

    def table(self, name):
        return self._tables.setdefault(name, _Table())


# =====================================================================
# Test handle + fixture
# =====================================================================
class Handle:
    def __init__(self, db, app):
        self.db = db
        self.app = app
        self.client = TestClient(app)

    def seed_post(self, **fields):
        title = fields.pop("title", "A Post")
        row = {
            "id": fields.pop("id", str(uuid.uuid4())),
            "slug": fields.pop("slug", title.lower().replace(" ", "-")),
            "title": title,
            "excerpt": "An excerpt",
            "content": "<p>Body copy</p>",
            "cover_image_url": None,
            "cover_image_alt": None,
            "meta_title": None,
            "meta_description": None,
            "focus_keyword": None,
            "tags": [],
            "author_name": "Lubist",
            "status": "published",
            "published_at": PAST,
            "reading_minutes": 1,
            "created_by": None,
            "created_at": _iso(datetime.now(timezone.utc)),
            "updated_at": _iso(datetime.now(timezone.utc)),
        }
        row.update(fields)
        self.db.table("blog_posts").rows.append(row)
        return row

    def rows(self):
        return self.db.table("blog_posts").rows

    def login_admin(self, user_id="admin-1"):
        td = TokenData(
            user_id=user_id, email="admin@example.com", user_role="admin",
            jti="jti-test", exp=datetime.utcnow() + timedelta(hours=1),
        )
        # Override the RequireFeature("blog") instance itself, not require_admin.
        # RequireFeature applies its role dependency by direct call rather than
        # via Depends(), so overriding require_admin would not intercept it.
        self.app.dependency_overrides[require_blog] = lambda: td
        return td

    def clear_overrides(self):
        self.app.dependency_overrides.pop(require_blog, None)


@pytest.fixture()
def bg(app):
    db = FakeSupabase()
    handle = Handle(db=db, app=app)
    app.dependency_overrides[get_db_client] = lambda: db

    yield handle

    handle.clear_overrides()
    app.dependency_overrides.pop(get_db_client, None)


# =====================================================================
# GET /blog  (public list)
# =====================================================================
def test_public_list_returns_published_only(bg):
    bg.seed_post(title="Live", status="published")
    bg.seed_post(title="Draft", status="draft", published_at=None)
    bg.seed_post(title="Archived", status="archived")

    r = bg.client.get(BLOG)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert [p["title"] for p in body["posts"]] == ["Live"]


def test_public_list_hides_scheduled_posts(bg):
    """A published post dated in the future must stay invisible until its time."""
    bg.seed_post(title="Live now", published_at=PAST)
    bg.seed_post(title="Goes live next week", published_at=FUTURE)

    titles = [p["title"] for p in bg.client.get(BLOG).json()["posts"]]
    assert titles == ["Live now"]


def test_public_list_orders_newest_first(bg):
    bg.seed_post(title="Older", published_at=_iso(NOW - timedelta(days=10)))
    bg.seed_post(title="Newer", published_at=_iso(NOW - timedelta(days=1)))

    titles = [p["title"] for p in bg.client.get(BLOG).json()["posts"]]
    assert titles == ["Newer", "Older"]


def test_public_list_omits_article_body(bg):
    """Index payloads must not carry full article HTML."""
    bg.seed_post(title="Heavy", content="<p>" + "x" * 5000 + "</p>")

    post = bg.client.get(BLOG).json()["posts"][0]
    assert "content" not in post
    assert "excerpt" in post


def test_public_list_filters_by_tag(bg):
    bg.seed_post(title="Hair", tags=["hair", "spa"])
    bg.seed_post(title="Nails", tags=["nails"])

    titles = [p["title"] for p in bg.client.get(BLOG, params={"tag": "spa"}).json()["posts"]]
    assert titles == ["Hair"]


def test_public_list_search_matches_title_and_keyword(bg):
    bg.seed_post(title="Bridal makeup guide", focus_keyword="bridal makeup")
    bg.seed_post(title="Nail care", focus_keyword="nail art")

    r = bg.client.get(BLOG, params={"search": "bridal"})
    assert [p["title"] for p in r.json()["posts"]] == ["Bridal makeup guide"]


def test_public_list_paginates_with_total(bg):
    for i in range(5):
        bg.seed_post(title=f"Post {i}", slug=f"post-{i}",
                     published_at=_iso(NOW - timedelta(days=i + 1)))

    body = bg.client.get(BLOG, params={"limit": 2, "offset": 0}).json()
    assert body["count"] == 2
    assert body["total"] == 5      # total ignores pagination
    assert body["limit"] == 2

    page2 = bg.client.get(BLOG, params={"limit": 2, "offset": 2}).json()
    assert page2["offset"] == 2
    assert page2["posts"][0]["title"] != body["posts"][0]["title"]


def test_public_list_is_unauthenticated(bg):
    bg.seed_post(title="Anon-visible")
    assert bg.client.get(BLOG).status_code == 200


# =====================================================================
# GET /blog/{slug}  (public detail)
# =====================================================================
def test_get_post_by_slug(bg):
    bg.seed_post(title="Best Hair Spa", slug="best-hair-spa", content="<p>Full body</p>")

    r = bg.client.get(f"{BLOG}/best-hair-spa")
    assert r.status_code == 200, r.text
    post = r.json()["post"]
    assert post["title"] == "Best Hair Spa"
    assert post["content"] == "<p>Full body</p>"


def test_draft_slug_404s_like_a_missing_post(bg):
    """A draft URL must not be distinguishable from a nonexistent one."""
    bg.seed_post(slug="secret-draft", status="draft", published_at=None)

    draft = bg.client.get(f"{BLOG}/secret-draft")
    missing = bg.client.get(f"{BLOG}/never-existed")
    assert draft.status_code == missing.status_code == 404


def test_scheduled_slug_404s_until_published(bg):
    bg.seed_post(slug="future-post", published_at=FUTURE)
    assert bg.client.get(f"{BLOG}/future-post").status_code == 404


def test_detail_includes_related_posts_sharing_a_tag(bg):
    bg.seed_post(title="Main", slug="main", tags=["hair", "spa"])
    bg.seed_post(title="Shares tag", slug="shares", tags=["spa"])
    bg.seed_post(title="Unrelated", slug="unrelated", tags=["nails"])

    related = bg.client.get(f"{BLOG}/main").json()["post"]["related_posts"]
    assert [p["title"] for p in related] == ["Shares tag"]


def test_related_posts_exclude_the_article_itself(bg):
    bg.seed_post(title="Main", slug="main", tags=["hair"])
    slugs = [p["slug"] for p in bg.client.get(f"{BLOG}/main").json()["post"]["related_posts"]]
    assert "main" not in slugs


# =====================================================================
# GET /blog/tags  and  /blog/sitemap-data
# =====================================================================
def test_tags_endpoint_returns_sorted_distinct_live_tags(bg):
    bg.seed_post(slug="a", tags=["spa", "hair"])
    bg.seed_post(slug="b", tags=["hair", "bridal"])
    bg.seed_post(slug="c", tags=["draft-only"], status="draft", published_at=None)

    body = bg.client.get(f"{BLOG}/tags").json()
    assert body["tags"] == ["bridal", "hair", "spa"]   # sorted, deduped, drafts excluded


def test_sitemap_data_lists_live_posts_only(bg):
    bg.seed_post(slug="live-one")
    bg.seed_post(slug="live-two")
    bg.seed_post(slug="a-draft", status="draft", published_at=None)
    bg.seed_post(slug="scheduled", published_at=FUTURE)

    body = bg.client.get(f"{BLOG}/sitemap-data").json()
    slugs = {e["slug"] for e in body["entries"]}
    assert slugs == {"live-one", "live-two"}
    assert body["count"] == 2


def test_sitemap_route_is_not_swallowed_by_the_slug_route(bg):
    """Static segments must win over /{slug}; a post named 'tags' must not shadow it."""
    bg.seed_post(slug="tags", title="A post literally slugged tags")

    assert "tags" in bg.client.get(f"{BLOG}/tags").json()
    assert "entries" in bg.client.get(f"{BLOG}/sitemap-data").json()


# =====================================================================
# GET /blog/admin/all
# =====================================================================
def test_admin_list_includes_drafts_and_scheduled(bg):
    bg.login_admin()
    bg.seed_post(slug="live")
    bg.seed_post(slug="draft", status="draft", published_at=None)
    bg.seed_post(slug="scheduled", published_at=FUTURE)

    assert bg.client.get(f"{BLOG}/admin/all").json()["total"] == 3


def test_admin_list_filters_by_status(bg):
    bg.login_admin()
    bg.seed_post(slug="live")
    bg.seed_post(slug="draft", status="draft", published_at=None)

    body = bg.client.get(f"{BLOG}/admin/all", params={"status": "draft"}).json()
    assert [p["slug"] for p in body["posts"]] == ["draft"]


def test_admin_get_post_by_id_returns_a_draft(bg):
    bg.login_admin()
    row = bg.seed_post(slug="wip", status="draft", published_at=None)

    r = bg.client.get(f"{BLOG}/admin/{row['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["post"]["slug"] == "wip"


# =====================================================================
# POST /blog  (create)
# =====================================================================
def test_create_generates_slug_from_title(bg):
    bg.login_admin()
    r = bg.client.post(BLOG, json={
        "title": "Best Hair Spa in Delhi (2026)",
        "content": "<p>Body</p>",
    })
    assert r.status_code == 200, r.text
    assert r.json()["post"]["slug"] == "best-hair-spa-in-delhi-2026"


def test_create_deduplicates_a_colliding_slug(bg):
    bg.login_admin()
    bg.seed_post(slug="hair-spa")

    r = bg.client.post(BLOG, json={"title": "Hair Spa", "content": "<p>x</p>"})
    assert r.json()["post"]["slug"] == "hair-spa-2"


def test_create_sanitises_the_article_body(bg):
    bg.login_admin()
    r = bg.client.post(BLOG, json={
        "title": "Injected",
        "content": '<h2>Fine</h2><script>alert(1)</script><p onclick="x()">Text</p>',
    })
    content = r.json()["post"]["content"]
    assert "<h2>Fine</h2>" in content
    assert "script" not in content.lower()
    assert "onclick" not in content.lower()


def test_create_unwraps_the_span_and_div_soup_a_paste_arrives_as(bg):
    # span/div only ever come from a Google Docs / Word paste, where they exist
    # to carry a style attribute. The tags go, the copy stays.
    bg.login_admin()
    r = bg.client.post(BLOG, json={
        "title": "Pasted",
        "content": '<div><p><span style="font-family:Calibri">Hair colour</span></p></div>',
    })
    content = r.json()["post"]["content"]
    assert content == "<p>Hair colour</p>"


def test_create_drops_content_classes(bg):
    # prose.css styles article content by element only; a pasted class is dead
    # weight at best and a hook into the host stylesheet at worst.
    bg.login_admin()
    r = bg.client.post(BLOG, json={
        "title": "Classy", "content": '<p class="c14 docs-para">Copy</p>',
    })
    assert r.json()["post"]["content"] == "<p>Copy</p>"


def test_create_normalises_the_structural_debris_of_a_paste(bg):
    # The real shape the first published article stored: a heading bolted into
    # <strong>, a trailing <br> inside it, and empty trailing paragraphs. Each
    # one makes a block render unlike its neighbours.
    bg.login_admin()
    r = bg.client.post(BLOG, json={
        "title": "Debris",
        "content": (
            "<h2><strong>Why This Salon Earns Your Trust</strong><br></h2>"
            "<p>Body copy.</p><p></p><p><br></p>"
        ),
    })
    content = r.json()["post"]["content"]
    assert content == "<h2>Why This Salon Earns Your Trust</h2><p>Body copy.</p>"


def test_create_keeps_deliberate_emphasis_inside_a_heading(bg):
    # Only a bold wrapping the WHOLE heading is redundant. A bolded word next to
    # unbolded text is the author emphasising something.
    bg.login_admin()
    r = bg.client.post(BLOG, json={
        "title": "Emphasis", "content": "<h2><strong>Best</strong> salons</h2>",
    })
    assert r.json()["post"]["content"] == "<h2><strong>Best</strong> salons</h2>"


def test_create_computes_reading_time_and_excerpt(bg):
    bg.login_admin()
    r = bg.client.post(BLOG, json={
        "title": "Long read",
        "content": "<p>" + "word " * 600 + "</p>",
    })
    post = r.json()["post"]
    assert post["reading_minutes"] == 3          # 600 words / 200 wpm
    assert post["excerpt"].startswith("word")    # auto-derived from the body


def test_create_stamps_published_at_when_publishing(bg):
    bg.login_admin()
    r = bg.client.post(BLOG, json={
        "title": "Go live", "content": "<p>x</p>", "status": "published",
    })
    assert r.json()["post"]["published_at"] is not None


def test_create_preserves_a_future_date_for_scheduling(bg):
    bg.login_admin()
    r = bg.client.post(BLOG, json={
        "title": "Scheduled", "content": "<p>x</p>",
        "status": "published", "published_at": FUTURE,
    })
    post_id = r.json()["post"]["id"]
    stored = next(p for p in bg.rows() if p["id"] == post_id)
    assert stored["published_at"].startswith(FUTURE[:16])
    # ...and it stays out of the public feed until then.
    assert bg.client.get(BLOG).json()["total"] == 0


def test_create_records_the_author(bg):
    bg.login_admin(user_id="admin-42")
    r = bg.client.post(BLOG, json={"title": "Attributed", "content": "<p>x</p>"})
    assert r.json()["post"]["created_by"] == "admin-42"


def test_create_rejects_cover_image_without_alt_text(bg):
    bg.login_admin()
    r = bg.client.post(BLOG, json={
        "title": "No alt", "content": "<p>x</p>",
        "cover_image_url": "https://res.cloudinary.com/x/blog/a.jpg",
    })
    assert r.status_code == 422


def test_create_rejects_publishing_empty_content(bg):
    bg.login_admin()
    r = bg.client.post(BLOG, json={"title": "Empty", "content": "   ", "status": "published"})
    assert r.status_code == 422


def test_create_rejects_overlong_meta_fields(bg):
    bg.login_admin()
    assert bg.client.post(BLOG, json={
        "title": "T", "content": "<p>x</p>", "meta_title": "x" * 71,
    }).status_code == 422
    assert bg.client.post(BLOG, json={
        "title": "T", "content": "<p>x</p>", "meta_description": "x" * 161,
    }).status_code == 422


# =====================================================================
# PUT /blog/{id}  (update)
# =====================================================================
def test_update_publishing_a_draft_stamps_the_date(bg):
    bg.login_admin()
    row = bg.seed_post(slug="wip", status="draft", published_at=None)

    r = bg.client.put(f"{BLOG}/{row['id']}", json={"status": "published"})
    assert r.status_code == 200, r.text
    assert r.json()["post"]["published_at"] is not None


def test_update_preserves_the_original_publish_date(bg):
    """Editing a live post must not re-date it — that would churn the sitemap."""
    bg.login_admin()
    original = _iso(NOW - timedelta(days=30))
    row = bg.seed_post(slug="live", published_at=original)

    r = bg.client.put(f"{BLOG}/{row['id']}", json={"title": "Edited headline"})
    assert r.json()["post"]["published_at"] == original


def test_update_resanitises_edited_content(bg):
    bg.login_admin()
    row = bg.seed_post(slug="p")

    r = bg.client.put(f"{BLOG}/{row['id']}", json={
        "content": '<p>Clean</p><img src="x.jpg" alt="a" onerror="hack()">'
    })
    content = r.json()["post"]["content"]
    assert "onerror" not in content.lower()
    assert 'alt="a"' in content


def test_update_recomputes_reading_time(bg):
    bg.login_admin()
    row = bg.seed_post(slug="p", reading_minutes=1)

    r = bg.client.put(f"{BLOG}/{row['id']}", json={"content": "<p>" + "w " * 800 + "</p>"})
    assert r.json()["post"]["reading_minutes"] == 4


def test_update_deduplicates_a_colliding_new_slug(bg):
    bg.login_admin()
    bg.seed_post(slug="taken")
    row = bg.seed_post(slug="mine")

    r = bg.client.put(f"{BLOG}/{row['id']}", json={"slug": "taken"})
    assert r.json()["post"]["slug"] == "taken-2"


def test_update_keeping_its_own_slug_does_not_suffix_it(bg):
    bg.login_admin()
    row = bg.seed_post(slug="stable")

    r = bg.client.put(f"{BLOG}/{row['id']}", json={"slug": "stable", "title": "New title"})
    assert r.json()["post"]["slug"] == "stable"


def test_update_rejects_publishing_a_post_with_no_body(bg):
    """The row is already empty; the request only flips status."""
    bg.login_admin()
    row = bg.seed_post(slug="hollow", status="draft", published_at=None, content="")

    r = bg.client.put(f"{BLOG}/{row['id']}", json={"status": "published"})
    assert r.status_code == 400
    assert "empty content" in r.json()["message"]


def test_update_missing_post_404s(bg):
    bg.login_admin()
    assert bg.client.put(f"{BLOG}/{uuid.uuid4()}", json={"title": "x"}).status_code == 404


# =====================================================================
# DELETE /blog/{id}
# =====================================================================
def test_delete_archives_and_reserves_the_slug(bg):
    """Archiving keeps the row so an indexed URL can never be reused."""
    bg.login_admin()
    row = bg.seed_post(slug="retired")

    r = bg.client.delete(f"{BLOG}/{row['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["message"] == "Blog post archived"
    assert bg.rows()[0]["status"] == "archived"
    assert bg.rows()[0]["slug"] == "retired"          # slug still taken
    assert bg.client.get(f"{BLOG}/retired").status_code == 404
    assert bg.client.get(BLOG).json()["total"] == 0


def test_hard_delete_purges_the_row(bg):
    bg.login_admin()
    row = bg.seed_post(slug="gone")

    r = bg.client.delete(f"{BLOG}/{row['id']}", params={"hard": True})
    assert r.status_code == 200, r.text
    assert r.json()["message"] == "Blog post permanently deleted"
    assert bg.rows() == []


def test_delete_missing_post_404s(bg):
    bg.login_admin()
    assert bg.client.delete(f"{BLOG}/{uuid.uuid4()}").status_code == 404
