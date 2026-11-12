"""RM flow: dashboard, request list, submit a salon join request, see it, drafts."""
import pytest

from .support.builders import salon_request_payload, submit_request
from .support.client import expect

FLOW = "rm"
FLOW_TITLE = "Relationship manager (RM)"
pytestmark = pytest.mark.e2e


def test_rm_dashboard(api, world):
    """GET /rm/dashboard"""
    data = expect(api.get("/rm/dashboard", token=world.token("rm")), 200)
    assert isinstance(data, dict), data


def test_rm_lists_requests_and_salons(api, world):
    """GET /rm/vendor-requests, /rm/salons, /rm/score-history, /rm/leaderboard"""
    token = world.token("rm")
    data = expect(api.get("/rm/vendor-requests", token=token), 200)
    assert "data" in data, data
    expect(api.get("/rm/salons", token=token), 200)
    expect(api.get("/rm/score-history", token=token), 200)
    expect(api.get("/rm/leaderboard", token=token), 200)


def test_rm_submits_salon_request(api, world, flow):
    """POST /rm/vendor-requests (salon) is accepted as pending"""
    req = submit_request(api, world, "salon")
    assert req.get("status") == "pending", f"status={req.get('status')}"
    assert req.get("request_type") in (None, "salon"), req.get("request_type")
    flow["request"] = req
    world.shared["salon_request"] = req  # admin flow approves this one


def test_rm_sees_request_in_own_list(api, world, flow):
    """Submitted request appears in GET /rm/vendor-requests and GET /rm/vendor-requests/{id}"""
    req = flow.need("request")
    token = world.token("rm")
    data = expect(api.get("/rm/vendor-requests", token=token, params={"status_filter": "pending", "limit": 100}), 200)
    assert req["id"] in {r.get("id") for r in data.get("data") or []}, "request not in RM's pending list"
    one = expect(api.get(f"/rm/vendor-requests/{req['id']}", token=token), 200)
    assert one.get("business_name") == req["business_name"]


def test_rm_duplicate_owner_rejected(api, world, flow):
    """Re-submitting with the same owner email/phone is refused (409)"""
    req = flow.need("request")
    payload = dict(req["_payload"])
    payload["business_name"] = payload["business_name"] + " DUP"
    resp = api.post("/rm/vendor-requests", token=world.token("rm"), params={"is_draft": "false"}, json=payload)
    assert resp.status_code == 409, f"duplicate owner accepted: {resp.status_code} {resp.text[:300]}"


def test_rm_draft_save_and_delete(api, world):
    """RM can save a draft and delete it"""
    payload = salon_request_payload(world, "salon", suffix="-DRAFT")
    token = world.token("rm")
    data = expect(api.post("/rm/vendor-requests", token=token, params={"is_draft": "true"}, json=payload), 200, 201)
    req = data.get("data", data)
    assert req.get("status") == "draft", req.get("status")
    expect(api.delete(f"/rm/vendor-requests/{req['id']}", token=token), 200, 204)
    resp = api.get(f"/rm/vendor-requests/{req['id']}", token=token)
    assert resp.status_code == 404, f"deleted draft still readable: {resp.status_code}"


def test_rm_buyer_request_requires_intake_fields(api, world):
    """regular_buyer request without age/gender/phone-verification is 422"""
    payload = salon_request_payload(world, "regular_buyer", suffix="-BAD")
    for key in ("owner_age", "owner_gender", "owner_phone_verification_token"):
        payload.pop(key, None)
    resp = api.post("/rm/vendor-requests", token=world.token("rm"), params={"is_draft": "false"}, json=payload)
    assert resp.status_code == 422, f"got {resp.status_code}: {resp.text[:300]}"
    text = resp.text
    assert "owner_age" in text and "owner_phone_verification_token" in text, text[:400]


def test_rm_buyer_request_rejects_bad_phone_token(api, world):
    """regular_buyer request whose phone token doesn't match owner_phone is 400"""
    from .support.tokens import phone_verification_token
    payload = salon_request_payload(world, "regular_buyer", suffix="-BADTOKEN")
    payload["owner_phone_verification_token"] = phone_verification_token(
        world.cfg.jwt_secret, "+919999999999", world.cfg.jwt_algorithm)
    resp = api.post("/rm/vendor-requests", token=world.token("rm"), params={"is_draft": "false"}, json=payload)
    assert resp.status_code == 400, f"got {resp.status_code}: {resp.text[:300]}"
