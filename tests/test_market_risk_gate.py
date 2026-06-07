"""Unit tests for the dashboard market Risk-Off gate (DB-B1).

All data access is injected, so these run without network. Covers each of the
five §0.1 conditions (trigger + non-trigger), the unknown→yellow path, and the
green/yellow/red status mapping.
"""

from __future__ import annotations

from ohmystock.swarm.market_risk_gate import evaluate_risk_gate


def _env(closes: list[float]) -> dict:
    return {"ok": True, "data": {"bars": [{"c": c} for c in closes]}, "error": None}


def _fail() -> dict:
    return {"ok": False, "data": None, "error": {"code": "DATA_UNAVAILABLE"}}


# Default "all calm" closes per symbol.
_TAIEX_CALM = [100.0 + i for i in range(80)]          # rising → close ≥ MA60
_SPY_CALM = [100.0] * 10                               # flat → no 5d drop
_VIX_CALM = [15.0, 15.0]                               # low, no spike
_TWD_CALM = [30.0, 30.0]                               # stable
_TAIFEX_CALM = [5.0, 4.0, 3.0, 2.0, 1.0]              # falling → no streak


def _kline(overrides: dict[str, list[float] | None] = {}):
    base: dict[str, list[float] | None] = {
        "TAIEX": _TAIEX_CALM,
        "SPY": _SPY_CALM,
        "VIX": _VIX_CALM,
        "USDTWD": _TWD_CALM,
    }
    base.update(overrides)

    def _fn(symbol: str, *, bars: int, end_date: str) -> dict:
        closes = base.get(symbol)
        if closes is None:
            return _fail()
        return _env(closes)

    return _fn


def _futures(series: list[float] | None):
    def _fn(asof: str) -> list[float] | None:
        return series

    return _fn


def test_all_calm_is_green() -> None:
    r = evaluate_risk_gate(
        "2026-06-07", kline_fn=_kline(), futures_fn=_futures(_TAIFEX_CALM)
    )
    assert r.status == "green"
    assert r.triggers == []
    assert r.unknown == []


def test_taiex_below_ma60_triggers_red() -> None:
    falling = [200.0 - i for i in range(80)]  # close < MA60, MA60 falling
    r = evaluate_risk_gate(
        "2026-06-07",
        kline_fn=_kline({"TAIEX": falling}),
        futures_fn=_futures(_TAIFEX_CALM),
    )
    assert r.status == "red"
    assert "taiex_below_ma60" in r.triggers


def test_spy_5d_drop_triggers_red() -> None:
    spy = [100, 100, 100, 100, 100, 100, 100, 100, 100, 96]  # -4% over 5d, down
    r = evaluate_risk_gate(
        "2026-06-07",
        kline_fn=_kline({"SPY": [float(x) for x in spy]}),
        futures_fn=_futures(_TAIFEX_CALM),
    )
    assert r.status == "red"
    assert "spy_5d_drop" in r.triggers


def test_vix_level_triggers_red() -> None:
    r = evaluate_risk_gate(
        "2026-06-07",
        kline_fn=_kline({"VIX": [24.0, 30.0]}),
        futures_fn=_futures(_TAIFEX_CALM),
    )
    assert "vix_high" in r.triggers


def test_vix_spike_triggers_red() -> None:
    r = evaluate_risk_gate(
        "2026-06-07",
        kline_fn=_kline({"VIX": [10.0, 14.0]}),  # +40% > 30%
        futures_fn=_futures(_TAIFEX_CALM),
    )
    assert "vix_high" in r.triggers


def test_twd_depreciation_triggers_red() -> None:
    r = evaluate_risk_gate(
        "2026-06-07",
        kline_fn=_kline({"USDTWD": [30.0, 30.2]}),  # +0.67% > 0.5%
        futures_fn=_futures(_TAIFEX_CALM),
    )
    assert "twd_depreciation" in r.triggers


def test_taifex_three_day_new_high_triggers_red() -> None:
    r = evaluate_risk_gate(
        "2026-06-07",
        kline_fn=_kline(),
        futures_fn=_futures([1.0, 2.0, 3.0, 4.0, 5.0]),  # 3 consecutive highs
    )
    assert "taifex_foreign_short_streak" in r.triggers


def test_unknown_condition_yields_yellow() -> None:
    # VIX data missing → unknown; nothing else triggers → yellow.
    r = evaluate_risk_gate(
        "2026-06-07",
        kline_fn=_kline({"VIX": None}),
        futures_fn=_futures(_TAIFEX_CALM),
    )
    assert r.status == "yellow"
    assert "vix_high" in r.unknown
    assert r.triggers == []


def test_trigger_wins_over_unknown() -> None:
    # SPY missing (unknown) but TWD triggers → red (trigger dominates).
    r = evaluate_risk_gate(
        "2026-06-07",
        kline_fn=_kline({"SPY": None, "USDTWD": [30.0, 30.5]}),
        futures_fn=_futures(_TAIFEX_CALM),
    )
    assert r.status == "red"
    assert "twd_depreciation" in r.triggers


def test_no_futures_fn_marks_taifex_unknown() -> None:
    r = evaluate_risk_gate("2026-06-07", kline_fn=_kline(), futures_fn=None)
    assert "taifex_foreign_short_streak" in r.unknown
    assert r.status == "yellow"
