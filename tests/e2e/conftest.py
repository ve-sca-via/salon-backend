"""
E2E suite plumbing (tests/e2e/ only).

Opt-in: nothing in this directory is even collected unless E2E_RUN=1 or
`--e2e` is on the command line, so the normal `pytest -m "not integration"` /
`pytest -m integration` runs never see (or import) these tests.
`python scripts/run_e2e.py` sets both for you.

This suite NEVER imports `app`: it is an HTTP client of a deployed server plus
a Supabase service-role client for seeding/cleanup. The two autouse fixtures
of tests/conftest.py that touch app internals are overridden below with no-ops.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_E2E_DIR = Path(__file__).resolve().parent
_ENABLED = os.environ.get("E2E_RUN") == "1" or "--e2e" in sys.argv
if not _ENABLED:
    collect_ignore_glob = ["test_*.py"]


def pytest_addoption(parser):
    group = parser.getgroup("e2e", "Lubist end-to-end (deployed environment) suite")
    group.addoption("--e2e", action="store_true", default=False,
                    help="Enable collection of tests/e2e (same as E2E_RUN=1).")
    group.addoption("--base-url", action="store", default=None,
                    help="Server root to test (default: E2E_BASE_URL or staging).")
    group.addoption("--flow", action="store", default=None,
                    help="Comma-separated flow keys to run (e.g. 'buyer,auth').")
    group.addoption("--keep-data", action="store_true", default=False,
                    help="Do not delete this run's per-run data at the end.")
    group.addoption("--allow-prod", action="store_true", default=False,
                    help="DANGEROUS: allow running against a production host.")
    group.addoption("--sweep-stale", action="store_true", default=False,
                    help="Also delete leftovers of ALL previous E2E runs (tag 'E2E-').")


def _opt(config, name, default=None):
    try:
        return config.getoption(name)
    except (ValueError, AttributeError):
        return default


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end test against a deployed environment (tests/e2e)")
    if not _ENABLED:
        return
    from .support.config import ProductionTargetError, load_config
    from .support.report import Collector, git_rev
    try:
        cfg = load_config(
            base_url=_opt(config, "--base-url"),
            keep_data=bool(_opt(config, "--keep-data", False)),
            allow_prod=bool(_opt(config, "--allow-prod", False)),
        )
    except ProductionTargetError as exc:
        raise pytest.UsageError(str(exc))
    config._e2e_cfg = cfg
    collector = Collector()
    collector.meta.update({
        "base_url": cfg.base_url, "run_id": cfg.run_id, "git": git_rev(),
        "payments": "ENABLED (E2E_RAZORPAY_ENABLED=1)" if cfg.razorpay_enabled else "disabled (set E2E_RAZORPAY_ENABLED=1)",
    })
    config._e2e_collector = collector


def pytest_collection_modifyitems(session, config, items):
    if not _ENABLED:
        return
    flows = _opt(config, "--flow")
    wanted = {f.strip() for f in flows.split(",")} if flows else None
    keep, drop = [], []
    for item in items:
        if _E2E_DIR not in item.path.parents:
            keep.append(item)
            continue
        item.add_marker(pytest.mark.e2e)
        flow = getattr(item.module, "FLOW", None)
        if wanted is not None and flow not in wanted:
            drop.append(item)
        else:
            keep.append(item)
    if drop:
        config.hook.pytest_deselected(items=drop)
        items[:] = keep
    collector = getattr(config, "_e2e_collector", None)
    if collector is not None:
        for item in items:
            if getattr(item.module, "FLOW", None):
                collector.register(item)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    collector = getattr(item.config, "_e2e_collector", None)
    if collector is not None:
        collector.record(report)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    collector = getattr(config, "_e2e_collector", None)
    if collector is None or not collector.steps or config.option.collectonly:
        return
    from .support.config import REPORTS_DIR
    for line in collector.console_lines():
        try:
            terminalreporter.write_line(line)
        except UnicodeEncodeError:
            terminalreporter.write_line(line.encode("ascii", "replace").decode())
    path = collector.write(REPORTS_DIR)
    terminalreporter.write_line(f"\nE2E report written to {path}")


# ----------------------------------------------------------------------
# Neutralise tests/conftest.py's app-touching autouse fixtures for this dir.
# ----------------------------------------------------------------------
@pytest.fixture(autouse=True, scope="session")
def _disable_app_rate_limiter():
    yield


@pytest.fixture(autouse=True)
def _clear_config_cache():
    yield


# ----------------------------------------------------------------------
# Core fixtures
# ----------------------------------------------------------------------
@pytest.fixture(scope="session")
def cfg(pytestconfig):
    cfg = getattr(pytestconfig, "_e2e_cfg", None)
    if cfg is None:
        pytest.skip("E2E suite not enabled (set E2E_RUN=1 or pass --e2e)")
    return cfg


@pytest.fixture(scope="session")
def api(cfg):
    from .support.client import ApiClient
    client = ApiClient(cfg.api, min_interval=cfg.min_interval)
    yield client
    client.close()


@pytest.fixture(scope="session")
def world(cfg, api, pytestconfig):
    from .support.world import World
    w = World(cfg, api)
    w.seed()
    collector = getattr(pytestconfig, "_e2e_collector", None)
    if w.seed_error and collector is not None:
        collector.notes.append(f"Seeding fixed accounts failed: {w.seed_error}")
    yield w
    if collector is not None:
        collector.notes.extend(w.notes)
    if w.cfg.missing_seed_secrets():
        return
    if cfg.keep_data:
        if collector is not None:
            collector.notes.append(f"--keep-data: per-run data tagged {cfg.run_id} was left in place.")
        return
    counts = w.cleanup(cfg.run_id)
    if _opt(pytestconfig, "--sweep-stale", False):
        stale = w.cleanup("E2E-")
        for k, v in stale.items():
            counts[k + " (stale)"] = v
    if collector is not None:
        collector.cleanup = counts


class FlowState(dict):
    """Per-flow (module) scratchpad. `need()` skips a step whose prerequisite
    data was never produced because an earlier step failed or was skipped."""

    def need(self, *keys: str):
        missing = [k for k in keys if self.get(k) in (None, "", [])]
        if missing:
            pytest.skip(f"prerequisite not available: {', '.join(missing)} (an earlier step failed or was skipped)")
        values = tuple(self[k] for k in keys)
        return values[0] if len(values) == 1 else values


@pytest.fixture(scope="module")
def flow():
    return FlowState()
