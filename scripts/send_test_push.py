"""
Send a sample "New booking" push to a staging vendor's phone, without making a booking.

    python scripts/send_test_push.py                    # e2e.vendor@example.com
    python scripts/send_test_push.py --email x@y.com    # another vendor
    python scripts/send_test_push.py --list             # just show the registered phones

Why: a real booking needs Razorpay (disabled on staging), so this is the quickest way to
prove the device side works - FCM key in EAS, the installed build, the notification
channel, and the tap opening the booking. It does NOT prove the backend sends a push when a
booking is made; that is covered by tests/test_booking_mocked.py and, once staging has
Razorpay test keys, by the E2E booking flow.

Reads tests/e2e/.env.staging (service-role key, same file the E2E suite uses) and talks to
Supabase REST + Expo directly, so it needs no app env. Refuses non-staging Supabase unless
--allow-prod is given.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
EXPO_URL = "https://exp.host/--/api/v2/push/send"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", default="e2e.vendor@example.com", help="vendor profile email")
    parser.add_argument("--booking-id", help="booking to open on tap (default: a fake id -> 'not found' screen)")
    parser.add_argument("--list", action="store_true", help="only list the user's registered phones")
    parser.add_argument("--allow-prod", action="store_true", help="DANGEROUS: permit a non-staging project")
    args = parser.parse_args()

    env = dotenv_values(ROOT / "tests" / "e2e" / ".env.staging")
    url, key = env.get("E2E_SUPABASE_URL"), env.get("E2E_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("E2E_SUPABASE_URL / E2E_SUPABASE_SERVICE_ROLE_KEY missing in tests/e2e/.env.staging")
        return 2
    base_url = env.get("E2E_BASE_URL", "")
    if "staging" not in base_url and not args.allow_prod:
        print(f"Refusing: E2E_BASE_URL={base_url!r} does not look like staging (use --allow-prod to override).")
        return 2

    rest = {"apikey": key, "Authorization": f"Bearer {key}"}
    with httpx.Client(timeout=15) as client:
        prof = client.get(f"{url}/rest/v1/profiles", headers=rest,
                          params={"select": "id,email,user_role", "email": f"eq.{args.email}"}).json()
        if not prof:
            print(f"No profile with email {args.email}")
            return 1
        user_id = prof[0]["id"]
        rows = client.get(f"{url}/rest/v1/device_tokens", headers=rest,
                          params={"select": "expo_push_token,platform,app,is_active,last_seen_at",
                                  "user_id": f"eq.{user_id}"}).json()
        if isinstance(rows, dict):  # PostgREST error, e.g. migration not applied
            print(f"device_tokens query failed: {rows}")
            return 1
        print(f"{args.email} ({prof[0]['user_role']}): {len(rows)} registered phone(s)")
        for r in rows:
            print(f"  - {r['app']} {r['platform']} active={r['is_active']} last_seen={r['last_seen_at']}")
        if args.list:
            return 0
        tokens = [r["expo_push_token"] for r in rows if r["is_active"]]
        if not tokens:
            print("\nNo active phone. Open the Partner app (v1.1.0+) signed in as this vendor and allow "
                  "notifications, then run this again.")
            return 1

        messages = [{
            "to": t, "title": "New booking",
            "body": "Test Customer booked [E2E] Classic Haircut · tomorrow at 11:00 AM",
            "data": {"type": "booking", "booking_id": args.booking_id or "00000000-0000-0000-0000-000000000000",
                     "booking_number": "TEST-PUSH"},
            "sound": "default", "priority": "high", "channelId": "bookings",
        } for t in tokens]
        resp = client.post(EXPO_URL, json=messages, headers={"Accept": "application/json"})
        print(f"\nExpo HTTP {resp.status_code}")
        for ticket in (resp.json() or {}).get("data", []):
            print(f"  {ticket}")
        ok = all(t.get("status") == "ok" for t in (resp.json() or {}).get("data", []))
        if ok:
            print("\nAccepted by Expo. A banner should appear within a few seconds. If it doesn't, the "
                  "FCM key in EAS or the build's google-services.json is the likely cause.")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
