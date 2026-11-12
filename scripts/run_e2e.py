"""
Run the end-to-end API flow suite against a deployed environment (staging by default).

    python scripts/run_e2e.py                      # everything, against staging
    python scripts/run_e2e.py --flow buyer         # one flow (comma-separate for several)
    python scripts/run_e2e.py --keep-data          # leave this run's data for inspection
    python scripts/run_e2e.py --base-url http://localhost:8000
    python scripts/run_e2e.py --sweep-stale        # also delete leftovers of older runs
    python scripts/run_e2e.py -- -x -vv            # anything after `--` goes to pytest

Flows: public, auth, boundaries, rm, admin, buyer, products, booking, vendor, forms

Secrets come from tests/e2e/.env.staging (or E2E_* environment variables) - see
docs/E2E_TESTING.md. A checklist summary is printed at the end and a markdown
report is written to tests/e2e/reports/<timestamp>.md.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOWS = ["public", "auth", "boundaries", "rm", "admin", "buyer", "products", "booking", "vendor", "forms"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", help="server root (default: E2E_BASE_URL or staging)")
    parser.add_argument("--flow", help=f"comma-separated subset of: {', '.join(FLOWS)}")
    parser.add_argument("--keep-data", action="store_true", help="skip per-run cleanup")
    parser.add_argument("--sweep-stale", action="store_true", help="also delete data left by older runs")
    parser.add_argument("--allow-prod", action="store_true", help="DANGEROUS: permit a production target")
    parser.add_argument("pytest_args", nargs="*", help="extra pytest args (after --)")
    args = parser.parse_args()

    if args.flow:
        unknown = [f for f in args.flow.split(",") if f.strip() not in FLOWS]
        if unknown:
            parser.error(f"unknown flow(s): {unknown}; choose from {FLOWS}")

    cmd = [sys.executable, "-m", "pytest", "tests/e2e", "--e2e",
           # Don't load tests/conftest.py (it force-loads dummy tests/test.env and
           # imports app internals for the unit tiers) - this suite is HTTP-only.
           "--confcutdir", str(ROOT / "tests" / "e2e"),
           "-p", "no:cacheprovider", "-q", "-rN", "--tb=short", "-o", "console_output_style=classic"]
    if args.base_url:
        cmd += ["--base-url", args.base_url]
    if args.flow:
        cmd += ["--flow", args.flow]
    if args.keep_data:
        cmd.append("--keep-data")
    if args.sweep_stale:
        cmd.append("--sweep-stale")
    if args.allow_prod:
        cmd.append("--allow-prod")
    cmd += args.pytest_args

    env = {**os.environ, "E2E_RUN": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    print("+", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=ROOT, env=env)


if __name__ == "__main__":
    sys.exit(main())
