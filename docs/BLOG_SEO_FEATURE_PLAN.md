# Blog & SEO Feature Plan

**Status:** Phases 1-3 COMPLETE (backend, admin panel, website + SSR) — remote migration push still pending
**Created:** 2026-08-20
**Branch target:** `dev`
**Decisions locked:** Build in-house (no headless CMS / WordPress) · Server-render blog routes only

---

## 1. Why this exists

Client wants to publish keyword-targeted blog articles to drive organic search traffic to
Lubist. He supplies keywords, copy and images; he wants to publish them himself without a
developer pasting content into code.

Two independent problems:

| Problem | Answer |
| --- | --- |
| Where does he author posts? | Admin panel, WYSIWYG editor (TipTap) |
| Will the posts actually rank? | **No — not today.** Requires server rendering. See §2 |

### Where formatting lives

```
Admin panel editor  ->  HTML/JSON  ->  blog_posts.content  ->  Website <article>
   (authoring)         (the content)     (storage)             (presentation)
```

The editor emits sanitised HTML. The website styles it with one `prose` stylesheet.
Client controls words and structure; we control the design system. He cannot break the site.

---

## 2. The blocker: the web app is invisible to crawlers

`salon-management-app` is a Vite SPA. Current state:

- `vercel.json` rewrites **every** URL to `/`
- `index.html` carries **one hardcoded title and meta description for the whole site**
- No `react-helmet`, no prerender, no `sitemap.xml`, no `robots.txt`, no JSON-LD

What a crawler receives for any URL today:

```html
<title>Lubist - Beauty. Booking. Simplified.</title>
<meta name="description" content="Lubist is a modern beauty and wellness platform..." />
<div id="root"></div>   <!-- empty -->
```

Googlebot can execute JS but defers it to a second pass and is unreliable for new
low-authority domains. Bing, WhatsApp / LinkedIn / X link previews and most AI crawlers do
not execute JS at all.

**Decision:** server-render `/blog` and `/blog/:slug` only, via a Vercel serverless
function. Contained change, no migration of the existing app. Blog pages are read-only
documents — they do not need React.

> NOTE: `/salons/:id` and `/products/:slug` have the identical problem and are the actual
> revenue pages. Build the SSR helper generic so those can be added later without a
> rewrite. Explicitly deferred, not forgotten.
>
> DONE in Phase 3: `api/_lib/html.js` is free of blog specifics. Adding a page type is
> a renderer in `api/_lib/<thing>.js`, an entry in `ROUTES`, a rewrite, and a sitemap
> entry — see `salon-management-app/api/README.md`.

---

## 3. Data model

Migration: `supabase/migrations/2026XXXXXXXXXX_create_blog_posts_table.sql`

`blog_posts`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `slug` | varchar unique NOT NULL | URL segment, indexed |
| `title` | varchar NOT NULL | |
| `excerpt` | text | listing card summary |
| `content` | text NOT NULL | sanitised HTML from editor |
| `cover_image_url` | text | Cloudinary |
| `cover_image_alt` | varchar | required when cover set — SEO |
| `meta_title` | varchar(70) | falls back to `title` |
| `meta_description` | varchar(160) | falls back to `excerpt` |
| `focus_keyword` | varchar | client's target term |
| `tags` | text[] | |
| `author_name` | varchar | display only |
| `status` | varchar | `draft` / `published` / `scheduled` |
| `published_at` | timestamptz | drives sort + `scheduled` gate |
| `reading_minutes` | int | computed on save |
| `created_at` / `updated_at` | timestamptz | |
| `created_by` | uuid FK profiles | |

Indexes: unique on `slug`, composite `(status, published_at DESC)`, GIN on `tags`.
RLS: public read where `status = 'published' AND published_at <= now()`; writes admin-only.

---

## 4. Phase 1 — Backend (mirror the `banners` module exactly)

Files, following `app/api/banners.py` as the template:

- `supabase/migrations/…_create_blog_posts_table.sql`
- `app/schemas/request/blog.py` — `BlogPostCreate`, `BlogPostUpdate`
- `app/schemas/response/blog.py` — list / detail / operation responses
- `app/services/blog_service.py` — CRUD, slug generation + uniqueness, HTML sanitisation, reading-time calc
- `app/api/blog.py` — router
- `main.py` — `app.include_router(blog.router, prefix=settings.API_PREFIX)`

Endpoints (static segments before `/{slug}` — same trap called out in `banners.py`):

```
GET    /blog                  public   paginated published list (tag / search filters)
GET    /blog/sitemap-data     public   slug + updated_at feed for sitemap.xml
GET    /blog/admin/all        admin    all posts incl. drafts
POST   /blog                  admin    create
GET    /blog/admin/{id}       admin    fetch draft for editing
PUT    /blog/{id}             admin    update
DELETE /blog/{id}             admin    soft delete
GET    /blog/{slug}           public   single published post   <-- LAST
```

