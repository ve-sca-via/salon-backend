"""
Seed a vendor join request as a Relationship Manager.

Flow this enables:
  1. Run this script  -> creates a PENDING vendor join request (submitted by the RM).
  2. Log into the Admin Panel -> Vendor Requests -> Approve it.
  3. On approval the backend creates the salon row (logo, cover images, hours, etc.).

Image handling (see app/services/vendor_approval_service.py):
  - documents.logo            -> salon.logo_url
  - cover_image_url           -> first entry of salon.cover_images
  - gallery_images[]          -> remaining salon.cover_images
  - documents.business_hours  -> salon opening/closing time + working_days
  - documents.description     -> salon.description

Usage:
    python scripts/seed_vendor_join_request.py
    python scripts/seed_vendor_join_request.py --base-url http://localhost:8000/api/v1
"""

import argparse
import sys
import time

import requests

DEFAULT_BASE_URL = "http://localhost:8000/api/v1"

# Relationship Manager who submits the request (must have role=relationship_manager
# and an rm_profiles row). NOTE: atif@gmail.com is a *vendor*, not an RM — the RM
# account is safdarniaxi@gmail.com (employee RM0001). Override with --email/--password.
RM_EMAIL = "safdarniaxi@gmail.com"
RM_PASSWORD = "Safdar@1234"

# Unsplash imagery (salon / beauty themed).
LOGO_URL = "https://images.unsplash.com/photo-1560066984-138dadb4c035?w=400&q=80"
COVER_IMAGE_URL = "https://images.unsplash.com/photo-1521590832167-7bcbfaa6381f?w=1200&q=80"
GALLERY_IMAGES = [
    "https://images.unsplash.com/photo-1570172619644-dfd03ed5d881?w=800&q=80",
    "https://images.unsplash.com/photo-1604654894610-df63bc536371?w=800&q=80",
    "https://images.unsplash.com/photo-1633681926022-84c23e8cb2d6?w=800&q=80",
    "https://images.unsplash.com/photo-1562322140-8baeececf3df?w=800&q=80",
]

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


def login(base_url: str, email: str, password: str) -> str:
    """Authenticate and return an access token."""
    try:
        resp = requests.post(f"{base_url}/auth/login", json={"email": email, "password": password})
        resp.raise_for_status()
        return resp.json()["access_token"]
    except requests.exceptions.RequestException as exc:
        print(f"[FAIL] Could not log in as {email}: {exc}")
        if getattr(exc, "response", None) is not None:
            print(f"       Response: {exc.response.text}")
        sys.exit(1)


def build_payload() -> dict:
    """A complete, valid vendor join request with Unsplash media."""
    # Unique-ish owner email so re-runs don't collide on the vendor account.
    suffix = int(time.time())
    return {
        # Business info
        "business_name": "Bloom & Co Salon",
        "business_type": "unisex_salon",  # salon | spa | clinic | unisex_salon | barber_shop | beauty_parlor
        "owner_name": "Rhea Kapoor",
        "owner_email": f"bloom.vendor+{suffix}@example.com",
        "owner_phone": "9876501234",
        # Location (real coords so nearby/maps work)
        "business_address": "12 MG Road, Near Trinity Metro, Bengaluru",
        "city": "Bengaluru",
        "state": "Karnataka",
        "pincode": "560001",
        "latitude": 12.9756,
        "longitude": 77.6050,
        # Legal & compliance
        "outlet": "Company owned",
        "is_gst": True,
        "gst_number": "29ABCDE1234F1Z5",
        "pan_number": "ABCDE1234F",
        # Media (these feed salon.logo_url / salon.cover_images on approval)
        "cover_image_url": COVER_IMAGE_URL,
        "gallery_images": GALLERY_IMAGES,
        # Request type
        "request_type": "salon",
        # Operations
        "opening_time": "09:00:00",
        "closing_time": "20:00:00",
        "working_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
        "facilities": FACILITIES,
        # Documents — logo, description and hours are read from here on approval
        "documents": {
            "logo": LOGO_URL,
            "description": (
                "Bloom & Co is a premium unisex salon offering hair, skin, nails and spa "
                "services with a relaxing, hygienic environment in the heart of Bengaluru."
            ),
            "business_hours": BUSINESS_HOURS,
            "facilities": FACILITIES,
        },
    }


def create_vendor_request(base_url: str, token: str, payload: dict) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    try:
        # is_draft=false -> submitted as "pending" for admin approval
        resp = requests.post(
            f"{base_url}/rm/vendor-requests",
            params={"is_draft": "false"},
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as exc:
        print(f"[FAIL] Could not create vendor request: {exc}")
        if getattr(exc, "response", None) is not None:
            print(f"       Response: {exc.response.text}")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a pending vendor join request as an RM.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL (with /api/v1)")
    parser.add_argument("--email", default=RM_EMAIL, help="RM login email")
    parser.add_argument("--password", default=RM_PASSWORD, help="RM login password")
    args = parser.parse_args()

    print(f"Logging in as RM {args.email} ...")
    token = login(args.base_url, args.email, args.password)
    print("  -> authenticated")

    payload = build_payload()
    print(f"Submitting vendor join request for '{payload['business_name']}' ...")
    result = create_vendor_request(args.base_url, token, payload)

    request_id = result.get("id") or result.get("request", {}).get("id")
    status_val = result.get("status") or result.get("request", {}).get("status")
    print("\n[OK] Vendor join request created.")
    print(f"     id:     {request_id}")
    print(f"     status: {status_val}")
    print("\nNext steps:")
    print("  1. Open the Admin Panel -> Vendor Requests.")
    print("  2. Approve this request to create the salon (with logo/cover/gallery).")
    print("  Note: an approved salon becomes publicly visible once the vendor completes")
    print("        registration and the registration fee is marked paid.")


if __name__ == "__main__":
    main()
