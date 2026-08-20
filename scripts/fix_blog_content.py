"""
One-off repair for blog posts written before the editor normalised pasted HTML.

WHY
Posts authored by pasting from Google Docs / Word / ChatGPT stored the SOURCE
document's block structure: a whole intro paragraph wrapped in <h3>, paragraph
breaks as <br><br> inside a single block, headings bolted into <strong>. The
sanitiser stripped the style attributes but kept the tags, so prose.css renders
those blocks in the heading face and the article comes out in three different
fonts.

New pastes are fixed at the source in
`salon-admin-panel/src/utils/pastedHtml.js`. This script applies the same rules
to what is already in the database.

The two judgement calls below — "a heading this long is a paragraph" and
"<br><br> means a new paragraph" — deliberately do NOT live in blog_service:
rewriting an author's structure silently on every save is not something the API
should do. Here they are a one-time, reviewed migration.

USAGE
    python scripts/fix_blog_content.py                  # dry run, prints a diff
    python scripts/fix_blog_content.py --apply          # write the changes
    python scripts/fix_blog_content.py --slug my-post   # limit to one post
"""
import argparse
import os
import re
import sys
from difflib import unified_diff

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from app.services.blog_service import (  # noqa: E402
    _normalize_structure,
    _sanitize_html,
    _strip_html,
)

# Same threshold as pastedHtml.MAX_HEADING_CHARS. A heading is a label; anything
# this long is body copy the author styled by accident.
MAX_HEADING_CHARS = 120

_BR_RUN = r"(?:<br\s*/?>\s*)"


def _split_block(tag: str, inner: str, min_run: int) -> str:
    """Split one block's inner HTML on <br> runs into sibling blocks."""
    parts = re.split(_BR_RUN + ("{%d,}" % min_run), inner)
    kept = [p for p in parts if _strip_html(p).strip() or "<img" in p]
    if len(kept) < 2:
        return f"<{tag}>{inner}</{tag}>"
    return "".join(f"<{tag}>{p}</{tag}>" for p in kept)


def _split_headings(html: str) -> str:
    """A heading is one line, so any <br> inside it starts a new block."""
    return re.sub(
        r"<(h[234])>(.*?)</\1>",
        lambda m: _split_block(m.group(1), m.group(2), 1),
        html,
        flags=re.S,
    )


def _split_paragraphs(html: str) -> str:
    """<br><br> is how a paste spells a paragraph break. Make it a real one."""
    return re.sub(
        r"<p>(.*?)</p>",
        lambda m: _split_block("p", m.group(1), 2),
        html,
        flags=re.S,
    )


def _demote_long_headings(html: str) -> str:
    """A heading holding a paragraph's worth of text is a paragraph."""

    def repl(m):
        inner = m.group(2)
        if len(_strip_html(inner).strip()) > MAX_HEADING_CHARS:
            return f"<p>{inner}</p>"
        return m.group(0)

    return re.sub(r"<(h[234])>(.*?)</\1>", repl, html, flags=re.S)


def repair(html: str) -> str:
    """Full repair pass — the server-side twin of normalizePastedHtml."""
    if not html:
        return ""
    out = _sanitize_html(html)      # tightened allowlist: unwraps span/div, drops class
    out = _split_headings(out)
    out = _split_paragraphs(out)
    out = _demote_long_headings(out)
    return _normalize_structure(out)


def _blocks(html: str):
    """Readable one-block-per-line form, so the diff is legible."""
    return [b for b in re.split(r"(?<=>)(?=<(?:p|h[234]|ul|ol|blockquote|img|hr|figure)\b)", html) if b]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the changes back")
    parser.add_argument("--slug", help="repair a single post")
    args = parser.parse_args()

    from supabase import create_client

    db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

    query = db.table("blog_posts").select("id,slug,title,status,content")
    if args.slug:
        query = query.eq("slug", args.slug)
    posts = query.execute().data or []

    if not posts:
        print("No posts found.")
        return 0

    changed = 0
    for post in posts:
        before = post.get("content") or ""
        after = repair(before)
        if before == after:
            print(f"  ok      {post['slug']}")
            continue

        changed += 1
        print(f"\n=== {post['slug']} ({post['status']}) ===")
        for line in unified_diff(_blocks(before), _blocks(after), "stored", "repaired", lineterm="", n=1):
            print(line[:300])

        # Reported, never auto-removed: whether the body should repeat the title
        # or lead with the cover image is the author's call, not the script's.
        first = _blocks(after)[0] if _blocks(after) else ""
        if _strip_html(first).strip().lower() == (post["title"] or "").strip().lower():
            print(f"  NOTE: the body opens by repeating the post title — remove it in the editor.")
        if before.lstrip().startswith("<img"):
            print(f"  NOTE: the body opens with an image; the cover image is a separate field.")

        if args.apply:
            db.table("blog_posts").update({"content": after}).eq("id", post["id"]).execute()
            print("  APPLIED")

    print(f"\n{changed} of {len(posts)} post(s) need repair.")
    if changed and not args.apply:
        print("Dry run — re-run with --apply to write these changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
