"""
End-to-end REGULAR BUYER seeder: request -> approve -> buyer account -> activate.

A "regular buyer" is a salon/shop owner who buys products from us at wholesale
(B2B) prices but does NOT list a bookable salon publicly. See
docs/REGULAR_BUYER_WORKFLOW.md for the full explanation.

This mirrors scripts/seed_full_salon.py but drives the regular_buyer path:
  1. RM submits a join request with request_type = "regular_buyer"  (API)
  2. Admin approves it  -> salon row with salon_type = "regular_buyer" (API)
  3. Create the buyer auth account (user_role = regular_buyer)        (service-role DB)
  4. Mark registration paid + activate                                (service-role DB)

The result is a fully-activated regular buyer you can log in as to test B2B
product buying. Unlike a normal salon, this account is hidden from public salon
discovery and has no services.

Steps 1-2 use the HTTP API (so it is built exactly like production). Steps 3-4
use the Supabase service-role client because the real paths (emailed
registration token + Razorpay registration payment) can't be driven from a seed.

Usage (backend running, venv active):
    python scripts/seed_regular_buyer.py
    python scripts/seed_regular_buyer.py --request-id <existing_pending_request_id>
    python scripts/seed_regular_buyer.py --salon-id  <already_approved_salon_id>
"""

import argparse
import os
import random
import sys
import time
from datetime import datetime, timezone

import requests

# Allow `from app...` imports when run as `python scripts/seed_regular_buyer.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from supabase import create_client

DEFAULT_BASE_URL = "http://localhost:8000/api/v1"

RM_EMAIL = "saf2@gmail.com"                 # role = relationship_manager
RM_PASSWORD = "Safdar@1234"
ADMIN_EMAIL = "787alisniazi787@gmail.com"   # role = admin
ADMIN_PASSWORD = "Safdar@1234"

BUYER_PASSWORD = "Buyer@1234"               # password for the seeded buyer account

# --- Randomization pools ----------------------------------------------------
# Regular buyers are shops/parlours that stock our products, not service salons.
SHOP_TYPES = ["salon", "spa", "beauty_parlor", "unisex_salon", "barber_shop"]

NAME_PREFIX = [
    "Bloom", "Luxe", "Glow", "Velvet", "Aura", "Opal", "Serene", "Gloss",
    "Vogue", "Halo", "Posh", "Bliss", "Radiance", "Lush", "Mirage", "Ivory",
]
NAME_SUFFIX = [
    "Beauty Store", "Cosmetics Depot", "Salon Supplies", "Trading Co",
    "Beauty Mart", "Wholesale Beauty", "Retail Store", "Enterprises",
]
OWNER_NAMES = [
    "Rhea Kapoor", "Aarav Mehta", "Sana Sheikh", "Vikram Rao", "Neha Verma",
    "Imran Khan", "Pooja Nair", "Karan Singh", "Diya Iyer", "Rohan Das",
]

# Real Indian cities with representative coords/pincode.
CITIES = [
    {"city": "Bengaluru", "state": "Karnataka", "pincode": "560001", "lat": 12.9716, "lon": 77.5946, "area": "MG Road"},
    {"city": "Mumbai", "state": "Maharashtra", "pincode": "400050", "lat": 19.0596, "lon": 72.8295, "area": "Bandra West"},
    {"city": "Delhi", "state": "Delhi", "pincode": "110001", "lat": 28.6315, "lon": 77.2167, "area": "Connaught Place"},
    {"city": "Hyderabad", "state": "Telangana", "pincode": "500034", "lat": 17.4126, "lon": 78.4490, "area": "Banjara Hills"},
    {"city": "Pune", "state": "Maharashtra", "pincode": "411001", "lat": 18.5362, "lon": 73.8939, "area": "Koregaon Park"},
]

# Unsplash photo IDs (shop / beauty). Sizes applied per use.
UNSPLASH_IDS = [
    "1560066984-138dadb4c035", "1570172619644-dfd03ed5d881", "1604654894610-df63bc536371",
    "1521590832167-7bcbfaa6381f", "1599351431202-1e0f0137899a", "1503951914875-452162b0f3f1",
]


def unsplash(photo_id: str, width: int) -> str:
    return f"https://images.unsplash.com/photo-{photo_id}?w={width}&q=80"


def die(msg: str, resp=None):
    print(f"[FAIL] {msg}")
    if resp is not None:
        print(f"       Response: {resp}")
    sys.exit(1)


