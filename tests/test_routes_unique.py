import pytest

from main import app


def _route_key(route):
    # Normalize path by removing path parameters style differences
    return (route.path, tuple(sorted(route.methods or [])))


def test_no_duplicate_path_method_pairs():
    seen = set()
    duplicates = []
    for route in app.routes:
        # skip docs/static routes if any
        if getattr(route, "include_in_schema", True) is False:
            continue
        key = _route_key(route)
        if key in seen:
            duplicates.append(key)
        else:
            seen.add(key)

    assert not duplicates, f"Duplicate (path,methods) entries found: {duplicates}"


def test_unique_operation_ids():
    opids = {}
    duplicates = []
    for route in app.routes:
        opid = getattr(route, "operation_id", None)
        if not opid:
            # fallback to endpoint name
            opid = getattr(route.endpoint, "__name__", None)
        if not opid:
            continue
        if opid in opids:
            duplicates.append((opid, opids[opid], route.path))
        else:
            opids[opid] = route.path

    assert not duplicates, f"Duplicate operation ids found: {duplicates}"
