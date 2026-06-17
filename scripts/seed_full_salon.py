"""
End-to-end salon seeder: request -> approve -> vendor account -> payment -> services.

Pipeline:
  1. RM submits a vendor join request          (API, as relationship_manager)
  2. Admin approves it -> salon row created     (API, as admin)
  3. Create a vendor account + link to salon    (service-role DB)
  4. "Pay" + activate the salon                 (service-role DB: flips the flags
     that the real Razorpay registration flow would otherwise set)
  5. Seed services with images + taxonomy       (service-role DB)

Result: a fully public salon (is_active/is_verified/registration_fee_paid = true)
with services, visible in the mobile app.

Steps 1-2 use the HTTP API (so the salon is built exactly like production).
Steps 3-5 use the Supabase service-role client because the real paths
(emailed registration token + Razorpay payment) can't be driven from a seed.

Usage (backend running, venv active):
    python scripts/seed_full_salon.py
    python scripts/seed_full_salon.py --request-id <existing_pending_request_id>
"""

import argparse
import os
import random
import sys
import time
from datetime import datetime, timezone

import requests

# Allow `from app...` imports when run as `python scripts/seed_full_salon.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from supabase import create_client

DEFAULT_BASE_URL = "http://localhost:8000/api/v1"

RM_EMAIL = "saf2@gmail.com"          # role = relationship_manager
RM_PASSWORD = "Safdar@1234"
ADMIN_EMAIL = "787alisniazi787@gmail.com"   # role = admin
ADMIN_PASSWORD = "Safdar@1234"

VENDOR_PASSWORD = "Vendor@1234"             # password for the seeded vendor account

# --- Randomization pools ----------------------------------------------------
SALON_TYPES = ["salon", "spa", "clinic", "unisex_salon", "barber_shop", "beauty_parlor"]

NAME_PREFIX = [
    "Bloom", "Luxe", "Glow", "Velvet", "Aura", "Opal", "Serene", "Gloss",
    "Vogue", "Halo", "Posh", "Bliss", "Radiance", "Lush", "Mirage", "Ivory",
]
NAME_SUFFIX = [
    "& Co Salon", "Beauty Lounge", "Spa & Studio", "Grooming Co", "Hair Atelier",
    "Wellness Studio", "Salon & Spa", "Beauty Bar", "Style House", "Glam Studio",
]
OWNER_NAMES = [
    "Rhea Kapoor", "Aarav Mehta", "Sana Sheikh", "Vikram Rao", "Neha Verma",
    "Imran Khan", "Pooja Nair", "Karan Singh", "Diya Iyer", "Rohan Das",
]

# Real Indian cities with representative coords/pincode for nearby + maps.
CITIES = [
    {"city": "Bengaluru", "state": "Karnataka", "pincode": "560001", "lat": 12.9716, "lon": 77.5946, "area": "MG Road"},
    {"city": "Mumbai", "state": "Maharashtra", "pincode": "400050", "lat": 19.0596, "lon": 72.8295, "area": "Bandra West"},
    {"city": "Delhi", "state": "Delhi", "pincode": "110001", "lat": 28.6315, "lon": 77.2167, "area": "Connaught Place"},
    {"city": "Hyderabad", "state": "Telangana", "pincode": "500034", "lat": 17.4126, "lon": 78.4490, "area": "Banjara Hills"},
    {"city": "Pune", "state": "Maharashtra", "pincode": "411001", "lat": 18.5362, "lon": 73.8939, "area": "Koregaon Park"},
    {"city": "Chennai", "state": "Tamil Nadu", "pincode": "600017", "lat": 13.0418, "lon": 80.2341, "area": "T. Nagar"},
    {"city": "Jaipur", "state": "Rajasthan", "pincode": "302001", "lat": 26.9124, "lon": 75.7873, "area": "C-Scheme"},
]

# Unsplash photo IDs (salon / beauty / spa). Sizes applied per use.
UNSPLASH_IDS = [
    "1560066984-138dadb4c035", "1570172619644-dfd03ed5d881", "1604654894610-df63bc536371",
    "1521590832167-7bcbfaa6381f", "1599351431202-1e0f0137899a", "1503951914875-452162b0f3f1",
    "1487412947147-5cebf100ffc2", "1595476108010-b4d1f102b1b1", "1522337660859-02fbefca4702",
    "1633681926022-84c23e8cb2d6", "1562322140-8baeececf3df", "1600948836101-f9ffda59d250",
    "1580618672591-eb180b1a973f", "1519415943484-9fa1873496d4", "1559599101-f09722fb4948",
]


