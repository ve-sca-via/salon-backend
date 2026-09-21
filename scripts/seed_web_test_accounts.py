"""
Fixed, re-runnable test accounts for signed-in testing of the web apps
(built for the Next.js migration's Phase 1/2 verification, useful for any client).

Creates (or repairs) one account per signed-in state, all with the same password:

  web.customer@example.com      customer, email confirmed
  web.unconfirmed@example.com   customer, email NOT confirmed (sign-in error states)
  web.vendor@example.com        vendor, salon approved + paid + active + services
  web.vendor.unpaid@example.com vendor, salon approved but registration fee unpaid
  web.buyer@example.com         regular_buyer, approved + paid (B2B products)

The RM portal uses the existing RM account (saf2@gmail.com).

Salons are built exactly like production (RM request -> admin approval over the
HTTP API), then finished with the service-role client, reusing the helpers from
seed_full_salon.py / seed_regular_buyer.py. Re-running is safe: accounts that
exist get their role/password/confirmation reset, salons that exist are reused.

LOCAL ONLY — refuses to run unless SUPABASE_URL points at localhost.

Usage (backend running, venv active):
    python scripts/seed_web_test_accounts.py
"""

import functools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import seed_full_salon as salon_seed  # noqa: E402
import seed_regular_buyer as buyer_seed  # noqa: E402
from app.core.config import settings  # noqa: E402
from supabase import create_client  # noqa: E402

PASSWORD = "Test@1234"
BASE_URL = salon_seed.DEFAULT_BASE_URL

CUSTOMER = "web.customer@example.com"
UNCONFIRMED = "web.unconfirmed@example.com"
VENDOR = "web.vendor@example.com"
VENDOR_UNPAID = "web.vendor.unpaid@example.com"
BUYER = "web.buyer@example.com"


@functools.cache
def token_for(email: str, password: str) -> str:
    """One login per role per run — /auth/login is rate-limited."""
    return salon_seed.login(BASE_URL, email, password)


def find_user_id(db, email: str) -> str | None:
    found = db.table("profiles").select("id").eq("email", email).execute().data
    if found:
        return found[0]["id"]
    for user in db.auth.admin.list_users(per_page=1000):
        if getattr(user, "email", None) == email:
            return user.id
    return None


def ensure_user(db, email: str, role: str, full_name: str, confirmed: bool = True, phone=None) -> str:
    """Create the auth user + profile, or reset an existing one to the expected state."""
    user_id = find_user_id(db, email)
    attrs = {"password": PASSWORD, "email_confirm": confirmed}
    if user_id:
        db.auth.admin.update_user_by_id(user_id, attrs)
        print(f"  reset   {email}")
    else:
        user_id = db.auth.admin.create_user({"email": email, **attrs}).user.id
        print(f"  created {email}")

    db.table("profiles").upsert(
        {
            "id": user_id,
            "email": email,
            "full_name": full_name,
            "user_role": role,
            "phone": phone,
            "age": 30,
            "gender": "female",
            "is_active": True,
        }
    ).execute()
    return user_id


def ensure_salon(db, seed_module, owner_email: str, business_name: str) -> dict:
    """Return the salon owned by `owner_email`, submitting + approving one if needed."""
    existing = db.table("salons").select("*").eq("email", owner_email).execute().data
    if existing:
        print(f"  reuse   salon '{existing[0]['business_name']}'")
        return existing[0]

    payload = seed_module.build_request_payload()
    payload["owner_email"] = owner_email
    payload["business_name"] = business_name

    rm_token = token_for(salon_seed.RM_EMAIL, salon_seed.RM_PASSWORD)
    resp = salon_seed.requests.post(
        f"{BASE_URL}/rm/vendor-requests",
        params={"is_draft": "false"},
        json=payload,
        headers={"Authorization": f"Bearer {rm_token}"},
    )
    if not resp.ok:
        salon_seed.die("create request failed", resp.text)
    data = resp.json()
    request_id = data.get("id") or data.get("request", {}).get("id")

    admin_token = token_for(salon_seed.ADMIN_EMAIL, salon_seed.ADMIN_PASSWORD)
    salon_id = salon_seed.approve_request(BASE_URL, admin_token, request_id)
    if not salon_id:
        found = db.table("salons").select("id").eq("join_request_id", request_id).execute().data
        salon_id = found[0]["id"] if found else None
    if not salon_id:
        salon_seed.die(f"approval did not yield a salon for {owner_email}")
    print(f"  created salon '{business_name}'")
    return db.table("salons").select("*").eq("id", salon_id).single().execute().data


def main() -> None:
    if not any(host in settings.SUPABASE_URL for host in ("127.0.0.1", "localhost")):
        salon_seed.die(f"refusing to seed test accounts into {settings.SUPABASE_URL} (not local)")

    db = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

    print("customer")
    ensure_user(db, CUSTOMER, "customer", "Web Test Customer")

    print("unconfirmed customer")
    ensure_user(db, UNCONFIRMED, "customer", "Web Unconfirmed Customer", confirmed=False)

    print("vendor (paid, live)")
    salon = ensure_salon(db, salon_seed, VENDOR, "Lubist Test Salon")
    vendor_id = ensure_user(db, VENDOR, "vendor", "Web Test Vendor", phone=salon.get("phone"))
    salon_seed.activate_salon(db, salon["id"], vendor_id)
    has_services = db.table("services").select("id").eq("salon_id", salon["id"]).limit(1).execute().data
    if not has_services:
        print(f"  seeded  {salon_seed.seed_services(db, salon['id'])} services")

    print("vendor (registration unpaid)")
    salon = ensure_salon(db, salon_seed, VENDOR_UNPAID, "Lubist Unpaid Salon")
    vendor_id = ensure_user(db, VENDOR_UNPAID, "vendor", "Web Unpaid Vendor", phone=salon.get("phone"))
    db.table("salons").update(
        {"vendor_id": vendor_id, "registration_fee_paid": False, "is_verified": False}
    ).eq("id", salon["id"]).execute()

    print("regular buyer")
    salon = ensure_salon(db, buyer_seed, BUYER, "Lubist Test Buyer Store")
    buyer_id = ensure_user(db, BUYER, "regular_buyer", "Web Test Buyer", phone=salon.get("phone"))
    buyer_seed.activate_regular_buyer(db, salon["id"], buyer_id)

    print(f"\n[DONE] password for every web.* account: {PASSWORD}")
    print(f"       RM portal: {salon_seed.RM_EMAIL} / {salon_seed.RM_PASSWORD}")


if __name__ == "__main__":
    main()
