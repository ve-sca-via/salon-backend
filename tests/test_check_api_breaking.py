"""
Tests for scripts/check_api_breaking.py - the CI gate that keeps the API
backward-compatible with installed mobile builds.

Runs against the real committed contract (openapi/openapi.json) with targeted
mutations, so the checker is exercised on the shapes FastAPI actually emits
($ref models, anyOf-null Optionals, allOf, arrays). No marker -> fast job.
"""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("check_api_breaking", ROOT / "scripts" / "check_api_breaking.py")
cab = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cab)


@pytest.fixture(scope="module")
def contract():
    path = ROOT / "openapi" / "openapi.json"
    if not path.exists():
        pytest.skip("openapi/openapi.json not generated")
    return json.loads(path.read_text(encoding="utf-8"))


def _schemas(doc):
    return doc["components"]["schemas"]


def test_identical_contract_is_compatible(contract):
    assert cab.find_breaking_changes(contract, copy.deepcopy(contract)) == []


def test_added_path_and_optional_field_are_compatible(contract):
    new = copy.deepcopy(contract)
    new["paths"]["/api/v1/brand-new"] = {"get": {"responses": {"200": {"description": "ok"}}}}
    _schemas(new)["LoginRequest"]["properties"]["device_name"] = {"type": "string"}
    _schemas(new)["LoginResponse"]["properties"]["extra"] = {"type": "string"}
    assert cab.find_breaking_changes(contract, new) == []


def test_removed_path_and_method(contract):
    new = copy.deepcopy(contract)
    del new["paths"]["/api/v1/app-config"]
    del new["paths"]["/api/v1/auth/login"]["post"]
    problems = cab.find_breaking_changes(contract, new)
    assert any("/api/v1/app-config: path removed" in p for p in problems)
    assert any("POST /api/v1/auth/login: method removed" in p for p in problems)


def test_path_param_rename_is_not_a_removal(contract):
    new = copy.deepcopy(contract)
    paths = new["paths"]
    old_key = next(p for p in paths if "{" in p)
    paths[old_key.replace("{", "{renamed_")] = paths.pop(old_key)
    assert cab.find_breaking_changes(contract, new) == []


def test_removed_response_field(contract):
    new = copy.deepcopy(contract)
    del _schemas(new)["LoginResponse"]["properties"]["refresh_token"]
    problems = cab.find_breaking_changes(contract, new)
    assert any(p.endswith(".refresh_token: response field removed") for p in problems), problems


def test_response_type_change_and_nullable_widening(contract):
    new = copy.deepcopy(contract)
    props = _schemas(new)["AppConfigResponse"]["properties"]
    props["update_required"] = {"type": "string"}
    props["client_app"] = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    problems = cab.find_breaking_changes(contract, new)
    assert any("update_required: response type changed boolean -> string" in p for p in problems), problems
    assert any("client_app: response type changed string -> null|string" in p for p in problems), problems


def test_newly_required_request_field(contract):
    new = copy.deepcopy(contract)
    login = _schemas(new)["LoginRequest"]
    login["properties"]["otp"] = {"type": "string"}
    login["required"] = login.get("required", []) + ["otp"]
    problems = cab.find_breaking_changes(contract, new)
    assert any(p.endswith(".otp: request field is newly required") for p in problems), problems


def test_request_type_narrowing_vs_widening(contract):
    narrowed = copy.deepcopy(contract)
    _schemas(narrowed)["LoginRequest"]["properties"]["password"] = {"type": "integer"}
    assert any("password: accepted type narrowed" in p for p in cab.find_breaking_changes(contract, narrowed))

    widened = copy.deepcopy(contract)
    _schemas(widened)["LoginRequest"]["properties"]["password"] = {
        "anyOf": [{"type": "string"}, {"type": "null"}]
    }
    assert cab.find_breaking_changes(contract, widened) == []


def test_newly_required_query_param(contract):
    new = copy.deepcopy(contract)
    params = new["paths"]["/api/v1/app-config"]["get"]["parameters"]
    params[0]["required"] = True
    params.append({"in": "query", "name": "brand_new", "required": True, "schema": {"type": "string"}})
    problems = cab.find_breaking_changes(contract, new)
    assert any("param 'brand_new': parameter is newly required" in p for p in problems)
    assert any(f"param '{params[0]['name']}': parameter is newly required" in p for p in problems)


def test_request_enum_narrowing():
    old = {"paths": {"/x": {"post": {"requestBody": {"content": {"application/json": {"schema": {
        "type": "object", "properties": {"kind": {"type": "string", "enum": ["a", "b"]}}}}}},
        "responses": {"200": {"description": "ok"}}}}}}
    new = copy.deepcopy(old)
    new["paths"]["/x"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"]["kind"]["enum"] = ["a"]
    problems = cab.find_breaking_changes(old, new)
    assert problems and "enum values removed" in problems[0]


def test_removed_success_status():
    old = {"paths": {"/x": {"post": {"responses": {"200": {"description": "ok"}}}}}}
    new = {"paths": {"/x": {"post": {"responses": {"201": {"description": "ok"}}}}}}
    assert cab.find_breaking_changes(old, new) == ["POST /x response 200: success status removed"]


def test_recursive_models_terminate():
    node = {"type": "object", "properties": {"child": {"$ref": "#/components/schemas/Node"}}}
    doc = {
        "components": {"schemas": {"Node": node}},
        "paths": {"/t": {"get": {"responses": {"200": {"content": {"application/json": {
            "schema": {"$ref": "#/components/schemas/Node"}}}}}}}},
    }
    assert cab.find_breaking_changes(doc, copy.deepcopy(doc)) == []


def test_cli_override_and_exit_codes(tmp_path, monkeypatch, contract):
    base = tmp_path / "base.json"
    head = tmp_path / "head.json"
    base.write_text(json.dumps(contract), encoding="utf-8")
    broken = copy.deepcopy(contract)
    del broken["paths"]["/api/v1/app-config"]
    head.write_text(json.dumps(broken), encoding="utf-8")

    monkeypatch.delenv("API_BREAKING_OK", raising=False)
    monkeypatch.delenv("PR_LABELS", raising=False)
    assert cab.main(["--base-file", str(base), "--head-file", str(head)]) == 1
    monkeypatch.setenv("PR_LABELS", "chore,breaking-api-ok")
    assert cab.main(["--base-file", str(base), "--head-file", str(head)]) == 0
    monkeypatch.delenv("PR_LABELS")
    monkeypatch.setenv("API_BREAKING_OK", "1")
    assert cab.main(["--base-file", str(base), "--head-file", str(head)]) == 0
    monkeypatch.delenv("API_BREAKING_OK")
    assert cab.main(["--base-file", str(base), "--head-file", str(base)]) == 0


def test_missing_base_contract_passes(monkeypatch, contract):
    monkeypatch.setattr(cab, "_git", lambda *args: None)
    assert cab.main(["--base-ref", "origin/nowhere"]) == 0