**Sanitise `content` server-side** (`bleach` or `nh3`) with a tag allowlist. The editor
already restricts input but the API must not trust it — stored HTML is injected directly
into a server-rendered page.

Images reuse the existing `CloudinaryService` / `app/api/upload.py`. No new upload path.

---

## 5. Phase 2 — Admin panel (BUILT)

Files, following `pages/Banners.jsx` + `services/api/bannerApi.js`:

- `src/services/api/blogApi.js`
- `src/pages/Blog.jsx` — list: title, status pill, published date, keyword, actions
- `src/pages/BlogEditor.jsx` — the editor screen
- `src/components/blog/RichTextEditor.jsx` — TipTap wrapper
- Sidebar entry + route in `App.jsx`

Editor screen — **three tabs**. This is what the client means by "control":

1. **Write** — TipTap. H2/H3, bold/italic, lists, links, blockquote, image insert
   (uploads to Cloudinary, **alt text field required**), code block.
2. **Preview** — renders the post in the real website `prose` styles. This is the
   "preview editor" experience he described; it does not need to live in the website repo.
3. **SEO** — explicit fields, not guessed: slug (editable, warns on change if already
   published), focus keyword, meta title with 70-char counter, meta description with
   160-char counter, cover image + alt, tags, and a live Google-result preview snippet.

Publish controls: Save draft · Schedule · Publish. Autosave drafts.

TipTap deps: `@tiptap/react @tiptap/starter-kit @tiptap/extension-link @tiptap/extension-image`

---

## 6. Phase 3 — Website + server rendering

**React side** (`salon-management-app`):

- `src/pages/public/Blog.jsx` — index, cards, tag filter, pagination
- `src/pages/public/BlogPost.jsx` — article
- `src/services/blogApi.js`
- `src/index.css` — `.prose` typography block (the single place formatting is defined)
- Routes `/blog`, `/blog/:slug` in `App.jsx`; footer + nav links

**SSR side** — the part that makes it rank:

- `api/render.js` — Vercel serverless function. Given a blog path, fetches the post from
  the backend and returns a **complete HTML document**: real `<title>`, meta description,
  canonical, `og:*` / `twitter:*`, `BlogPosting` JSON-LD, and the full article body in the
  markup.
- `vercel.json` — route `/blog` and `/blog/:slug` to the function **before** the catch-all
  SPA rewrite. Everything else keeps working exactly as today.
- `api/sitemap.js` — `sitemap.xml` built from `/blog/sitemap-data` plus static pages.
- `public/robots.txt` — allow all, point at the sitemap.

Cache the function response (`s-maxage`) so it is not hitting the API on every crawl.

---

## 7. What the client must provide

- Target keyword list, one per planned article
- Article copy (title, body, section headings)
- Images, each with a caption / alt line
- Preferred author name / byline

**Tell him:** the blog's job is to capture *informational* searches ("how often should I
get a hair spa", "bridal makeup cost in Delhi") and then **link internally into `/salons`
and `/products`**. Articles that don't link to the money pages don't transfer SEO value.
Agree this before he starts writing.

---

## 8. Deferred (deliberately)

- SSR for `/salons/:id` and `/products/:slug` — bigger SEO win, separate task
- Full Next.js migration
- Comments, reactions, newsletter capture
- Multi-author / editorial roles
- Category taxonomy beyond flat `tags`

---

## 9. Checklist

### Backend — COMPLETE except the migration push
- [x] Migration written — `supabase/migrations/20260820000000_create_blog_posts_table.sql`
- [x] **Migration applied to LOCAL** via `npx supabase migration up --local`. This also
      applied two migrations that had been sitting unapplied: `20260701000000`
      (partner_requests) and `20260801000000` (salon pincode alignment).
- [ ] **Migration pushed to REMOTE** (`supabase db push`) — still outstanding. The same
      three migrations will go up together; the pincode one fixes the salon-approval bug.
- [x] Request / response schemas — `app/schemas/request/blog.py`, `app/schemas/response/blog.py`
- [x] `blog_service.py` — HTML sanitisation (nh3), slug uniqueness, reading time, excerpt fallback
- [x] `app/api/blog.py` router — 9 routes, static segments verified ahead of `/{slug}`
- [x] Wired in `main.py`
- [x] Image upload — `POST /upload/cloudinary-blog-image` (folder `blog`)
- [x] `nh3==0.2.20` added to `requirements.txt` and installed
- [x] Tests — `tests/test_blog_mocked.py` (40) + `tests/test_integration_blog.py` (13).
      Full suite: 620 passed with the stack up, 594 in the fast CI job.