def unsplash(photo_id: str, width: int) -> str:
    return f"https://images.unsplash.com/photo-{photo_id}?w={width}&q=80"


BUSINESS_HOURS = {
    "monday": "9:00 AM - 7:00 PM",
    "tuesday": "9:00 AM - 7:00 PM",
    "wednesday": "9:00 AM - 7:00 PM",
    "thursday": "9:00 AM - 7:00 PM",
    "friday": "9:00 AM - 8:00 PM",
    "saturday": "9:00 AM - 8:00 PM",
    "sunday": "Closed",
}
FACILITIES = {
    "free_wifi": True,
    "car_parking": True,
    "air_conditioner": True,
    "sanitized_tools": True,
    "comfortable_seating": True,
    "hygienic_environment": True,
}

# Two services per category (uses the category's subcategories when available).
SERVICE_TEMPLATES = [
    {"name": "Signature Haircut", "price": 499, "discounted_price": 399, "duration": 45},
    {"name": "Wash & Blow Dry", "price": 699, "discounted_price": None, "duration": 40},
    {"name": "Global Hair Color", "price": 2499, "discounted_price": 1999, "duration": 90},
    {"name": "Express Facial", "price": 1299, "discounted_price": 999, "duration": 60},
    {"name": "Luxury Spa Therapy", "price": 1999, "discounted_price": None, "duration": 75},
    {"name": "Classic Manicure", "price": 599, "discounted_price": None, "duration": 30},
]


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
    suffix = int(time.time())
    name = f"{random.choice(NAME_PREFIX)} {random.choice(NAME_SUFFIX)}"
    owner = random.choice(OWNER_NAMES)
    loc = random.choice(CITIES)
    btype = random.choice(SALON_TYPES)
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
        "gallery_images": [unsplash(pid, 800) for pid in random.sample(UNSPLASH_IDS, 4)],
        "request_type": "salon",
        "opening_time": "09:00:00",
        "closing_time": "20:00:00",
        "working_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
        "facilities": FACILITIES,
        "documents": {
            "logo": unsplash(random.choice(UNSPLASH_IDS), 400),
            "description": (
                f"{name} is a premium {btype.replace('_', ' ')} offering hair, skin, nails and "
                f"spa services with a relaxing, hygienic environment in {loc['city']}."
            ),
            "business_hours": BUSINESS_HOURS,
            "facilities": FACILITIES,
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
            json={"admin_notes": "Seeded approval"},
            headers=headers,
        )
        r.raise_for_status()
        return r.json().get("data", {}).get("salon_id")
    except requests.exceptions.RequestException as exc:
        die(f"approve failed: {exc}", getattr(getattr(exc, "response", None), "text", None))


def create_vendor_account(db, salon: dict) -> str | None:
    """Create (or reuse) a vendor auth user + profile and return its id."""
    email = salon.get("email")
    name = f"{salon.get('business_name', 'Salon')} Owner"
    if not email:
        print("  [skip] salon has no email; leaving vendor_id unset")
        return None

    existing = db.table("profiles").select("id").eq("email", email).execute()
    if existing.data:
        vendor_id = existing.data[0]["id"]
        print(f"  vendor profile already exists ({email})")
    else:
        try:
            res = db.auth.admin.create_user(
                {"email": email, "password": VENDOR_PASSWORD, "email_confirm": True}
            )
            vendor_id = res.user.id
            print(f"  created vendor auth user ({email}) / password: {VENDOR_PASSWORD}")
        except Exception:  # noqa: BLE001 — likely already exists; look it up
            vendor_id = None
            try:
                for u in db.auth.admin.list_users():
                    if getattr(u, "email", None) == email:
                        vendor_id = u.id
                        break
            except Exception as exc:  # noqa: BLE001
                print(f"  [warn] could not resolve auth user: {str(exc)[:150]}")
            if not vendor_id:
                print("  [warn] vendor auth user could not be created/found; skipping link")
                return None

    # Ensure a vendor profile row exists (a trigger may have created a bare one).
    db.table("profiles").upsert(
        {
            "id": vendor_id,
            "email": email,
            "full_name": name,
            "user_role": "vendor",
            "phone": salon.get("phone"),
            "age": 30,
            "gender": "female",
            "is_active": True,
        }
    ).execute()
    return vendor_id


