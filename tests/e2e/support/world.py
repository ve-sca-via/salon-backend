"""
`World`: the shared test-data universe for one E2E session.

Two kinds of data:

1. FIXED accounts, re-used across runs and seeded idempotently with the
   service-role client (created if missing, password + role re-asserted every
   run so a run never depends on what the last one left behind):

       e2e.admin@example.com      admin
       e2e.rm@example.com         relationship_manager (+ rm_profiles row)
       e2e.vendor@example.com     vendor   + "[E2E] Lubist Test Salon" (+1 service)
       e2e.customer@example.com   customer

2. PER-RUN entities (join requests, approved salons, the vendor/buyer accounts
   they produce, products, coupons, bookings, orders, partner leads). Every one
   carries the run id (``E2E-<yyyymmddHHMMSS>``) in a name/email/notes field,
   and cleanup finds them BY THAT TAG, so a crashed run still cleans up and
   ``--sweep-stale`` can remove leftovers of every past run (tag ``E2E-``).

The fixed salon is public on staging by design (customer booking flow needs a
bookable salon); it is clearly named and never deleted.
"""
from __future__ import annotations

import random
from typing import Any, Callable

import pytest

from .client import ApiClient, expect
from .config import E2EConfig

FIXED_ACCOUNTS = {
    "admin": ("e2e.admin@example.com", "admin", "E2E Admin"),
    "rm": ("e2e.rm@example.com", "relationship_manager", "E2E Relationship Manager"),
    "vendor": ("e2e.vendor@example.com", "vendor", "E2E Vendor"),
    "customer": ("e2e.customer@example.com", "customer", "E2E Customer"),
}
FIXED_SALON_NAME = "[E2E] Lubist Test Salon"
FIXED_SERVICE_NAME = "[E2E] Classic Haircut"
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


