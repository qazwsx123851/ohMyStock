"""Tests for ``scripts/backfill_rs_rating.py`` — covers task 4.5.

Spec: openspec/changes/rs-percentile-finmind-wiring/specs/rs-percentile/spec.md
      ("Backfill entrypoint is range-bounded, idempotent, and verifies row count")
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

from ohmystock.sepa.rs import (
    init_schema as init_rs_schema,
    reset_providers,
    set_universe_closes_loader,
)


_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "backfill_rs_rating.py"


@pytest.fixture(scope="module")
def backfill_module():
    """Load ``scripts/backfill_rs_rating.py`` as a module for testing.

    The script lives outside the import path; we load via importlib.
    """
    spec = importlib.util.spec_from_file_location(
        "backfill_rs_rating", _SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["backfill_rs_rating"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _reset_loaders():
    yield
    reset_providers()


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    try:
        init_rs_schema(c)
        yield c
    finally:
        c.close()


def _make_stub_loader(num_symbols: int):
    """Return a loader that yields ``num_symbols`` valid 260-close ramps per asof."""

    def loader(asof: date) -> dict[str, list[float]]:
        # Each symbol gets a unique ramp so percentile ranks vary.
        return {
            f"S{i:04d}": [1.0 + i + 0.01 * j for j in range(260)]
            for i in range(num_symbols)
        }

    return loader


def _empty_loader(asof: date) -> dict[str, list[float]]:
    return {}


class TestRunBackfill:
    """Spec scenarios under 'Backfill entrypoint …'."""

    def test_populates_cache_and_exits_zero(
        self,
        conn: sqlite3.Connection,
        backfill_module,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        set_universe_closes_loader(_make_stub_loader(num_symbols=150))

        exit_code = backfill_module.run_backfill(
            days=5, today=date(2026, 5, 6), conn=conn
        )
        assert exit_code == 0

        # 5 asofs × 150 symbols = 750 rows >= floor (500).
        first = "2026-04-30"  # 5 business days back from Wed 2026-05-06
        last = "2026-05-06"
        total = conn.execute(
            "SELECT COUNT(*) FROM rs_rating_cache "
            "WHERE asof_date BETWEEN ? AND ?",
            (first, last),
        ).fetchone()[0]
        assert total == 750

        captured = capsys.readouterr()
        # 5 per-asof lines + 1 final OK line.
        per_day_lines = [
            ln for ln in captured.out.splitlines() if "|" in ln and "ms" in ln
        ]
        assert len(per_day_lines) == 5
        assert "OK:" in captured.out

    def test_idempotent_rerun_keeps_row_count(
        self, conn: sqlite3.Connection, backfill_module
    ) -> None:
        set_universe_closes_loader(_make_stub_loader(num_symbols=150))

        # First run.
        rc1 = backfill_module.run_backfill(
            days=5, today=date(2026, 5, 6), conn=conn
        )
        count_after_first = conn.execute(
            "SELECT COUNT(*) FROM rs_rating_cache"
        ).fetchone()[0]

        # Second run with same args.
        rc2 = backfill_module.run_backfill(
            days=5, today=date(2026, 5, 6), conn=conn
        )
        count_after_second = conn.execute(
            "SELECT COUNT(*) FROM rs_rating_cache"
        ).fetchone()[0]

        assert rc1 == 0 and rc2 == 0
        assert count_after_first == count_after_second == 750

    def test_floor_failure_exits_non_zero(
        self,
        conn: sqlite3.Connection,
        backfill_module,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        set_universe_closes_loader(_empty_loader)

        exit_code = backfill_module.run_backfill(
            days=5, today=date(2026, 5, 6), conn=conn
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "FAIL:" in captured.err
        assert "expected >= 500" in captured.err


class TestWalkBackBusinessDays:
    """Sanity coverage for the date-range helper."""

    def test_skips_weekends(self, backfill_module) -> None:
        # 2026-05-06 is Wed; walking back 5 business days lands on 2026-04-30.
        asofs = backfill_module._walk_back_business_days(date(2026, 5, 6), 5)
        assert asofs[0] == date(2026, 4, 30)
        assert asofs[-1] == date(2026, 5, 6)
        # All weekdays (Mon=0 .. Fri=4).
        assert all(d.weekday() < 5 for d in asofs)

    def test_returns_oldest_to_newest(self, backfill_module) -> None:
        asofs = backfill_module._walk_back_business_days(date(2026, 5, 6), 10)
        assert asofs == sorted(asofs)


class TestMainCli:
    """Cover the argparse entrypoint without actually running the loop."""

    def test_main_rejects_zero_days(
        self, backfill_module, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Stop after wiring/parse — no real DB call.
        monkeypatch.setattr(backfill_module, "wire_production_loader", lambda: None)
        with pytest.raises(SystemExit) as exc:
            backfill_module.main(["--days", "0"])
        # argparse error -> SystemExit code 2.
        assert exc.value.code == 2
