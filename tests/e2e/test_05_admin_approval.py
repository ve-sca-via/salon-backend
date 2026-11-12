"""Admin approval: pending queue -> approve RM's salon request -> vendor completes
registration -> registration fee -> salon goes live. Plus reject path."""
import pytest

from .support.builders import approve, submit_request
from .support.client import detail, expect, xfail_if
from .support.tokens import razorpay_signature, registration_token

FLOW = "admin"
FLOW_TITLE = "Admin approval & vendor onboarding"
pytestmark = pytest.mark.e2e


def test_admin_dashboard(api, world):
    """GET /admin/stats and /admin/recent-activity"""
    token = world.token("admin")
    expect(api.get("/admin/stats", token=token), 200)
    expect(api.get("/admin/recent-activity", token=token, params={"limit": 5}), 200)


def test_admin_sees_pending_request(api, world, flow):
    """RM's salon request is in GET /admin/vendor-requests?status_filter=pending"""
    req = world.shared.get("salon_request") or submit_request(api, world, "salon")
    data = expect(api.get("/admin/vendor-requests", token=world.token("admin"),
                          params={"status_filter": "pending", "limit": 200}), 200)
    rows = data if isinstance(data, list) else data.get("data", [])
    assert req["id"] in {r.get("id") for r in rows}, "RM's request missing from admin pending queue"
    flow["request"] = req


def test_admin_approves_salon(api, world, flow):
    """POST /admin/vendor-requests/{id}/approve creates an inactive, unpaid salon"""
    req = flow.need("request")
    data = approve(api, world, req["id"])
    salon_id = (data.get("data") or {}).get("salon_id") or data.get("salon_id")
    assert salon_id, f"approval returned no salon_id: {data}"
    salon = world.db.table("salons").select("*").eq("id", salon_id).single().execute().data
    assert salon["join_request_id"] == req["id"]
    assert salon["salon_type"] == "salon"
    assert salon["email"] == req["owner_email"]
    status = world.db.table("vendor_join_requests").select("status").eq("id", req["id"]).single().execute().data
    assert status["status"] == "approved", status
    flow["salon"] = salon
    if salon.get("registration_fee_paid"):
        world.notes.append("Salon registration fee is 0 on staging - approval auto-activated the salon.")


def test_double_approve_is_rejected(api, world, flow):
    """Approving the same request twice does not create a second salon"""
    req = flow.need("request")
    resp = api.post(f"/admin/vendor-requests/{req['id']}/approve", token=world.token("admin"), json={})
    assert resp.status_code in (400, 409), f"second approval -> {resp.status_code}: {resp.text[:200]}"
    n = world.db.table("salons").select("id").eq("join_request_id", req["id"]).execute().data
    assert len(n) == 1, f"{len(n)} salons for one request"


def test_unpaid_salon_not_public(api, flow):
    """Approved-but-unpaid salon is hidden from GET /salons/{id} (404)"""
    salon = flow.need("salon")
    if salon.get("registration_fee_paid"):
        pytest.skip("fee waived on staging; salon is live immediately")
    resp = api.get(f"/salons/{salon['id']}")
    assert resp.status_code == 404, f"unpaid salon is public: {resp.status_code}"


def test_vendor_completes_registration(api, world, flow):
    """POST /vendors/complete-registration with the emailed token creates the vendor"""
    req, salon = flow.need("request", "salon")
    # The real token only exists inside the approval email (stateless JWT, not
    # stored); we sign an identical one with the server's secret.
    token = registration_token(world.cfg.jwt_secret, request_id=req["id"], salon_id=salon["id"],
                               email=req["owner_email"], request_type="salon",
                               algorithm=world.cfg.jwt_algorithm)
    body = {"token": token, "full_name": req["owner_name"], "password": world.cfg.password,
            "confirm_password": world.cfg.password, "age": 31, "gender": "male"}
    data = expect(api.post("/vendors/complete-registration", json=body), 200)
    inner = data.get("data") or {}
    assert inner.get("access_token"), f"no token returned: {list(inner)}"
    user = inner.get("user") or {}
    assert user.get("user_role", "vendor") == "vendor", user
    linked = world.db.table("salons").select("vendor_id").eq("id", salon["id"]).single().execute().data
    assert linked["vendor_id"], "salon not linked to the new vendor"
    flow["vendor_token"] = inner["access_token"]
    flow["vendor_email"] = req["owner_email"]
    flow["reg_token"] = token