def login(base_url: str, email: str, password: str) -> str:
    try:
        r = requests.post(f"{base_url}/auth/login", json={"email": email, "password": password})
        r.raise_for_status()
        return r.json()["access_token"]
    except requests.exceptions.RequestException as exc:
        die(f"login failed for {email}: {exc}", getattr(getattr(exc, "response", None), "text", None))


def build_request_payload() -> dict:
    """Build a regular_buyer join-request payload.

    Regular buyers use the shortened flow (no services, no business hours), but
    the API accepts the same schema as a salon request — we simply set
    request_type = "regular_buyer" and omit service-specific fields.
    """
    suffix = int(time.time())
    name = f"{random.choice(NAME_PREFIX)} {random.choice(NAME_SUFFIX)}"
    owner = random.choice(OWNER_NAMES)
    loc = random.choice(CITIES)
    btype = random.choice(SHOP_TYPES)
    phone = random.choice("6789") + "".join(random.choices("0123456789", k=9))

    # Valid GSTIN/PAN with random (collision-resistant) values.
    letters = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=5))
    digits = "".join(random.choices("0123456789", k=4))
    pan = f"{letters}{digits}F"
    gst = f"29{pan}1Z5"

    slug = "".join(ch for ch in name.lower() if ch.isalnum())[:12]
    lat = round(loc["lat"] + random.uniform(-0.03, 0.03), 6)
    lon = round(loc["lon"] + random.uniform(-0.03, 0.03), 6)
    house = random.randint(1, 200)

    return {
        "business_name": name,
        "business_type": btype,
        "owner_name": owner,
        # Distinct owner email is REQUIRED: if owner_email == RM email the approval
        # flow intentionally skips the registration email (see workflow doc §5.1).
        "owner_email": f"{slug}.{suffix}@example.com",
        "owner_phone": phone,
        "business_address": f"{house} {loc['area']}, {loc['city']}",
        "city": loc["city"],
        "state": loc["state"],
        "pincode": loc["pincode"],
        "latitude": lat,
        "longitude": lon,
        "outlet": random.choice(["Company owned", "franchisee"]),
        "is_gst": True,
        "gst_number": gst,
        "pan_number": pan,
        "cover_image_url": unsplash(random.choice(UNSPLASH_IDS), 1200),
        "gallery_images": [unsplash(pid, 800) for pid in random.sample(UNSPLASH_IDS, 3)],
        # The one field that makes this a regular buyer instead of a salon:
        "request_type": "regular_buyer",
        "documents": {
            "logo": unsplash(random.choice(UNSPLASH_IDS), 400),
            "description": (
                f"{name} is a beauty/salon products retailer in {loc['city']} that buys "
                f"stock from us at wholesale (B2B) prices. Not a bookable salon."
            ),
        },
    }


