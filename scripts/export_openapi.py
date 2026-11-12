"""
Export the backend's OpenAPI contract to openapi/openapi.json.

Why this exists: production and staging run with `openapi_url=None`, so the
contract can't be fetched from a deployed server. Instead we build it straight
from the code and commit the result. That committed file is:

  * the single source the mobile apps generate their TypeScript types from
    (`npm run api:types` in lubist_mobile_application / lubist_vendor_application);
  * a reviewable diff — any PR that changes a request/response shape shows up
    as a change to openapi/openapi.json;
  * checked in CI (`--check`) so it can't silently go stale.

Usage (from backend/, venv active):
    python scripts/export_openapi.py            # write openapi/openapi.json
    python scripts/export_openapi.py --check    # exit 1 if the file is stale
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Settings() has ~50 required env vars. Building the schema needs none of their
# real values, so borrow the dummy test config (same trick as tests/conftest.py).
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "tests" / "test.env", override=True)
# Keep the committed contract independent of whatever prefix a local .env uses:
# every deployed environment (prod + staging) serves the API under /api/v1.
os.environ["API_PREFIX"] = "/api/v1"

from fastapi.openapi.utils import get_openapi  # noqa: E402

import main  # noqa: E402

OUT = ROOT / "openapi" / "openapi.json"


def build() -> str:
    app = main.app
    schema = get_openapi(
        title="Lubist API",
        version=app.version or "0",
        routes=app.routes,
    )
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def run() -> int:
    content = build()
    if "--check" in sys.argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != content:
            print(
                "openapi/openapi.json is stale. Run `python scripts/export_openapi.py` "
                "and commit the result.",
                file=sys.stderr,
            )
            return 1
        print("openapi/openapi.json is up to date.")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(content, encoding="utf-8", newline="\n")
    paths = json.loads(content)["paths"]
    print(f"Wrote {OUT.relative_to(ROOT)} ({len(paths)} paths).")
    return 0


if __name__ == "__main__":
    sys.exit(run())
