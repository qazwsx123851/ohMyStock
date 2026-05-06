"""One-time backfill of ``rs_rating_cache`` for the last N trading days.

Spec: openspec/changes/rs-percentile-finmind-wiring/specs/rs-percentile/spec.md
      ("Backfill entrypoint is range-bounded, idempotent, and verifies row count")

Usage::

    python scripts/backfill_rs_rating.py --days 252

Behavior:

* Wires the production universe-closes loader (same call as the FastAPI
  lifespan).
* Walks back ``--days`` business days from today (TPE timezone),
  oldest-to-newest.
* Calls ``compute_rs_rating("2330", asof)`` per day to trigger a full-
  universe compute and cache write. ``2330`` (TSMC) is a stable trigger
  symbol that will remain in the universe across the full range.
* Prints ``asof | universe_size | elapsed_ms`` per day.
* After the loop, asserts ``COUNT(*) FROM rs_rating_cache WHERE asof_date BETWEEN ? AND ?``
  is at least ``days * 100`` (sanity floor — real value is closer to
  ``days * ~1500``). On floor failure, exits non-zero with the actual count.
* Re-running over the same range is idempotent: cache hits short-circuit
  ``compute_rs_rating`` before any write, so the row count stays the same.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta, timezone

from ohmystock.api.db import get_connection
from ohmystock.data.disposition import fetch_disposition_set
from ohmystock.sepa.rs import compute_rs_rating, init_schema, set_universe_closes_loader
from ohmystock.sepa.rs_loader import build_universe_closes_loader

_TPE_TZ = timezone(timedelta(hours=8))
_TRIGGER_SYMBOL = "2330"
_FLOOR_PER_DAY = 100


def _walk_back_business_days(today: date, days: int) -> list[date]:
    """Return ``days`` Mon-Fri dates ending at ``today``, oldest-to-newest.

    Holidays are not subtracted; the row-count floor in ``run_backfill``
    swallows holiday no-ops as long as ~most days return data.
    """
    out: list[date] = []
    cursor = today
    while len(out) < days:
        if cursor.weekday() < 5:
            out.append(cursor)
        cursor -= timedelta(days=1)
    out.reverse()
    return out


def wire_production_loader() -> None:
    """Install the production loader (mirrors `api.app._lifespan`)."""
    set_universe_closes_loader(
        build_universe_closes_loader(disposition_fetcher=fetch_disposition_set)
    )


def run_backfill(
    *,
    days: int,
    today: date | None = None,
    conn: sqlite3.Connection | None = None,
) -> int:
    """Run the backfill loop. Returns a process exit code (0 = success).

    ``today``: override "today" for tests / determinism (default: TPE today).
    ``conn``:  optional shared SQLite connection (default: open via api.db).
    """
    if today is None:
        today = datetime.now(_TPE_TZ).date()
    asofs = _walk_back_business_days(today, days)
    floor = days * _FLOOR_PER_DAY

    owns_conn = conn is None
    c = get_connection() if owns_conn else conn
    try:
        init_schema(c)
        first_iso, last_iso = asofs[0].isoformat(), asofs[-1].isoformat()

        for asof in asofs:
            t0 = time.perf_counter()
            compute_rs_rating(_TRIGGER_SYMBOL, asof, conn=c)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            row = c.execute(
                "SELECT COUNT(*) FROM rs_rating_cache WHERE asof_date = ?",
                (asof.isoformat(),),
            ).fetchone()
            universe_size = int(row[0]) if row else 0
            print(f"{asof.isoformat()} | {universe_size} | {elapsed_ms}ms")

        total = c.execute(
            "SELECT COUNT(*) FROM rs_rating_cache "
            "WHERE asof_date BETWEEN ? AND ?",
            (first_iso, last_iso),
        ).fetchone()[0]
        if int(total) < floor:
            print(
                f"FAIL: rs_rating_cache rows in [{first_iso}, {last_iso}] = "
                f"{total}, expected >= {floor}",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {total} rows in [{first_iso}, {last_iso}] (floor {floor})")
        return 0
    finally:
        if owns_conn:
            c.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill rs_rating_cache for the last N trading days."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=252,
        help="Number of business days to walk back (default: 252).",
    )
    args = parser.parse_args(argv)
    if args.days <= 0:
        parser.error("--days must be a positive integer")

    wire_production_loader()
    return run_backfill(days=args.days)


if __name__ == "__main__":
    sys.exit(main())
