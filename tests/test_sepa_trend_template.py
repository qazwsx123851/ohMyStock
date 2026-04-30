"""Tests for ``ohmystock.sepa.trend_template``.

Spec: openspec/changes/sepa-trend-template-and-stage/specs/sepa-trend-template/spec.md
"""

from __future__ import annotations

import dataclasses

import pytest

from ohmystock.data.sources.base import BarRow
from ohmystock.sepa import (
    InsufficientHistoryError,
    TrendTemplateResult,
    evaluate_trend_template,
)


def _bar(close: float, ts: str = "2026-01-01") -> BarRow:
    return {
        "ts": ts,
        "o": close,
        "h": close * 1.005,
        "l": close * 0.995,
        "c": close,
        "v": 1000,
        "amount": int(close * 1000),
    }


def _make_ramp_bars(n: int = 252, start: float = 100.0, end: float = 200.0) -> list[BarRow]:
    if n == 1:
        return [_bar(start, "2026-01-01")]
    step = (end - start) / (n - 1)
    return [_bar(start + i * step, f"2026-{(i // 21) + 1:02d}-{(i % 21) + 1:02d}") for i in range(n)]


def _make_decline_bars(n: int = 252, start: float = 200.0, end: float = 100.0) -> list[BarRow]:
    return _make_ramp_bars(n=n, start=start, end=end)


def _make_flat_bars(n: int = 252, value: float = 100.0) -> list[BarRow]:
    return [_bar(value, f"2026-{(i // 21) + 1:02d}-{(i % 21) + 1:02d}") for i in range(n)]


# ---------- Scenario: All eight conditions pass on a synthetic Stage-2 ramp ----------


def test_ramp_all_eight_conditions_pass() -> None:
    bars = _make_ramp_bars()
    result = evaluate_trend_template(bars, rs_percentile=80.0)
    assert result.passed is True
    assert set(result.conditions.keys()) == {"c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8"}
    for key, outcome in result.conditions.items():
        assert outcome.passed is True, f"{key} failed: {outcome.detail}"


def test_ramp_returns_rs_percentile_in_result() -> None:
    bars = _make_ramp_bars()
    result = evaluate_trend_template(bars, rs_percentile=72.5)
    assert result.rs_percentile == 72.5


# ---------- Scenario: Condition c6 fails when MA200 dips mid-window ----------


def test_c6_fails_when_ma200_dips_in_last_20_sessions() -> None:
    bars = _make_ramp_bars()
    bars[245] = _bar(50.0, bars[245]["ts"])
    result = evaluate_trend_template(bars, rs_percentile=80.0)
    assert result.conditions["c6"].passed is False
    assert "dipped" in result.conditions["c6"].detail
    assert result.passed is False


# ---------- Scenario: Condition c7 fails when close > 25% below 52-week high ----------


def test_c7_fails_when_close_too_far_below_52w_high() -> None:
    ramp_up = _make_ramp_bars(n=180, start=100.0, end=200.0)
    decline = _make_ramp_bars(n=72, start=200.0, end=140.0)
    bars = ramp_up + decline
    assert len(bars) == 252
    result = evaluate_trend_template(bars, rs_percentile=80.0)
    assert result.conditions["c7"].passed is False
    assert result.passed is False


# ---------- Scenario: rs_percentile is None ----------


def test_c8_tri_state_when_rs_percentile_none() -> None:
    bars = _make_ramp_bars()
    result = evaluate_trend_template(bars, rs_percentile=None)
    c8 = result.conditions["c8"]
    assert c8.passed is None
    assert "rs_percentile not provided" in c8.detail
    assert result.passed is False
    for key in ("c1", "c2", "c3", "c4", "c5", "c6", "c7"):
        assert result.conditions[key].passed in (True, False)
        assert result.conditions[key].passed is not None


# ---------- Scenario: insufficient history raises ----------


def test_insufficient_history_raises_with_actual_length_in_message() -> None:
    bars = _make_ramp_bars()[:251]
    with pytest.raises(InsufficientHistoryError) as exc_info:
        evaluate_trend_template(bars, rs_percentile=80.0)
    msg = str(exc_info.value)
    assert "251" in msg
    assert "252" in msg


def test_empty_bars_raises_insufficient_history() -> None:
    with pytest.raises(InsufficientHistoryError):
        evaluate_trend_template([], rs_percentile=80.0)


# ---------- Scenario: 52W window uses exactly the last 252 bars ----------


def test_52w_window_uses_only_last_252_bars() -> None:
    ramp = _make_ramp_bars(n=300, start=100.0, end=200.0)
    spike_close = 500.0
    ramp[10] = {
        "ts": ramp[10]["ts"],
        "o": spike_close,
        "h": spike_close,
        "l": spike_close,
        "c": spike_close,
        "v": 1000,
        "amount": int(spike_close * 1000),
    }
    last_close_target = 180.0
    ramp[-1] = _bar(last_close_target, ramp[-1]["ts"])
    result = evaluate_trend_template(ramp, rs_percentile=80.0)
    assert result.conditions["c7"].passed is True
    assert "500" not in result.conditions["c7"].detail


# ---------- Scenario: output is immutable ----------


def test_trend_template_result_is_frozen() -> None:
    bars = _make_ramp_bars()
    result = evaluate_trend_template(bars, rs_percentile=80.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.passed = False  # type: ignore[misc]


def test_condition_outcome_is_frozen() -> None:
    bars = _make_ramp_bars()
    result = evaluate_trend_template(bars, rs_percentile=80.0)
    outcome = result.conditions["c1"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        outcome.passed = False  # type: ignore[misc]


def test_result_has_correct_type() -> None:
    bars = _make_ramp_bars()
    result = evaluate_trend_template(bars, rs_percentile=80.0)
    assert isinstance(result, TrendTemplateResult)
