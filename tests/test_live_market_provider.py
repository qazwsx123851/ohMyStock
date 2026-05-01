"""Tests for compute_taiex_snapshot + LiveMarketSnapshotProvider.

Spec: openspec/changes/live-providers/specs/live-providers/spec.md
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from typing import Any

import pytest

from ohmystock.data.sources.base import BarRow
from ohmystock.journal.schema import init_schema
from ohmystock.swarm import LiveProviderError, MarketSnapshot
from ohmystock.swarm._live_market import compute_taiex_snapshot


def _bar(ts: str, c: float) -> BarRow:
    return BarRow(
        ts=ts,
        o=c,
        h=c * 1.01,
        l=c * 0.99,
        c=c,
        v=1_000_000,
        amount=int(c * 1_000_000),
    )


def _envelope_ok(bars: list[BarRow]) -> dict[str, Any]:
    return {"ok": True, "elapsed_ms": 1, "data": {"bars": bars}, "error": None}


def _envelope_err(code: str, message: str = "boom") -> dict[str, Any]:
    return {
        "ok": False,
        "elapsed_ms": 1,
        "data": None,
        "error": {"code": code, "message": message, "retriable": False},
    }


def _patch_get_kline(monkeypatch: pytest.MonkeyPatch, env: dict[str, Any]) -> None:
    monkeypatch.setattr(
        "ohmystock.swarm._live_market.get_kline",
        lambda symbol, bars, end_date: env,
    )


def _series_business_days(end_date: str, count: int) -> list[str]:
    """Return ``count`` consecutive business days ending at ``end_date``."""
    end = date.fromisoformat(end_date)
    out: list[date] = []
    cursor = end
    while len(out) < count:
        if cursor.weekday() < 5:
            out.append(cursor)
        cursor -= timedelta(days=1)
    out.reverse()
    return [d.isoformat() for d in out]


# ---------- risk_off behaviour ----------


def test_taiex_above_ma60_returns_risk_off_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dates = _series_business_days("2026-04-30", 80)
    closes = [10000.0 + i * 5 for i in range(80)]  # rising
    bars = [_bar(d, c) for d, c in zip(dates, closes)]
    _patch_get_kline(monkeypatch, _envelope_ok(bars))

    snap, diag = compute_taiex_snapshot("2026-04-30", starting_equity=1_000_000.0)

    assert isinstance(snap, MarketSnapshot)
    assert snap.risk_off is False
    assert snap.taiex_close == bars[-1]["c"]
    assert snap.monthly_pnl_pct == 0.0  # no conn provided
    assert diag == {
        "spy_5d_return": "unknown",
        "vix": "unknown",
        "twd_usd": "unknown",
        "taifex_foreign_short": "unknown",
    }


def test_taiex_below_ma60_with_falling_ma_triggers_risk_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dates = _series_business_days("2026-04-30", 80)
    closes = [20000.0 - i * 50 for i in range(80)]
    bars = [_bar(d, c) for d, c in zip(dates, closes)]
    _patch_get_kline(monkeypatch, _envelope_ok(bars))

    snap, _ = compute_taiex_snapshot("2026-04-30", starting_equity=1_000_000.0)

    assert snap.risk_off is True


def test_taiex_below_ma60_with_rising_ma_does_not_trigger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dates = _series_business_days("2026-04-30", 80)
    closes = [10000.0 + i * 100 for i in range(79)] + [10000.0]
    bars = [_bar(d, c) for d, c in zip(dates, closes)]
    _patch_get_kline(monkeypatch, _envelope_ok(bars))

    snap, _ = compute_taiex_snapshot("2026-04-30", starting_equity=1_000_000.0)

    assert snap.risk_off is False


def test_insufficient_bars_does_not_trigger_risk_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dates = _series_business_days("2026-04-30", 30)
    closes = [10000.0 - i * 100 for i in range(30)]
    bars = [_bar(d, c) for d, c in zip(dates, closes)]
    _patch_get_kline(monkeypatch, _envelope_ok(bars))

    snap, _ = compute_taiex_snapshot("2026-04-30", starting_equity=1_000_000.0)

    assert snap.risk_off is False


# ---------- error mapping ----------


def test_get_kline_data_unavailable_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get_kline(monkeypatch, _envelope_err("DATA_UNAVAILABLE", "no cache"))
    with pytest.raises(LiveProviderError) as exc:
        compute_taiex_snapshot("2026-04-30")
    assert exc.value.code == "DATA_UNAVAILABLE"
    assert "TAIEX" in str(exc.value)


def test_get_kline_invalid_input_mapped_to_upstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get_kline(monkeypatch, _envelope_err("INVALID_INPUT", "bad"))
    with pytest.raises(LiveProviderError) as exc:
        compute_taiex_snapshot("2026-04-30")
    assert exc.value.code == "UPSTREAM_ERROR"


def test_empty_bars_raises_data_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_get_kline(monkeypatch, _envelope_ok([]))
    with pytest.raises(LiveProviderError) as exc:
        compute_taiex_snapshot("2026-04-30")
    assert exc.value.code == "DATA_UNAVAILABLE"


def test_stale_cache_raises_stale_data(monkeypatch: pytest.MonkeyPatch) -> None:
    bars = [_bar("2026-04-15", 20000.0)]
    _patch_get_kline(monkeypatch, _envelope_ok(bars))
    with pytest.raises(LiveProviderError) as exc:
        compute_taiex_snapshot("2026-04-30")
    assert exc.value.code == "STALE_DATA"


def test_freshness_within_5_business_days_is_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bars = [_bar("2026-04-23", 20000.0)]
    _patch_get_kline(monkeypatch, _envelope_ok(bars))
    snap, _ = compute_taiex_snapshot("2026-04-30")
    assert snap.taiex_close == 20000.0


# ---------- monthly_pnl_pct via journal ----------


def test_monthly_pnl_read_from_journal_when_conn_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dates = _series_business_days("2026-04-30", 80)
    closes = [10000.0 + i * 5 for i in range(80)]
    bars = [_bar(d, c) for d, c in zip(dates, closes)]
    _patch_get_kline(monkeypatch, _envelope_ok(bars))

    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    conn.execute(
        "INSERT INTO journal_entries(decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            "dec_x",
            "entry",
            "2330",
            "2026-04-10T10:00:00+08:00",
            json.dumps({"actual_entry_price": 800.0, "actual_qty": 1}),
        ),
    )
    conn.execute(
        "INSERT INTO journal_entries(decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            "dec_x",
            "exit",
            "2330",
            "2026-04-20T13:30:00+08:00",
            json.dumps({"pnl_pct": 10.0}),
        ),
    )
    conn.commit()

    snap, _ = compute_taiex_snapshot(
        "2026-04-30", conn=conn, starting_equity=1_000_000.0
    )
    # 10% of (800 * 1 lot * 1000 shares = 800_000) = 80_000 vs 1_000_000 = 8.0%
    assert snap.monthly_pnl_pct == pytest.approx(8.0)
    conn.close()


# ---------- LiveMarketSnapshotProvider integration ----------


def test_live_market_provider_records_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ohmystock.swarm import LiveMarketSnapshotProvider

    dates = _series_business_days("2026-04-30", 80)
    closes = [10000.0 + i * 5 for i in range(80)]
    bars = [_bar(d, c) for d, c in zip(dates, closes)]
    _patch_get_kline(monkeypatch, _envelope_ok(bars))

    # Avoid real DB I/O by stubbing _open_journal_conn to raise; the
    # provider tolerates that and proceeds with monthly_pnl_pct=0.0.
    def _raise_conn() -> sqlite3.Connection:
        raise LiveProviderError(code="DATA_UNAVAILABLE", message="no journal")

    monkeypatch.setattr(
        "ohmystock.swarm._adapters._open_journal_conn", _raise_conn
    )

    provider = LiveMarketSnapshotProvider(asof="2026-04-30")
    snap = provider.get()

    assert isinstance(snap, MarketSnapshot)
    assert snap.monthly_pnl_pct == 0.0
    assert provider.last_diagnostics["spy_5d_return"] == "unknown"
    assert provider.last_diagnostics["vix"] == "unknown"