def test_registration_token_single_use(api, world, flow):
    """Replaying the registration token is refused"""
    req, token = flow.need("request", "reg_token")
    body = {"token": token, "full_name": req["owner_name"], "password": world.cfg.password,
            "confirm_password": world.cfg.password, "age": 31, "gender": "male"}
    resp = api.post("/vendors/complete-registration", json=body)
    assert 400 <= resp.status_code < 500, f"replay -> {resp.status_code}: {resp.text[:300]}"


def test_tampered_registration_token(api, world):
    """Forged registration token is rejected (400)"""
    body = {"token": "eyJhbGciOiJIUzI1NiJ9.eyJ0eXBlIjoicmVnaXN0cmF0aW9uIn0.forged", "full_name": "X Y",
            "password": "Test@1234", "confirm_password": "Test@1234", "age": 30, "gender": "male"}
    resp = api.post("/vendors/complete-registration", json=body)
    assert resp.status_code == 400, f"got {resp.status_code}"


def test_new_vendor_logs_in(api, world, flow):
    """New vendor logs in with the password they set and sees their unpaid salon"""
    email = flow.need("vendor_email")
    sess = world.login(email, world.cfg.password)
    assert (sess.get("user") or {}).get("user_role") == "vendor", sess.get("user")
    salon = expect(api.get("/vendors/salon", token=sess["access_token"]), 200)
    assert salon["id"] == flow["salon"]["id"]
    flow["vendor_token"] = sess["access_token"]
    flow["fee"] = salon.get("registration_fee_amount")
    if not salon.get("registration_fee_paid"):
        assert (salon.get("registration_fee_amount") or 0) > 0, "unpaid salon shows no fee amount"


def test_registration_fee_payment(api, world, flow):
    """Vendor pays the registration fee via Razorpay (create-order -> verify)"""
    token, req, salon = flow.need("vendor_token", "request", "salon")
    if salon.get("registration_fee_paid"):
        pytest.skip("fee waived on staging")
    if not world.cfg.razorpay_enabled:
        resp = api.post("/payments/registration/create-order", token=token, params={"vendor_request_id": req["id"]})
        assert resp.status_code in (503, 500), f"create-order without Razorpay keys -> {resp.status_code}"
        pytest.skip("Razorpay disabled on staging (set E2E_RAZORPAY_ENABLED=1 + E2E_RAZORPAY_KEY_SECRET "
                    f"once TEST keys are in system_config); create-order answered {resp.status_code}: {detail(resp)[:120]}")
    order = expect(api.post("/payments/registration/create-order", token=token,
                            params={"vendor_request_id": req["id"]}), 200)
    assert float(order["amount"]) == float(flow.get("fee") or order["amount"])
    pay_id = "pay_E2E" + world.cfg.run_id[-10:]
    sig = razorpay_signature(world.cfg.razorpay_key_secret, order["order_id"], pay_id)
    expect(api.post("/payments/registration/verify", token=token,
                    json={"razorpay_order_id": order["order_id"], "razorpay_payment_id": pay_id,
                          "razorpay_signature": sig}), 200)
    row = world.db.table("salons").select("registration_fee_paid,is_active").eq("id", salon["id"]).single().execute().data
    assert row["registration_fee_paid"] and row["is_active"], row
    flow["paid"] = True


