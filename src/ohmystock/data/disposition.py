"""Disposition-list interface + cache for the rs-percentile universe filter.

Spec: openspec/changes/rs-percentile-finmind-wiring/specs/rs-percentile/spec.md
      ("Disposition list interface and cache table ship; live TWSE/OTC scrape is deferred")

This module ships the **stable interface** that the rest of the
rs-percentile wiring is built against:

* The ``disposition_list_cache`` table (created idempotently via
  ``init_schema``) holds `(asof_date, symbol)` rows for any cached
  disposition lists.
* ``fetch_disposition_set(asof, *, conn=None) -> set[str]`` is the single
  callable consumed by ``ohmystock.sepa.rs_loader``. Cache hit returns the
  cached set. **Cache miss returns ``set()``** — no upstream scrape is
  attempted in this change. The function never raises.

The actual TWSE 處置股 + OTC 全額交割 scrape (with graceful degrade to
last-known-set) is deferred to a follow-up change
``rs-percentile-disposition-scrape-impl`` that replaces the cache-miss
branch of ``fetch_disposition_set``. The follow-up MUST preserve the
no-raise contract documented here, so the rs-percentile pipeline never
crashes on a flaky or unreachable upstream.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from ohmystock.api.db import get_connection

__all__ = [
    "init_schema",
    "fetch_disposition_set",
]


_DDL_DISPOSITION_CACHE = """
CREATE TABLE IF NOT EXISTS disposition_list_cache (
    asof_date  TEXT NOT NULL,
    symbol     TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (asof_date, symbol)
)
""".strip()


def init_schema(conn: sqlite3.Connection) -> None:
    """Create ``disposition_list_cache`` if absent. Idempotent. Single transaction."""
    with conn:
        conn.execute(_DDL_DISPOSITION_CACHE)


def _read_cached_set(conn: sqlite3.Connection, asof_iso: str) -> set[str]:
    """Return the set of symbols cached for ``asof_iso`` (empty set if none)."""
    cursor = conn.execute(
        "SELECT symbol FROM disposition_list_cache WHERE asof_date = ?",
        (asof_iso,),
    )
    return {row[0] for row in cursor.fetchall()}


def fetch_disposition_set(
    asof: date | str,
    *,
    conn: sqlite3.Connection | None = None,
) -> set[str]:
    """Return the disposition set for ``asof``.

    Cache hit: returns the cached set.
    Cache miss: returns ``set()`` (stub — see module docstring).

    Never raises. ``conn=None`` (production) opens a fresh connection via
    ``ohmystock.api.db.get_connection``; tests / batched callers pass an
    in-memory or shared conn.
    """
    asof_iso = asof if isinstance(asof, str) else asof.isoformat()
    owns_conn = conn is None
    c = get_connection() if owns_conn else conn
    try:
        init_schema(c)
        return _read_cached_set(c, asof_iso)
    finally:
        if owns_conn:
            c.close()
