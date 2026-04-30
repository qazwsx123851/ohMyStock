"""Tests for ``ohmystock.sepa.stage``.

Spec: openspec/changes/sepa-trend-template-and-stage/specs/sepa-stage-classification/spec.md
"""

from __future__ import annotations

import dataclasses

import pytest

from ohmystock.data.sources.base import BarRow
from ohmystock.sepa import (
    InsufficientHistoryError,
    StageResult,
    classify_stage,
    is_stage_4_reject,
)


def _bar(close: float, ts: str = "2026-01-01", h_mult: float = 1.005, l_mult: float = 0.995) -> BarRow:
    return {
        "ts": ts,
        "o": close,
        "h": close * h_mult,
        "l": close * l_mult,
        "c": close,
        "v": 1000,
        "amount": int(close * 1000),
    }


def _ts(i: int) -> str:
    return f"2026-{(i // 21) + 1:02d}-{(i % 21) + 1:02d}"


def _make_ramp_bars(n: int = 252, start: float = 100.0, end: float = 200.0) -> list[BarRow]:
    if n == 1:
        return [_bar(start, "2026-01-01")]
    step = (end - start) / (n - 1)
    return [_bar(start + i * step, _ts(i)) for i in range(n)]


def _make_flat_bars(n: int = 252, value: float = 100.0) -> list[BarRow]:
    return [_bar(value, _ts(i)) for i in range(n)]


# ---------- Scenario: Synthetic Stage-2 monotonic ramp ----------


def test_ramp_classifies_as_stage_2() -> None:
    bars = _make_ramp_bars()
    result = classify_stage(bars)
    assert result.stage == 2
    assert "Stage 2" in result.reason


# ---------- Scenario: Synthetic Stage-4 decline ----------


def test_decline_classifies_as_stage_4() -> None:
    bars = _make_ramp_bars(n=252, start=200.0, end=100.0)
    result = classify_stage(bars)
    assert result.stage == 4
    assert "MA50<MA150<MA200" in result.reason
    assert "close<MA50" in result.reason
    assert "MA200 not rising" in result.reason


# ---------- Scenario: Stage-2 mean-stack but volatile range qualifies as Stage 3 ----------


def test_volatile_last_30_bars_promote_to_stage_3() -> None:
    bars = _make_ramp_bars()
    last_close = bars[-1]["c"]
    high_inflated = last_close * 1.10
    low_deflated = last_close * 0.85
    for i in range(len(bars) - 30, len(bars)):
        b = bars[i]
        bars[i] = {
            "ts": b["ts"],
            "o": b["o"],
            "h": high_inflated,
            "l": low_deflated,
            "c": b["c"],
            "v": b["v"],
            "amount": b["amount"],
        }
    result = classify_stage(bars)
    assert result.stage == 3
    assert "Stage 3" in result.reason


# ---------- Scenario: Flat sideways closes Stage 1 ----------


def test_flat_bars_classify_as_stage_1() -> None:
    bars = _make_flat_bars(n=252, value=100.0)
    result = classify_stage(bars)
    assert result.stage == 1


# ---------- Scenario: is_stage_4_reject ----------


def test_is_stage_4_reject_true_on_decline() -> None:
    bars = _make_ramp_bars(n=252, start=200.0, end=100.0)
    assert is_stage_4_reject(bars) is True


def test_is_stage_4_reject_false_on_stage_2_ramp() -> None:
    bars = _make_ramp_bars()
    assert is_stage_4_reject(bars) is False


def test_is_stage_4_reject_false_on_flat_stage_1() -> None:
    bars = _make_flat_bars()
    assert is_stage_4_reject(bars) is False


# ---------- Scenario: Mean-stack inverted but MA200 rising (deep pullback in uptrend) ----------


def test_inverted_mean_stack_with_ma200_still_rising_is_not_stage_4() -> None:
    closes: list[float] = []
    closes.extend([50.0] * 52)
    closes.extend([200.0] * 150)
    closes.extend([100.0] * 49)
    closes.append(90.0)
    assert len(closes) == 252
    bars = [_bar(c, _ts(i)) for i, c in enumerate(closes)]
    result = classify_stage(bars)
    assert result.stage != 4
    assert is_stage_4_reject(bars) is False


# ---------- Scenario: insufficient history raises ----------


def test_classify_stage_raises_on_insufficient_history() -> None:
    bars = _make_ramp_bars()[:251]
    with pytest.raises(InsufficientHistoryError):
        classify_stage(bars)


def test_is_stage_4_reject_raises_on_insufficient_history() -> None:
    bars = _make_ramp_bars()[:251]
    with pytest.raises(InsufficientHistoryError):
        is_stage_4_reject(bars)


# ---------- Scenario: output is immutable ----------


def test_stage_result_is_frozen() -> None:
    bars = _make_ramp_bars()
    result = classify_stage(bars)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.stage = 1  # type: ignore[misc]


def test_stage_result_has_correct_type() -> None:
    bars = _make_ramp_bars()
    result = classify_stage(bars)
    assert isinstance(result, StageResult)