class World:
    def __init__(self, cfg: E2EConfig, api: ApiClient):
        self.cfg = cfg
        self.api = api
        self._db = None
        self._sessions: dict[str, dict] = {}
        self.accounts: dict[str, dict] = {}
        self.fixed_salon: dict | None = None
        self.fixed_service: dict | None = None
        self.seed_error: str | None = None
        self.shared: dict[str, Any] = {}   # cross-flow hand-offs (rarely needed)
        self.notes: list[str] = []         # free-form observations for the report

    # ------------------------------------------------------------------
    # service-role DB
    # ------------------------------------------------------------------
    @property
    def db(self):
        if self._db is None:
            missing = self.cfg.missing_seed_secrets()
            if missing:
                pytest.skip(f"service-role access not configured (missing {', '.join(missing)})")
            from supabase import create_client
            self._db = create_client(self.cfg.supabase_url, self.cfg.service_role_key)
        return self._db

    def require_seeded(self) -> None:
        if self.seed_error:
            pytest.skip(f"fixed E2E accounts could not be seeded: {self.seed_error}")

    # ------------------------------------------------------------------
    # seeding
    # ------------------------------------------------------------------
    def seed(self) -> None:
        try:
            for role, (email, user_role, name) in FIXED_ACCOUNTS.items():
                uid = self.ensure_user(email, self.cfg.password, user_role, name)
                self.accounts[role] = {"id": uid, "email": email, "password": self.cfg.password,
                                       "role": user_role}
            self.db.table("rm_profiles").upsert({"id": self.accounts["rm"]["id"]}).execute()
            self._ensure_fixed_salon()
        except pytest.skip.Exception as exc:
            self.seed_error = str(exc)
        except Exception as exc:  # noqa: BLE001 - surfaced as a skip reason + report note
            self.seed_error = f"{type(exc).__name__}: {str(exc)[:300]}"

    def _find_auth_user_id(self, email: str) -> str | None:
        prof = self.db.table("profiles").select("id").eq("email", email).limit(1).execute()
        if prof.data:
            return prof.data[0]["id"]
        page = 1
        while page < 60:
            users = self.db.auth.admin.list_users(page=page, per_page=200)
            if not users:
                return None
            for u in users:
                if (getattr(u, "email", "") or "").lower() == email.lower():
                    return u.id
            if len(users) < 200:
                return None
            page += 1
        return None

    def ensure_user(self, email: str, password: str, user_role: str, full_name: str,
                    **profile_extra: Any) -> str:
        """Create-or-repair a confirmed auth user + profile. Returns the user id."""
        uid = self._find_auth_user_id(email)
        attrs = {"email": email, "password": password, "email_confirm": True,
                 "user_metadata": {"full_name": full_name, "user_role": user_role}}
        if uid is None:
            uid = self.db.auth.admin.create_user(attrs).user.id
        else:
            self.db.auth.admin.update_user_by_id(uid, {"password": password, "email_confirm": True})
        self.db.table("profiles").upsert({
            "id": uid, "email": email, "full_name": full_name, "user_role": user_role,
            "is_active": True, "age": 30, "gender": "other", "deleted_at": None,
            "token_valid_after": None, **profile_extra,
        }).execute()
        return uid

    def _ensure_fixed_salon(self) -> None:
        vendor_id = self.accounts["vendor"]["id"]
        hours = {d: "9:00 AM - 9:00 PM" for d in DAYS}
        salon_fields = {
            "business_name": FIXED_SALON_NAME,
            "email": self.accounts["vendor"]["email"],
            "phone": "+919000000001",
            "address": "1 E2E Test Street, MG Road",
            "city": "Bengaluru", "state": "Karnataka", "pincode": "560001",
            "latitude": 12.9716, "longitude": 77.5946,
            "vendor_id": vendor_id, "salon_type": "salon",
            "is_active": True, "is_verified": True, "registration_fee_paid": True,
            "accepting_bookings": True, "deleted_at": None,
            "opening_time": "09:00:00", "closing_time": "21:00:00",
            "working_days": [d.capitalize() for d in DAYS], "business_hours": hours,
            "description": "Fixed salon used by the automated E2E suite on staging. Not a real business.",
        }
        found = self.db.table("salons").select("*").eq("vendor_id", vendor_id).limit(1).execute()
        if found.data:
            salon = self.db.table("salons").update(salon_fields).eq("id", found.data[0]["id"]).execute().data[0]
        else:
            salon = self.db.table("salons").insert(salon_fields).execute().data[0]
        self.fixed_salon = salon

        svc = self.db.table("services").select("*").eq("salon_id", salon["id"]) \
            .eq("name", FIXED_SERVICE_NAME).limit(1).execute()
        if svc.data:
            service = self.db.table("services").update({"is_active": True, "price": 500, "duration_minutes": 30}) \
                .eq("id", svc.data[0]["id"]).execute().data[0]
        else:
            cat = self.db.table("service_categories").select("id").eq("is_active", True).limit(1).execute()
            if not cat.data:
                cat = self.db.table("service_categories").select("id").limit(1).execute()
            if not cat.data:
                raise RuntimeError("staging has no service_categories row to attach the fixed service to")
            service = self.db.table("services").insert({
                "name": FIXED_SERVICE_NAME, "salon_id": salon["id"], "category_id": cat.data[0]["id"],
                "price": 500, "duration_minutes": 30, "is_active": True, "gender_category": "both",
                "description": "E2E fixed service",
            }).execute().data[0]
        self.fixed_service = service

    # ------------------------------------------------------------------
    # auth sessions (one login per account per run: login is 5/min/IP)
    # ------------------------------------------------------------------
    def login(self, email: str, password: str) -> dict:
        if email not in self._sessions:
            resp = self.api.post("/auth/login", json={"email": email, "password": password})
            data = expect(resp, 200, what=f"login {email}")
            self._sessions[email] = data
        return self._sessions[email]

    def session(self, role: str) -> dict:
        self.require_seeded()
        acct = self.accounts[role]
        return self.login(acct["email"], acct["password"])

    def token(self, role: str) -> str:
        return self.session(role)["access_token"]

    def forget_session(self, email: str) -> None:
        self._sessions.pop(email, None)

    # ------------------------------------------------------------------
    # unique per-run values
    # ------------------------------------------------------------------
    def unique_phone(self) -> str:
        """10-digit Indian mobile not used by any join request (owner phones must be unique)."""
        for _ in range(20):
            phone = "6" + "".join(random.choices("0123456789", k=9))
            hit = self.db.table("vendor_join_requests").select("id").eq("owner_phone", phone).limit(1).execute()
            prof = self.db.table("profiles").select("id").in_("phone", [phone, "+91" + phone]).limit(1).execute()
            if not hit.data and not prof.data:
                return phone
        raise RuntimeError("could not find an unused phone number")

    @staticmethod
    def pan() -> str:
        letters = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=5))
        return f"{letters}{random.randint(1000, 9999)}F"

    # ------------------------------------------------------------------
    # cleanup - by tag, FK-safe order
    # ------------------------------------------------------------------
    def cleanup(self, tag: str, log: Callable[[str], None] = print) -> dict[str, int]:
        db = self.db
        counts: dict[str, int] = {}

        def run(label: str, fn: Callable[[], Any]) -> Any:
            try:
                res = fn()
                n = len(getattr(res, "data", None) or []) if res is not None else 0
                if n:
                    counts[label] = counts.get(label, 0) + n
                return res
            except Exception as exc:  # noqa: BLE001 - cleanup is best effort, but loud
                log(f"[e2e cleanup] {label}: {str(exc)[:200]}")
                return None

        like = f"%{tag}%"
        sel = lambda table, cols, col: (db.table(table).select(cols).ilike(col, like).execute().data or [])  # noqa: E731

        salons = sel("salons", "id,vendor_id", "business_name")
        salon_ids = [s["id"] for s in salons]
        requests_ = sel("vendor_join_requests", "id", "business_name")
        request_ids = [r["id"] for r in requests_]

        fixed_ids = {a["id"] for a in self.accounts.values()} if self.accounts else set()
        user_ids = {s["vendor_id"] for s in salons if s.get("vendor_id")}
        user_ids |= {p["id"] for p in sel("profiles", "id", "email")}
        user_ids |= {p["id"] for p in sel("profiles", "id", "full_name")}
        user_ids -= fixed_ids  # never delete the fixed accounts

        product_ids = [p["id"] for p in sel("products", "id", "name")]
        coupon_ids = [c["id"] for c in sel("coupons", "id", "title")]
        service_ids = [s["id"] for s in sel("services", "id", "name")]

        booking_ids = {b["id"] for b in sel("bookings", "id", "notes")}
        if salon_ids:
            booking_ids |= {b["id"] for b in (db.table("bookings").select("id").in_("salon_id", salon_ids).execute().data or [])}
        if service_ids:
            for b in db.table("bookings").select("id,services").eq("salon_id", (self.fixed_salon or {}).get("id", "00000000-0000-0000-0000-000000000000")).execute().data or []:
                if any((s or {}).get("service_id") in service_ids for s in (b.get("services") or [])):
                    booking_ids.add(b["id"])
        booking_ids = list(booking_ids)

        order_ids = {o["id"] for o in (db.table("product_orders").select("id").ilike("shipping_address->>full_name", like).execute().data or [])}
        if user_ids:
            order_ids |= {o["id"] for o in (db.table("product_orders").select("id").in_("user_id", list(user_ids)).execute().data or [])}
        if product_ids:
            order_ids |= {i["order_id"] for i in (db.table("product_order_items").select("order_id").in_("product_id", product_ids).execute().data or [])}
        order_ids = list(order_ids)

        if booking_ids:
            for table in ("coupon_redemptions", "booking_payments", "payments", "reviews"):
                run(table, lambda t=table: db.table(t).delete().in_("booking_id", booking_ids).execute())
            run("bookings", lambda: db.table("bookings").delete().in_("id", booking_ids).execute())
        if order_ids:
            run("coupon_redemptions", lambda: db.table("coupon_redemptions").delete().in_("product_order_id", order_ids).execute())
            run("product_order_items", lambda: db.table("product_order_items").delete().in_("order_id", order_ids).execute())
            run("product_orders", lambda: db.table("product_orders").delete().in_("id", order_ids).execute())

        # Carts / intents of every account the run touched (fixed ones included:
        # they exist only for this suite, so their carts are always disposable).
        cart_users = list(user_ids | fixed_ids)
        if cart_users:
            run("cart_items", lambda: db.table("cart_items").delete().in_("user_id", cart_users).execute())
            run("product_cart_items", lambda: db.table("product_cart_items").delete().in_("user_id", cart_users).execute())
            run("payment_intents", lambda: db.table("payment_intents").delete().in_("customer_id", cart_users).execute())
        if salon_ids:
            run("payment_intents", lambda: db.table("payment_intents").delete().in_("salon_id", salon_ids).execute())
            run("vendor_registration_payments", lambda: db.table("vendor_registration_payments").delete().in_("salon_id", salon_ids).execute())
        if request_ids:
            run("vendor_registration_payments", lambda: db.table("vendor_registration_payments").delete().in_("vendor_request_id", request_ids).execute())
        if user_ids:
            run("vendor_registration_payments", lambda: db.table("vendor_registration_payments").delete().in_("vendor_id", list(user_ids)).execute())

        if coupon_ids:
            run("coupon_redemptions", lambda: db.table("coupon_redemptions").delete().in_("coupon_id", coupon_ids).execute())
            run("coupons", lambda: db.table("coupons").delete().in_("id", coupon_ids).execute())
        if product_ids:
            run("product_favorites", lambda: db.table("product_favorites").delete().in_("product_id", product_ids).execute())
            run("products", lambda: db.table("products").delete().in_("id", product_ids).execute())
        if service_ids:
            run("services", lambda: db.table("services").delete().in_("id", service_ids).execute())
        if salon_ids:
            run("favorites", lambda: db.table("favorites").delete().in_("salon_id", salon_ids).execute())
            run("salons", lambda: db.table("salons").delete().in_("id", salon_ids).execute())
        run("rm_score_history", lambda: db.table("rm_score_history").delete().ilike("description", like).execute())
        if request_ids:
            run("vendor_join_requests", lambda: db.table("vendor_join_requests").delete().in_("id", request_ids).execute())
        run("partner_requests", lambda: db.table("partner_requests").delete().ilike("shop_name", like).execute())
        for uid in user_ids:
            run("token_blacklist", lambda u=uid: db.table("token_blacklist").delete().eq("user_id", u).execute())
            run("profiles", lambda u=uid: db.table("profiles").delete().eq("id", u).execute())
            try:
                db.auth.admin.delete_user(uid)
                counts["auth_users"] = counts.get("auth_users", 0) + 1
            except Exception as exc:  # noqa: BLE001
                log(f"[e2e cleanup] auth user {uid}: {str(exc)[:200]}")
        return counts