**Design decisions made during Phase 1** (differ slightly from the original sketch):
- No `scheduled` status. Statuses are `draft` / `published` / `archived`; scheduling is
  a `published` post with a future `published_at`. Every public read filters
  `status='published' AND published_at <= now()`, so posts go live with no cron job.
- Soft delete archives rather than removing the row, which keeps the slug reserved so an
  already-indexed URL can never be reused by a different article.
- Added `GET /blog/tags` (index filter bar) and `related_posts` on the detail response
  (the "read next" block that carries readers toward the salon pages).

**Two bugs the mocked tests could not catch** (found by running against the real stack —
this is why `test_integration_blog.py` exists and should not be deleted):
- `postgrest 0.13.2` (pinned by `supabase 2.0.3`) has **no `.or_()`** method. Every search
  query raised AttributeError and 500'd. Now built via `query.params.add("or", ...)` with
  `*` wildcards, which is the URL form of the operator.
- The array-overlap operator is **`.ov()`, not `.overlaps()`**. Related-posts threw, and
  because that failure is deliberately swallowed to protect the article page, the feature
  would have silently returned an empty list forever. The integration test asserts a
  NON-EMPTY result so an empty list can never pass vacuously again.
- Also fixed: punctuation-stripping in search left double spaces that matched nothing.

Search is plain substring ILIKE on the cleaned phrase — "hair spa" finds
"Best Hair Spa in Delhi", "hair delhi" does not. Fine at blog scale; swap in postgrest's
`plfts` if the archive grows enough to need ranked full-text search.

### Admin panel — COMPLETE
- [x] `src/services/api/blogApi.js` — 7 endpoints, wired into `store.js` (reducer,
      middleware, and the persist blacklist so posts are never served stale)
- [x] `src/pages/Blog.jsx` — list with status/search filters, server-side pagination,
      archive + restore-to-draft
- [x] `src/components/blog/RichTextEditor.jsx` — TipTap 3 wrapper
- [x] Preview tab using the real prose styles
- [x] SEO tab with counters + SERP preview + SEO checks
- [x] Image upload with required alt text (cover **and** in-article)
- [x] Sidebar entry + routes `/blog`, `/blog/new`, `/blog/:postId/edit`
- [x] Tests — 51 new (`blogApi` 10, `Blog` page 13, `BlogEditor` 21, utils 18 minus
      overlap). Full admin suite: **117 passed**, lint clean, production build green.

**Design decisions made during Phase 2:**
- **TipTap 3.30**, not 2.x — v2 does not declare React 19 support. In v3 `StarterKit`
  already bundles `Link` and `Underline`, so they are configured through
  `StarterKit.configure({ link: {…} })` rather than installed separately, and
  `Placeholder` now comes from `@tiptap/extensions`. `useEditor` no longer re-renders
  on every transaction, so toolbar active-state is read via `useEditorState`.
- **Autosave applies to drafts only.** A published post is a page already sitting in
  search results; it changes only when the author clicks Update. New posts don't
  autosave either — the first save has to be deliberate or a stray keystroke creates rows.
- **The article body starts at h2.** The page shell owns the single h1 (the title), so
  the editor offers H2/H3/H4 only.
- **`prose.css` lives in `src/components/blog/` and is the canonical stylesheet.**
  Phase 3 copies it into the website verbatim; the file says so at the top. If the two
  drift, the Preview tab stops being a preview. It is plain CSS with no Tailwind
  directives specifically so it can be dropped into the other repo unchanged.
- **Scheduling reuses the existing model** — status `published` + a future
  `published_at`. `describeStatus()` (`src/utils/blogStatus.js`) derives the
  "Scheduled" label for display; nothing new is stored.
- Slug changes on an already-published post require an explicit confirm naming both the
  old and new URL, since the old one is what search engines have indexed.

**Two things fixed along the way (outside the blog module):**
- `src/components/common/FormElements.jsx` — `Input` / `Select` / `Textarea` rendered a
  `<label>` with no `htmlFor`, so every labelled field in the admin panel was announced
  as unlabelled and clicking a label didn't focus its input. They now generate an id via
  `useId()` and associate the label. Verified against the full suite (117 passed).
- `Sidebar.isActive` matched the path exactly, so `/blog/new` and `/blog/:id/edit` would
  have left the nav with nothing highlighted. It now also matches sub-paths.

**Known cost:** the `BlogEditor` chunk is 431 kB (134 kB gzip) because ProseMirror ships
with TipTap. It is lazy-loaded and admin-only, and the `Blog` list chunk stays at 4.7 kB.

### Website + SSR (Phase 3) — COMPLETE, not yet deployed
All in `salon-management-app`.

