"""
Fail CI when a change to openapi/openapi.json would break an installed client.

Mobile builds live on phones for months, so the backend must stay
backward-compatible with every app version still above the minimum supported
version (docs/CLIENT_APPS_AND_VERSIONING.md, "API compatibility rules"). This
compares the committed contract against the one on the PR's base branch and
reports, as BREAKING:

  * a removed path or HTTP method;
  * a removed 2xx response status, or a removed field in a 2xx JSON response;
  * a response field whose type widened (e.g. string -> string|null, which a
    client typed `string` cannot handle) or changed;
  * a request field or parameter that is newly required;
  * a request field or parameter whose accepted types or enum values narrowed;
  * a request body that became required.

Additive changes (new paths, new optional inputs, new response fields) pass.

Override for an intentional break (e.g. removing an endpoint no supported build
calls any more): put `[breaking-api-ok]` in a commit message on the branch, or
label the PR `breaking-api-ok` (the workflow passes labels in PR_LABELS), or set
API_BREAKING_OK=1. The report is still printed so the reviewer sees it.

Usage (from backend/):
    python scripts/check_api_breaking.py --base-ref origin/staging
    python scripts/check_api_breaking.py --base-file old.json [--head-file new.json]

Exit codes: 0 = compatible / overridden / no base contract, 1 = breaking.
Pure Python, stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = "openapi/openapi.json"
OVERRIDE_TOKEN = "[breaking-api-ok]"
OVERRIDE_LABEL = "breaking-api-ok"
HTTP_METHODS = ("get", "put", "post", "delete", "patch", "options", "head", "trace")

Schema = Dict[str, Any]


# =====================================================
# SCHEMA HELPERS
# =====================================================

class Spec:
    def __init__(self, doc: Dict[str, Any]):
        self.doc = doc
        self.schemas = (doc.get("components") or {}).get("schemas") or {}

    def resolve(self, schema: Optional[Schema]) -> Tuple[Optional[str], Schema]:
        """Follow $ref chains. Returns (last ref name or None, schema)."""
        name = None
        seen = set()
        schema = schema or {}
        while isinstance(schema, dict) and "$ref" in schema:
            ref = schema["$ref"]
            if ref in seen:
                break
            seen.add(ref)
            name = ref.rsplit("/", 1)[-1]
            schema = self.schemas.get(name, {})
        return name, schema if isinstance(schema, dict) else {}


def _non_null_members(schema: Schema) -> List[Schema]:
    members = schema.get("anyOf") or schema.get("oneOf") or []
    return [m for m in members if not (isinstance(m, dict) and m.get("type") == "null")]


def type_set(spec: Spec, schema: Optional[Schema], depth: int = 0) -> Set[str]:
    """The JSON types a schema admits. 'any' means unconstrained."""
    _, s = spec.resolve(schema)
    if depth > 20 or not s:
        return {"any"}
    if "anyOf" in s or "oneOf" in s:
        out: Set[str] = set()
        for member in s.get("anyOf") or s.get("oneOf") or []:
            out |= type_set(spec, member, depth + 1)
        return out
    if "allOf" in s:
        members = s["allOf"]
        return type_set(spec, members[0], depth + 1) if len(members) == 1 else {"object"}
    t = s.get("type")
    out = set(t) if isinstance(t, list) else ({t} if t else set())
    if s.get("nullable"):
        out.add("null")
    if not out:
        if "properties" in s:
            return {"object"}
        if "items" in s:
            return {"array"}
        return {"any"}
    return out


def object_shape(spec: Spec, schema: Optional[Schema]) -> Tuple[Dict[str, Schema], Set[str], bool]:
    """(properties, required, is_object) - merging allOf and unwrapping Optional[Model]."""
    _, s = spec.resolve(schema)
    if "allOf" in s:
        props: Dict[str, Schema] = {}
        required: Set[str] = set()
        is_obj = False
        for member in s["allOf"]:
            p, r, o = object_shape(spec, member)
            props.update(p)
            required |= r
            is_obj = is_obj or o
        return props, required, is_obj
    members = _non_null_members(s)
    if ("anyOf" in s or "oneOf" in s) and len(members) == 1:
        return object_shape(spec, members[0])
    props = s.get("properties") or {}
    return props, set(s.get("required") or []), bool(props) or s.get("type") == "object"


def array_items(spec: Spec, schema: Optional[Schema]) -> Optional[Schema]:
    _, s = spec.resolve(schema)
    members = _non_null_members(s)
    if ("anyOf" in s or "oneOf" in s) and len(members) == 1:
        return array_items(spec, members[0])
    return s.get("items") if s.get("type") == "array" or "items" in s else None


def enum_values(spec: Spec, schema: Optional[Schema]) -> Optional[Set[str]]:
    _, s = spec.resolve(schema)
    members = _non_null_members(s)
    if ("anyOf" in s or "oneOf" in s) and len(members) == 1:
        return enum_values(spec, members[0])
    if "enum" in s:
        return {json.dumps(v, sort_keys=True) for v in s["enum"]}
    return None


def _fmt(types: Set[str]) -> str:
    return "|".join(sorted(types))


# =====================================================
# COMPARISON
# =====================================================

class Checker:
    def __init__(self, old: Dict[str, Any], new: Dict[str, Any]):
        self.old = Spec(old)
        self.new = Spec(new)
        self.problems: List[str] = []
        self._seen: Set[Tuple[str, str, str]] = set()

    def report(self, where: str, what: str) -> None:
        self.problems.append(f"{where}: {what}")

    # -- schemas --------------------------------------------------------

    def compare_schema(self, old: Schema, new: Schema, where: str, direction: str) -> None:
        """direction: 'response' (server -> client) or 'request' (client -> server)."""
        old_ref, _ = self.old.resolve(old)
        new_ref, _ = self.new.resolve(new)
        if old_ref and new_ref:
            # A recursive or widely shared model is walked once per (old, new,
            # direction) pair; its problems are reported at the first place
            # it is reached, which is enough to fail the check.
            pair = (old_ref, new_ref, direction)
            if pair in self._seen:
                return
            self._seen.add(pair)

        old_types = type_set(self.old, old)
        new_types = type_set(self.new, new)
        if "any" not in old_types and "any" not in new_types:
            if direction == "response" and not new_types <= old_types:
                self.report(where, f"response type changed {_fmt(old_types)} -> {_fmt(new_types)}")
            if direction == "request" and not old_types <= new_types:
                self.report(where, f"accepted type narrowed {_fmt(old_types)} -> {_fmt(new_types)}")

        if direction == "request":
            old_enum = enum_values(self.old, old)
            new_enum = enum_values(self.new, new)
            if old_enum is not None and new_enum is not None and not old_enum <= new_enum:
                removed = ", ".join(sorted(old_enum - new_enum))
                self.report(where, f"accepted enum values removed: {removed}")

        old_props, old_req, old_is_obj = object_shape(self.old, old)
        new_props, new_req, _ = object_shape(self.new, new)
        if old_is_obj:
            if direction == "response":
                for name in sorted(old_props):
                    if name not in new_props:
                        self.report(f"{where}.{name}", "response field removed")
            else:
                for name in sorted(new_req - old_req):
                    self.report(f"{where}.{name}", "request field is newly required")
            for name in sorted(set(old_props) & set(new_props)):
                self.compare_schema(old_props[name], new_props[name], f"{where}.{name}", direction)

        old_items = array_items(self.old, old)
        new_items = array_items(self.new, new)
        if old_items is not None and new_items is not None:
            self.compare_schema(old_items, new_items, f"{where}[]", direction)

    # -- operations -----------------------------------------------------

    @staticmethod
    def _json_schema(content: Optional[Dict[str, Any]]) -> Optional[Schema]:
        if not content:
            return None
        for media in ("application/json", *content.keys()):
            if media in content:
                return (content[media] or {}).get("schema")
        return None

    def compare_operation(self, label: str, old_op: Dict[str, Any], new_op: Dict[str, Any]) -> None:
        # Parameters (query/path/header/cookie)
        old_params = {(p.get("in"), p.get("name")): p for p in old_op.get("parameters", []) if "name" in p}
        new_params = {(p.get("in"), p.get("name")): p for p in new_op.get("parameters", []) if "name" in p}
        for key, param in new_params.items():
            if key[0] == "path":
                continue  # path params are matched positionally via the path template
            was = old_params.get(key)
            if param.get("required") and not (was and was.get("required")):
                self.report(f"{label} {key[0]} param '{key[1]}'", "parameter is newly required")
        for key in set(old_params) & set(new_params):
            self.compare_schema(
                old_params[key].get("schema") or {}, new_params[key].get("schema") or {},
                f"{label} {key[0]} param '{key[1]}'", "request",
            )

        # Request body
        old_body = old_op.get("requestBody") or {}
        new_body = new_op.get("requestBody") or {}
        if new_body.get("required") and not old_body.get("required"):
            self.report(f"{label} request body", "request body is newly required")
        old_schema = self._json_schema(old_body.get("content"))
        new_schema = self._json_schema(new_body.get("content"))
        if old_schema is not None and new_schema is not None:
            self.compare_schema(old_schema, new_schema, f"{label} request", "request")

        # Responses (2xx only - error shapes are shared and versioned separately)
        old_responses = {k: v for k, v in (old_op.get("responses") or {}).items() if str(k).startswith("2")}
        new_responses = {k: v for k, v in (new_op.get("responses") or {}).items() if str(k).startswith("2")}
        for code, old_resp in old_responses.items():
            if code not in new_responses:
                self.report(f"{label} response {code}", "success status removed")
                continue
            o = self._json_schema(old_resp.get("content"))
            n = self._json_schema(new_responses[code].get("content"))
            if o is not None and n is not None:
                self.compare_schema(o, n, f"{label} response {code}", "response")

    def run(self) -> List[str]:
        def normalise(path: str) -> str:
            return re.sub(r"\{[^}]+\}", "{}", path)

        new_doc_paths = self.new.doc.get("paths") or {}
        # Renaming a path parameter ({id} -> {salon_id}) is invisible to
        # clients, so fall back to matching on the template shape. Several
        # templates can share a shape (/blog/{slug} GET, /blog/{post_id} PUT),
        # so their methods are merged.
        by_shape: Dict[str, Dict[str, Any]] = {}
        for p, item in new_doc_paths.items():
            by_shape.setdefault(normalise(p), {}).update(item)
        for path, old_item in sorted((self.old.doc.get("paths") or {}).items()):
            new_item = new_doc_paths.get(path)
            if new_item is None or any(m in old_item and m not in new_item for m in HTTP_METHODS):
                new_item = by_shape.get(normalise(path))
            if new_item is None:
                self.report(path, "path removed")
                continue
            for method in HTTP_METHODS:
                if method not in old_item:
                    continue
                label = f"{method.upper()} {path}"
                if method not in new_item:
                    self.report(label, "method removed")
                    continue
                self.compare_operation(label, old_item[method], new_item[method])
        return self.problems


def find_breaking_changes(old: Dict[str, Any], new: Dict[str, Any]) -> List[str]:
    return Checker(old, new).run()


# =====================================================
# CLI
# =====================================================

def _git(*args: str) -> Optional[str]:
    try:
        proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    except FileNotFoundError:
        return None
    return proc.stdout if proc.returncode == 0 else None


def override_reason(base_ref: Optional[str]) -> Optional[str]:
    if os.environ.get("API_BREAKING_OK", "").strip().lower() in ("1", "true", "yes"):
        return "API_BREAKING_OK is set"
    labels = [l.strip() for l in os.environ.get("PR_LABELS", "").split(",")]
    if OVERRIDE_LABEL in labels:
        return f"PR is labelled '{OVERRIDE_LABEL}'"
    if base_ref:
        log = _git("log", f"{base_ref}..HEAD", "--format=%B")
        if log and OVERRIDE_TOKEN in log:
            return f"a commit message contains {OVERRIDE_TOKEN}"
    return None


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--base-ref", help="git ref holding the old contract, e.g. origin/staging")
    group.add_argument("--base-file", help="path to the old contract")
    parser.add_argument("--head-file", default=str(ROOT / CONTRACT), help="path to the new contract")
    args = parser.parse_args(argv)

    if args.base_file:
        base_text = Path(args.base_file).read_text(encoding="utf-8")
    else:
        base_text = _git("show", f"{args.base_ref}:{CONTRACT}")
        if base_text is None:
            print(f"No {CONTRACT} on {args.base_ref}; nothing to compare against (first contract). OK.")
            return 0

    old = json.loads(base_text)
    new = json.loads(Path(args.head_file).read_text(encoding="utf-8"))
    problems = find_breaking_changes(old, new)

    if not problems:
        print("No breaking API changes against the base contract.")
        return 0

    print(f"{len(problems)} breaking API change(s):")
    for problem in problems:
        print(f"  - {problem}")
    reason = override_reason(args.base_ref)
    if reason:
        print(f"\nAllowed because {reason}. Make sure every supported app build is unaffected.")
        return 0
    print(
        "\nInstalled app versions may still depend on these. Make the change additive "
        "(see docs/CLIENT_APPS_AND_VERSIONING.md, 'API compatibility rules'), or, if the "
        f"break is intentional and no supported build is affected, add {OVERRIDE_TOKEN} to a "
        f"commit message or label the PR '{OVERRIDE_LABEL}'.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