def activate_salon(db, salon_id: str, vendor_id: str | None):
    update = {
        "is_active": True,
        "is_verified": True,
        "registration_fee_paid": True,
        "accepting_bookings": True,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }
    if vendor_id:
        update["vendor_id"] = vendor_id
    db.table("salons").update(update).eq("id", salon_id).execute()


def seed_services(db, salon_id: str):
    cats = db.table("service_categories").select("id, name").eq("is_active", True).limit(3).execute().data or []
    if not cats:
        print("  [skip] no service categories found — run seed_service_categories.py first")
        return 0

    subs = db.table("service_subcategories").select("id, name, parent_category_id").execute().data or []
    subs_by_cat: dict[str, list] = {}
    for s in subs:
        subs_by_cat.setdefault(s["parent_category_id"], []).append(s)

    # Random subset/order of services each run.
    chosen = random.sample(SERVICE_TEMPLATES, k=random.randint(4, len(SERVICE_TEMPLATES)))
    rows = []
    for i, tpl in enumerate(chosen):
        cat = cats[i % len(cats)]
        cat_subs = subs_by_cat.get(cat["id"], [])
        sub = random.choice(cat_subs) if cat_subs else None
        disc = tpl["discounted_price"]
        # Constraint: discount_percentage and discounted_price must both be set or both null.
        discount_pct = round((tpl["price"] - disc) / tpl["price"] * 100, 2) if disc else None
        rows.append(
            {
                "salon_id": salon_id,
                "category_id": cat["id"],
                "subcategory_id": sub["id"] if sub else None,
                "name": tpl["name"],
                "description": f"{tpl['name']} by our expert stylists.",
                "price": tpl["price"],
                "discounted_price": disc,
                "discount_percentage": discount_pct,
                "duration_minutes": tpl["duration"],
                "image_url": unsplash(random.choice(UNSPLASH_IDS), 600),
                "is_active": True,
            }
        )

    db.table("services").insert(rows).execute()
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a fully public salon end-to-end.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--request-id", help="Approve an existing pending request instead of creating one")
    parser.add_argument("--salon-id", help="Finalize an already-approved salon (skip request + approval)")
    parser.add_argument("--rm-email", default=RM_EMAIL)
    parser.add_argument("--rm-password", default=RM_PASSWORD)
    parser.add_argument("--admin-email", default=ADMIN_EMAIL)
    parser.add_argument("--admin-password", default=ADMIN_PASSWORD)
    args = parser.parse_args()

    db = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

    if args.salon_id:
        # Steps 1-2 already done — finalize an existing approved salon.
        salon_id = args.salon_id
        print(f"1-2) Using existing approved salon {salon_id}")
    else:
        # 1. Create the request (unless reusing one)
        request_id = args.request_id
        if not request_id:
            print("1) Submitting vendor join request as RM ...")
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

    salon = db.table("salons").select("id, email, phone, business_name").eq("id", salon_id).single().execute().data

    # 3. Vendor account
    print("3) Creating vendor account ...")
    vendor_id = create_vendor_account(db, salon)

    # 4. Payment + activation
    print("4) Marking registration paid + activating salon ...")
    activate_salon(db, salon_id, vendor_id)

    # 5. Services
    print("5) Seeding services with images ...")
    count = seed_services(db, salon_id)
    print(f"   -> {count} services added")

    print("\n[DONE] Public salon ready:")
    print(f"   name:     {salon.get('business_name')}")
    print(f"   salon_id: {salon_id}")
    print(f"   vendor:   {salon.get('email')} (password: {VENDOR_PASSWORD})" if vendor_id else "   vendor:   (not created)")
    print("   It should now appear in the mobile app (Discover / nearby) with services.")


if __name__ == "__main__":
    main()
