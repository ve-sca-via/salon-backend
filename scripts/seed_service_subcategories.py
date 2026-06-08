"""
Seed service subcategories (level 2) and sub-subcategories (level 3)
via the admin API, so the 3-level taxonomy is visible in the vendor flow.

Run AFTER seed_service_categories.py (needs the level-1 categories to exist)
and AFTER applying migration 20260608000000_add_subcategory_nesting.sql.

Idempotent: existing nodes (matched case-insensitively by name within the
same parent) are reused instead of duplicated.
"""
import json
import subprocess
import sys

BASE_URL = "http://localhost:8000/api/v1"


def _curl(method, path, token=None, body=None):
    """Minimal HTTP via curl (the requests lib hangs against this dev server)."""
    cmd = ["curl", "-s", "-X", method, f"{BASE_URL}{path}", "-H", "Content-Type: application/json"]
    if token:
        cmd += ["-H", f"Authorization: Bearer {token}"]
    if body is not None:
        cmd += ["-d", json.dumps(body)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
    if not out:
        raise RuntimeError("empty response (is the backend running on :8000?)")
    return json.loads(out)

ADMIN_EMAIL = "787alisniazi787@gmail.com"
ADMIN_PASSWORD = "Safdar@1234"

# category name -> { subcategory name -> [sub-subcategory names] }
# Keyed to the category that exists in this DB ("Hair"). The existing "Haircut"
# subcategory is reused; only the level-3 nodes below it are new.
TAXONOMY = {
    "Hair": {
        "Haircut": ["Spanish Haircut", "Layer Cut", "Fade"],
        "Hair Color": ["Global Color", "Highlights", "Balayage"],
        "Hair Treatment": ["Keratin", "Smoothening"],
    },
}


def login():
    data = _curl("POST", "/auth/login", body={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    token = data.get("access_token")
    if not token:
        print(f"[FATAL] Admin login failed: {data}")
        sys.exit(1)
    return token


def get_categories(token):
    data = _curl("GET", "/admin/service-categories?limit=100", token=token)
    return {c["name"].strip().lower(): c for c in data.get("data", [])}


def get_subcategories(token, category_id):
    data = _curl("GET", f"/admin/service-categories/{category_id}/subcategories", token=token)
    return data.get("data", [])


def create_subcategory(token, category_id, name, parent_subcategory_id=None):
    payload = {"name": name, "is_active": True}
    if parent_subcategory_id:
        payload["parent_subcategory_id"] = parent_subcategory_id
    data = _curl("POST", f"/admin/service-categories/{category_id}/subcategories", token=token, body=payload)
    if not data.get("success"):
        raise RuntimeError(str(data))
    return data["data"]


def ensure_node(token, category_id, existing, name, parent_subcategory_id=None):
    """Find (case-insensitive, same parent) or create a subcategory node. Returns its id."""
    target = name.strip().lower()
    for row in existing:
        if (row.get("name") or "").strip().lower() == target and \
           (row.get("parent_subcategory_id") or None) == (parent_subcategory_id or None):
            return row["id"], False
    created = create_subcategory(token, category_id, name, parent_subcategory_id)
    existing.append(created)
    return created["id"], True


def main():
    print("Seeding subcategories + sub-subcategories...\n")
    token = login()

    categories = get_categories(token)
    if not categories:
        print("[FATAL] No level-1 categories found. Run seed_service_categories.py first.")
        sys.exit(1)

    created_l2 = created_l3 = 0
    for cat_name, subs in TAXONOMY.items():
        cat = categories.get(cat_name.strip().lower())
        if not cat:
            print(f"[skip] Category not found: {cat_name}")
            continue
        cat_id = cat["id"]
        existing = get_subcategories(token, cat_id)
        print(f"Category: {cat_name}")

        for sub_name, sub_subs in subs.items():
            try:
                sub_id, is_new = ensure_node(token, cat_id, existing, sub_name)
            except RuntimeError as e:
                print(f"  [ERROR] creating subcategory '{sub_name}': {e}")
                if "parent_subcategory_id" in str(e):
                    print("  >>> Looks like migration 20260608000000_add_subcategory_nesting.sql "
                          "is NOT applied. Apply it and re-run.")
                    sys.exit(1)
                continue
            created_l2 += int(is_new)
            print(f"  - {sub_name} {'(new)' if is_new else '(exists)'}")

            for ss_name in sub_subs:
                try:
                    _, ss_new = ensure_node(token, cat_id, existing, ss_name, parent_subcategory_id=sub_id)
                    created_l3 += int(ss_new)
                    print(f"      • {ss_name} {'(new)' if ss_new else '(exists)'}")
                except RuntimeError as e:
                    print(f"      [ERROR] creating sub-subcategory '{ss_name}': {e}")

    print(f"\nDone. Created {created_l2} subcategories and {created_l3} sub-subcategories "
          f"(existing nodes were reused).")


if __name__ == "__main__":
    main()
