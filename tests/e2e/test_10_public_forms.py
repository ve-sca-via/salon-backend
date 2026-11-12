"""Public lead forms: partner-with-us (1 admin email per run) and careers
(validation + admin listing only - a real application uploads a resume to
Cloudinary and emails HR, so the happy path is in MANUAL_QA_CHECKLIST.md)."""
import pytest

from .support.client import expect

FLOW = "forms"
FLOW_TITLE = "Partner-with-us & careers forms"
pytestmark = pytest.mark.e2e


def test_partner_apply(api, world, flow):
    """POST /partners/apply (public) stores the lead"""
    body = {"owner_name": "E2E Partner Owner", "shop_name": f"E2E Partner Shop {world.cfg.run_id}",
            "shop_type": "Salon", "email": f"e2e.partner+{world.cfg.run_tag}@example.com",
            "phone": "9000000004", "location": "Indiranagar, Bengaluru"}
    data = expect(api.post("/partners/apply", json=body), 200, 201)
    lead = data.get("data") or data.get("request") or data
    flow["lead_id"] = lead.get("id") or (world.db.table("partner_requests").select("id")
                                         .eq("shop_name", body["shop_name"]).single().execute().data["id"])


def test_partner_apply_validation(api):
    """Invalid shop_type / email is 422 (no lead, no email)"""
    resp = api.post("/partners/apply", json={"owner_name": "x", "shop_name": "x", "shop_type": "Casino",
                                             "email": "not-an-email", "phone": "1", "location": "x"})
    assert resp.status_code == 422, resp.status_code


def test_admin_reviews_partner_lead(api, world, flow):
    """Admin finds the lead and marks it contacted"""
    lead_id = flow.need("lead_id")
    token = world.token("admin")
    data = expect(api.get("/partners/requests", token=token, params={"search": world.cfg.run_id}), 200)
    assert lead_id in str(data), "lead missing from admin list"
    expect(api.patch(f"/partners/requests/{lead_id}", token=token,
                     json={"status": "contacted", "admin_notes": "E2E"}), 200)
    row = world.db.table("partner_requests").select("status").eq("id", lead_id).single().execute().data
    assert row["status"] == "contacted"


def test_careers_validation(api):
    """POST /careers/apply without the required fields/files is 422"""
    resp = api.post("/careers/apply", data={"full_name": "E2E"})
    assert resp.status_code == 422, resp.status_code


def test_admin_lists_career_applications(api, world):
    """GET /careers/applications (admin)"""
    expect(api.get("/careers/applications", token=world.token("admin"), params={"limit": 5}), 200)