def create_request(base_url: str, rm_token: str) -> str:
    headers = {"Authorization": f"Bearer {rm_token}"}
    try:
        r = requests.post(
            f"{base_url}/rm/vendor-requests",
            params={"is_draft": "false"},
            json=build_request_payload(),
            headers=headers,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("id") or data.get("request", {}).get("id")
    except requests.exceptions.RequestException as exc:
        die(f"create request failed: {exc}", getattr(getattr(exc, "response", None), "text", None))


def approve_request(base_url: str, admin_token: str, request_id: str) -> str:
    headers = {"Authorization": f"Bearer {admin_token}"}
    try:
        r = requests.post(
            f"{base_url}/admin/vendor-requests/{request_id}/approve",
            json={"admin_notes": "Seeded regular-buyer approval"},
            headers=headers,
        )
        r.raise_for_status()
        return r.json().get("data", {}).get("salon_id")
    except requests.exceptions.RequestException as exc:
        die(f"approve failed: {exc}", getattr(getattr(exc, "response", None), "text", None))


def create_buyer_account(db, salon: dict) -> str | None:
    """Create (or reuse) a regular_buyer auth user + profile and return its id."""
    email = salon.get("email")
    name = f"{salon.get('business_name', 'Shop')} Owner"
    if not email:
        print("  [skip] salon has no email; leaving vendor_id unset")
        return None

    existing = db.table("profiles").select("id").eq("email", email).execute()
    if existing.data:
        buyer_id = existing.data[0]["id"]
        print(f"  buyer profile already exists ({email})")
    else:
        try:
            res = db.auth.admin.create_user(
                {"email": email, "password": BUYER_PASSWORD, "email_confirm": True}
            )
            buyer_id = res.user.id
            print(f"  created buyer auth user ({email}) / password: {BUYER_PASSWORD}")
        except Exception:  # noqa: BLE001 — likely already exists; look it up
            buyer_id = None
            try:
                for u in db.auth.admin.list_users():
                    if getattr(u, "email", None) == email:
                        buyer_id = u.id
                        break
            except Exception as exc:  # noqa: BLE001
                print(f"  [warn] could not resolve auth user: {str(exc)[:150]}")
            if not buyer_id:
                print("  [warn] buyer auth user could not be created/found; skipping link")
                return None

    # Ensure a profile row exists with the regular_buyer role (this is what makes
    # the product APIs return B2B/wholesale pricing for this account).
    db.table("profiles").upsert(
        {
            "id": buyer_id,
            "email": email,
            "full_name": name,
            "user_role": "regular_buyer",
            "phone": salon.get("phone"),
            "age": 35,
            "gender": "male",
            "is_active": True,
        }
    ).execute()
    return buyer_id


def activate_regular_buyer(db, salon_id: str, buyer_id: str | None):
    """Mark registration paid + activate, and ensure salon_type is regular_buyer.

    A regular_buyer salon stays hidden from public discovery (salon_type gate in
    app/api/salons.py) — activation just lets the owner log in and buy products.
    """
    update = {
        "salon_type": "regular_buyer",
        "is_active": True,
        "is_verified": True,
        "registration_fee_paid": True,
        "accepting_bookings": False,   # regular buyers don't take bookings
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }
    if buyer_id:
        update["vendor_id"] = buyer_id
    db.table("salons").update(update).eq("id", salon_id).execute()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a fully-activated regular buyer end-to-end.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--request-id", help="Approve an existing pending request instead of creating one")
    parser.add_argument("--salon-id", help="Finalize an already-approved regular-buyer salon (skip request + approval)")
    parser.add_argument("--rm-email", default=RM_EMAIL)
    parser.add_argument("--rm-password", default=RM_PASSWORD)
    parser.add_argument("--admin-email", default=ADMIN_EMAIL)
    parser.add_argument("--admin-password", default=ADMIN_PASSWORD)
    args = parser.parse_args()

    db = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

    if args.salon_id:
        salon_id = args.salon_id
        print(f"1-2) Using existing approved salon {salon_id}")
    else:
        # 1. Create the request (unless reusing one)
        request_id = args.request_id
        if not request_id:
            print("1) Submitting regular-buyer join request as RM ...")
            rm_token = login(args.base_url, args.rm_email, args.rm_password)
            request_id = create_request(args.base_url, rm_token)
            print(f"   -> request {request_id}")
        else:
            print(f"1) Using existing request {request_id}")

        # 2. Approve as admin
        print("2) Approving request as admin ...")
        admin_token = login(args.base_url, args.admin_email, args.admin_password)
        salon_id = approve_request(args.base_url, admin_token, request_id)
        if not salon_id:
            # Fallback: find the salon linked to this request
            found = db.table("salons").select("id").eq("join_request_id", request_id).execute()
            salon_id = found.data[0]["id"] if found.data else None
        if not salon_id:
            die("approval did not yield a salon_id")
        print(f"   -> salon {salon_id}")

    salon = db.table("salons").select("id, email, phone, business_name, salon_type").eq("id", salon_id).single().execute().data

    # 3. Buyer account (user_role = regular_buyer)
    print("3) Creating regular-buyer account ...")
    buyer_id = create_buyer_account(db, salon)

    # 4. Payment + activation
    print("4) Marking registration paid + activating regular buyer ...")
    activate_regular_buyer(db, salon_id, buyer_id)

    print("\n[DONE] Regular buyer ready:")
    print(f"   shop:     {salon.get('business_name')}")
    print(f"   salon_id: {salon_id}  (salon_type: regular_buyer — hidden from public discovery)")
    if buyer_id:
        print(f"   login:    {salon.get('email')} (password: {BUYER_PASSWORD})")
    else:
        print("   login:    (buyer account not created)")
    print("   Log in on the web app to test buying products at B2B (wholesale) prices.")


if __name__ == "__main__":
    main()
