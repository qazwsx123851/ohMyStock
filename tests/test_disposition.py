"""Tests for ``ohmystock.data.disposition`` — covers task 2.5.

Spec: openspec/changes/rs-percentile-finmind-wiring/specs/rs-percentile/spec.md
      ("Disposition list interface and cache table ship; live TWSE/OTC scrape is deferred")
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from ohmystock.data.disposition import fetch_disposition_set, init_schema


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    try:
        init_schema(c)
        yield c
    finally:
        c.close()


class TestInitSchema:
    """Spec scenario: 'Cache table exists with documented schema'."""

    def test_creates_table_with_documented_columns_and_pk(
        self, conn: sqlite3.Connection
    ) -> None:
        cols = {
            row[1]: (row[2], bool(row[3]))
            for row in conn.execute(
                "PRAGMA table_info(disposition_list_cache)"
            ).fetchall()
        }
        # All three columns are NOT NULL per the DDL.
        assert cols["asof_date"] == ("TEXT", True)
        assert cols["symbol"] == ("TEXT", True)
        assert cols["fetched_at"] == ("TEXT", True)

        # Composite primary key (asof_date, symbol).
        pk_columns = [
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(disposition_list_cache)"
            ).fetchall()
            if row[5]  # pk flag
        ]
        assert sorted(pk_columns) == ["asof_date", "symbol"]

    def test_init_schema_is_idempotent(self, conn: sqlite3.Connection) -> None:
        # Calling twice must not raise.
        init_schema(conn)
        init_schema(conn)


class TestFetchDispositionSet:
    """Spec scenarios: 'Cache hit ...' and 'Cache miss returns empty set ...'."""

    def test_cache_hit_returns_cached_set(self, conn: sqlite3.Connection) -> None:
        asof_iso = "2026-04-30"
        conn.executemany(
            "INSERT INTO disposition_list_cache (asof_date, symbol, fetched_at) "
            "VALUES (?, ?, ?)",
            [
                (asof_iso, "5678", "2026-04-30T08:30:00+00:00"),
                (asof_iso, "1234", "2026-04-30T08:30:00+00:00"),
            ],
        )
        conn.commit()

        result = fetch_disposition_set(date(2026, 4, 30), conn=conn)

        assert result == {"5678", "1234"}

    def test_cache_miss_returns_empty_set_without_raising(
        self, conn: sqlite3.Connection
    ) -> None:
        # No rows for this asof.
        result = fetch_disposition_set(date(2026, 4, 30), conn=conn)
        assert result == set()

    def test_accepts_iso_string_or_date_object(
        self, conn: sqlite3.Connection
    ) -> None:
        asof_iso = "2026-04-30"
        conn.execute(
            "INSERT INTO disposition_list_cache (asof_date, symbol, fetched_at) "
            "VALUES (?, ?, ?)",
            (asof_iso, "5678", "2026-04-30T08:30:00+00:00"),
        )
        conn.commit()

        from_string = fetch_disposition_set("2026-04-30", conn=conn)
        from_date = fetch_disposition_set(date(2026, 4, 30), conn=conn)

        assert from_string == from_date == {"5678"}

    def test_no_raise_when_table_absent(self) -> None:
        """If init_schema hasn't been called yet, fetch must still not raise."""
        c = sqlite3.connect(":memory:")
        try:
            # Don't call init_schema; fetch should create it implicitly.
            result = fetch_disposition_set("2026-04-30", conn=c)
            assert result == set()
        finally:
            c.close()