def test_registration_bad_signature_rejected(api, world, flow):
    """Registration verify with a wrong signature is 400"""
    token = flow.need("vendor_token")
    if not world.cfg.razorpay_enabled:
        pytest.skip("Razorpay disabled on staging (E2E_RAZORPAY_ENABLED!=1)")
    resp = api.post("/payments/registration/verify", token=token,
                    json={"razorpay_order_id": "order_fake", "razorpay_payment_id": "pay_fake", "razorpay_signature": "00"})
    assert resp.status_code == 400, f"got {resp.status_code}"


def test_process_payment_requires_real_payment(api, world, flow):
    """Unpaid vendor cannot self-activate via POST /vendors/process-payment"""
    token, salon = flow.need("vendor_token", "salon")
    if flow.get("paid") or salon.get("registration_fee_paid"):
        pytest.skip("salon already paid - nothing to bypass")
    resp = api.post("/vendors/process-payment", token=token)
    row = world.db.table("salons").select("registration_fee_paid,is_active,is_verified").eq("id", salon["id"]).single().execute().data
    if resp.status_code == 200 and row["registration_fee_paid"]:
        flow["paid"] = True  # the bypass activated it; later steps can rely on that
    # Fixed: the DEMO endpoint answers 403 outside ENVIRONMENT=development.
    assert resp.status_code in (400, 402, 403, 404, 410), f"got {resp.status_code}"
    assert not row["registration_fee_paid"], "process-payment marked the fee paid with no payment"


def test_activated_salon_is_public(api, world, flow):
    """After payment the salon is publicly visible"""
    salon = flow.need("salon")
    if not (flow.get("paid") or salon.get("registration_fee_paid")):
        pytest.skip("salon was never activated in this run")
    row = world.db.table("salons").select("is_verified").eq("id", salon["id"]).single().execute().data
    resp = api.get(f"/salons/{salon['id']}")
    if not row["is_verified"]:
        assert resp.status_code == 404
        pytest.skip("paid but not admin-verified yet: hidden until verification, as designed")
    assert resp.status_code == 200, f"activated salon not public: {resp.status_code}"


def test_admin_lists_and_toggles_salon(api, world, flow):
    """Admin sees the salon in GET /admin/salons/ and can deactivate/reactivate it"""
    salon = flow.need("salon")
    token = world.token("admin")
    data = expect(api.get("/admin/salons/", token=token, params={"limit": 500}), 200)
    rows = data if isinstance(data, list) else (data.get("salons") or data.get("data") or [])
    assert salon["id"] in {r.get("id") for r in rows}, "new salon missing from admin salon list"
    before = world.db.table("salons").select("is_active").eq("id", salon["id"]).single().execute().data["is_active"]
    expect(api.put(f"/admin/salons/{salon['id']}/status", token=token, json={"is_active": not before}), 200)
    expect(api.put(f"/admin/salons/{salon['id']}/status", token=token, json={"is_active": before}), 200)
    after = world.db.table("salons").select("is_active").eq("id", salon["id"]).single().execute().data["is_active"]
    assert after == before


def test_admin_rejects_request(api, world):
    """Admin rejects a second request with a reason; it leaves the pending queue"""
    req = submit_request(api, world, "salon", suffix="-REJ")
    token = world.token("admin")
    resp = api.post(f"/admin/vendor-requests/{req['id']}/reject", token=token, json={})
    assert resp.status_code == 422, f"reject without a reason -> {resp.status_code}"
    expect(api.post(f"/admin/vendor-requests/{req['id']}/reject", token=token,
                    json={"admin_notes": f"E2E rejection {world.cfg.run_id}"}), 200)
    row = world.db.table("vendor_join_requests").select("status").eq("id", req["id"]).single().execute().data
    assert row["status"] == "rejected", row
    salons = world.db.table("salons").select("id").eq("join_request_id", req["id"]).execute().data
    assert not salons, "rejected request produced a salon"
