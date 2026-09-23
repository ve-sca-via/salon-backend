"""
Query Better Stack logs from the command line.

Better Stack's only read path is the ClickHouse-backed SQL API; the old
`/api/v1/query` REST endpoints were removed and now 404. Credentials come from
`.betterstack.env` in the repo root (gitignored) or from the environment.

Required settings:
    BETTERSTACK_SQL_USER
    BETTERSTACK_SQL_PASSWORD
    BETTERSTACK_SQL_ENDPOINT     e.g. https://eu-central-1a-connect.betterstackdata.com
    BETTERSTACK_SQL_TABLE        e.g. t506833_lubist_logs (first entry is used)

Usage:
    python scripts/betterstack_query.py --schema
    python scripts/betterstack_query.py --sample 20
    python scripts/betterstack_query.py --errors --hours 24
    python scripts/betterstack_query.py --endpoints --hours 24
    python scripts/betterstack_query.py --sql "SELECT count() FROM {table}"

`{table}` is substituted with `remote(<BETTERSTACK_SQL_TABLE>)` in --sql.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import httpx

ENV_FILE = Path(__file__).resolve().parent.parent / ".betterstack.env"


def load_settings() -> dict:
    """Read credentials from .betterstack.env, falling back to the environment."""
    values = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")

    for key in (
        "BETTERSTACK_SQL_USER",
        "BETTERSTACK_SQL_PASSWORD",
        "BETTERSTACK_SQL_ENDPOINT",
        "BETTERSTACK_SQL_TABLE",
    ):
        values.setdefault(key, os.environ.get(key, ""))

    missing = [k for k, v in values.items() if not v and k.startswith("BETTERSTACK_SQL")]
    if missing:
        sys.exit(f"Missing required settings: {', '.join(missing)}\nChecked {ENV_FILE}")

    # The table setting may list several tables; queries here target logs.
    values["TABLE"] = values["BETTERSTACK_SQL_TABLE"].split(",")[0].strip()
    return values


def run_sql(cfg: dict, sql: str) -> str:
    """POST a query to the SQL API and return the raw response body."""
    # Do NOT add ?output_format_pretty_row_numbers=0 to this URL. Better Stack's
    # proxy rejects that documented parameter with a pre-auth HTTP 500
    # ("Failed to connect: fetch failed"), which looks like a credential fault
    # but is not. Formatting is controlled by the FORMAT clause instead.
    response = httpx.post(
        cfg["BETTERSTACK_SQL_ENDPOINT"].rstrip("/") + "/",
        content=sql.encode("utf-8"),
        headers={"Content-Type": "text/plain"},
        auth=(cfg["BETTERSTACK_SQL_USER"], cfg["BETTERSTACK_SQL_PASSWORD"]),
        timeout=120.0,
    )
    if response.status_code != 200:
        sys.exit(
            f"Query failed (HTTP {response.status_code}): {response.text.strip()}\n"
            "A 403 means the username/password are wrong. A 500 "
            "'Failed to connect: fetch failed' means the SQL API connection exists "
            "but Better Stack cannot reach the cluster behind it -- recreate the "
            "connection under Integrations -> SQL API and confirm the team is selected."
        )
    return response.text


def print_rows(body: str) -> None:
    """Pretty-print a JSONEachRow response."""
    rows = [json.loads(line) for line in body.splitlines() if line.strip()]
    if not rows:
        print("(no rows)")
        return
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))
    print(f"\n{len(rows)} row(s)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Query Better Stack logs.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--schema", action="store_true", help="show the table columns")
    group.add_argument("--sample", type=int, metavar="N", help="show N most recent rows")
    group.add_argument("--errors", action="store_true", help="recent ERROR-level rows")
    group.add_argument("--endpoints", action="store_true", help="failing endpoints by count")
    group.add_argument("--sql", metavar="QUERY", help="run an arbitrary SQL query")
    parser.add_argument("--hours", type=int, default=24, help="lookback window (default 24)")
    args = parser.parse_args()

    cfg = load_settings()
    table = f"remote({cfg['TABLE']})"
    since = f"dt > now() - INTERVAL {args.hours} HOUR"

    if args.schema:
        sql = f"DESCRIBE TABLE {table} FORMAT JSONEachRow"
    elif args.sample is not None:
        sql = f"SELECT * FROM {table} ORDER BY dt DESC LIMIT {args.sample} FORMAT JSONEachRow"
    elif args.errors:
        # The app emits JSON per line; Better Stack exposes parsed fields under
        # the JSON column. Extracting from `raw` works regardless of how the
        # source is configured to flatten them.
        sql = (
            f"SELECT dt, raw FROM {table} "
            f"WHERE {since} AND position(raw, '\"level\":\"ERROR\"') > 0 "
            f"ORDER BY dt DESC LIMIT 100 FORMAT JSONEachRow"
        )
    elif args.endpoints:
        sql = (
            f"SELECT JSONExtractString(raw, 'path') AS path, "
            f"JSONExtractInt(raw, 'status_code') AS status_code, count() AS hits "
            f"FROM {table} WHERE {since} AND status_code >= 400 "
            f"GROUP BY path, status_code ORDER BY hits DESC LIMIT 50 FORMAT JSONEachRow"
        )
    else:
        sql = args.sql.replace("{table}", table)
        if "FORMAT" not in sql.upper():
            sql += " FORMAT JSONEachRow"

    print_rows(run_sql(cfg, sql))


if __name__ == "__main__":
    main()