**React side** (the in-SPA click-through render)
- [x] `src/components/blog/prose.css` — verbatim copy of the admin panel's; `diff` is clean
- [x] `src/services/api/blogApi.js` — 3 public endpoints, registered in `store/index.js`
- [x] `src/components/blog/BlogPostCard.jsx` — shared by the index grid and "Read next"
- [x] `src/pages/public/Blog.jsx` — tag filter + pagination, both driven by the query string
- [x] `src/pages/public/BlogPost.jsx` — article, related posts, CTA into /salons and /products
- [x] `src/hooks/useDocumentMeta.js` — tab title during in-app navigation (explicitly NOT SEO)
- [x] Routes `/blog` and `/blog/:slug` in `App.jsx`; footer link + navbar "More" dropdown entry

**SSR side** (what actually ranks)
- [x] `api/render.js` — dispatcher; owns status codes and cache headers
- [x] `api/_lib/html.js` — page-agnostic document shell, escaping, JSON-LD, chrome
- [x] `api/_lib/blog.js` — blog markup and structured data
- [x] `api/_lib/http.js`, `_lib/config.js`, `_lib/prose.js`
- [x] `vercel.json` — /sitemap.xml, /blog, /blog/:slug routed ahead of the SPA catch-all
- [x] `api/sitemap.js` — static pages + every live post, built per request
- [x] `public/robots.txt` — allows all public pages, blocks auth/checkout, points at the sitemap
- [x] `api/README.md` — routing rule, how to add a page type, the curl checks
- [x] Tests — 54 SSR (`api/**`) + 34 React (blogApi 8, Blog 13, BlogPost 13).
      Full web suite: **226 passed**, production build green, new files lint clean.
- [x] Verified end-to-end against the running local backend and a real published
      post: title, description, canonical, og/twitter, 2 valid JSON-LD blocks,
      exactly one h1, article body in the markup, 404 for a bad slug, sitemap 200.

**Still to do (needs a deploy / access I do not have)**
- [ ] Set `SITE_URL=https://www.lubist.com` on the Vercel project
- [ ] Deploy and re-run the `curl` checks in `api/README.md` against production
- [ ] Google Search Console: submit sitemap, request indexing

**Design decisions made during Phase 3:**
- **The route type is passed by the rewrite, not parsed from the URL.** `vercel.json`
  sends `?type=blog-index` / `?type=blog-post&slug=:slug`, which keeps the mapping
  declarative in one file. Vercel merges the visitor's query string into the
  rewrite's, so `/blog?type=blog-post&slug=x` arrives with two `type` values and
  no defined winner — a duplicate `type` or `slug` is therefore rejected as
  malformed (400). `tag` and `page` are the visitor's, so duplicates take the first.
- **404 and 503 are never confused.** `_lib/http.js` returns `notFound` only for a
  real 404; anything else (timeout, 5xx, DNS) becomes 503 + `no-store`. Answering
  404 during an API blip would tell crawlers that live, ranking articles were
  removed. Same reason `sitemap.xml` 503s rather than publishing a sitemap that
  silently omits every post.
- **`?page=1` does not exist.** `indexPath()` omits defaults, so each list has
  exactly one URL rather than two that are duplicate content. Paginated pages are
  linked with `rel=prev/next`.
- **Error, empty and notice pages are `noindex, follow`.**
- **prose.css now has three copies**, unavoidably: the admin panel (canonical),
  `src/components/blog/prose.css` (verbatim, imported by the SPA), and
  `api/_lib/prose.js` (the same CSS as a string, because a server-rendered
  document cannot import a stylesheet). `api/_lib/prose.test.js` pins copy 3 to
  copy 2. Copy 1 vs 2 crosses a repo boundary — `diff` them by hand.
- **`api/` is CommonJS.** `package.json` has no `"type": "module"`, and adding one
  would change how Vite, PostCSS and Tailwind load their configs. `eslint.config.js`
  gained an `api/**/*.js` block for the Node globals; `vitest.config.js` gained
  `api/**/*.{test,spec}.js` so the functions are covered by `npm test`.
- **The sitemap lists only server-rendered pages.** `/salons/:id` and
  `/products/:slug` are deliberately absent: a sitemap URL that resolves to an
  empty SPA shell invites a crawl and gives it nothing. They go in when they get
  a renderer.
- **`SITE_URL` falls back to the hardcoded production domain, not `VERCEL_URL`.**
  VERCEL_URL is a per-deployment hostname; if the env var were ever missing,
  every canonical would point at a throwaway domain.

**Two content notes for the client (not code):**
- The one published post has no `cover_image_url` — the image is inside the body
  instead. That means no `og:image`, so the link unfurls on WhatsApp/LinkedIn as a
  small text card. Set a cover image on every post.
- That post also repeats its title as the first line of the body and uses `h3`
  for running text. Neither breaks the page (the shell owns the single h1), but
  the body should start at `h2` and not repeat the title.
