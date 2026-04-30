"""Golden-value and convention tests for ``ohmystock.indicators``.

Spec: openspec/changes/technical-indicators-skill/specs/technical-indicators/spec.md
"""

from __future__ import annotations

import pytest

from ohmystock.data.sources.base import BarRow
from ohmystock.indicators import atr, bollinger_bands, ema, macd, rsi, sma
from ohmystock.indicators import core as indicators_core


def _flat_bars(n: int) -> list[BarRow]:
    return [
        {
            "ts": f"2026-04-{d:02d}",
            "o": 100.0,
            "h": 110.0,
            "l": 90.0,
            "c": 100.0,
            "v": 0,
            "amount": 0,
        }
        for d in range(1, n + 1)
    ]


# ---------- SMA ----------


def test_sma_period_one_is_identity() -> None:
    assert sma([1.5, 2.5, 3.5], 1) == [1.5, 2.5, 3.5]


def test_sma_linear_ramp_period_4() -> None:
    assert sma([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], 4) == [None, None, None, 2.5, 3.5, 4.5]


def test_sma_empty_input() -> None:
    assert sma([], 5) == []


def test_sma_invalid_period() -> None:
    with pytest.raises(ValueError):
        sma([1.0, 2.0, 3.0], 0)
    with pytest.raises(ValueError):
        sma([1.0, 2.0, 3.0], -1)


# ---------- EMA ----------


def test_ema_golden_period_3() -> None:
    assert ema([2.0, 4.0, 6.0, 8.0, 10.0], 3) == [None, None, 4.0, 6.0, 8.0]


@pytest.mark.parametrize("period", [1, 5, 50])
def test_ema_length_invariant(period: int) -> None:
    closes = [float(i) for i in range(1, 101)]
    assert len(ema(closes, period)) == len(closes)


# ---------- RSI ----------


def test_rsi_constant_input_is_50() -> None:
    result = rsi([10.0] * 30, 14)
    assert result[:14] == [None] * 14
    for v in result[14:]:
        assert v == 50.0


def test_rsi_strictly_rising_is_100() -> None:
    closes = [float(i) for i in range(1, 31)]
    result = rsi(closes, 14)
    for v in result[14:]:
        assert v == 100.0


def test_rsi_warmup_is_none() -> None:
    closes = [float(i) for i in range(1, 31)]
    result = rsi(closes, 14)
    assert result[:14] == [None] * 14


# ---------- MACD ----------


def test_macd_outputs_match_input_length() -> None:
    closes = [float(i) for i in range(1, 51)]
    macd_line, signal_line, histogram = macd(closes)
    assert len(macd_line) == len(closes)
    assert len(signal_line) == len(closes)
    assert len(histogram) == len(closes)


def test_macd_alignment_first_defined_indices() -> None:
    closes = [float(i) for i in range(1, 51)]
    macd_line, signal_line, _ = macd(closes)
    first_macd = next(i for i, v in enumerate(macd_line) if v is not None)
    first_signal = next(i for i, v in enumerate(signal_line) if v is not None)
    assert first_macd == 25
    assert first_signal == 33


# ---------- ATR ----------


def test_atr_flat_bars_equals_high_minus_low() -> None:
    bars = _flat_bars(20)
    result = atr(bars, 14)
    for v in result[14:]:
        assert v == pytest.approx(20.0)


def test_atr_warmup_layout() -> None:
    bars = _flat_bars(20)
    result = atr(bars, 14)
    assert result[:14] == [None] * 14
    for v in result[14:]:
        assert v == pytest.approx(20.0)


# ---------- Bollinger Bands ----------


def test_bollinger_constant_input_zero_width() -> None:
    closes = [5.0] * 25
    upper, middle, lower = bollinger_bands(closes, period=20, k=2.0)
    for i in range(19, 25):
        assert upper[i] == 5.0
        assert middle[i] == 5.0
        assert lower[i] == 5.0


def test_bollinger_outputs_match_input_length() -> None:
    closes = [float(i) for i in range(1, 31)]
    upper, middle, lower = bollinger_bands(closes, period=20, k=2.0)
    assert len(upper) == len(closes)
    assert len(middle) == len(closes)
    assert len(lower) == len(closes)


# ---------- Cross-cutting ----------


def test_package_reexports_are_same_objects() -> None:
    assert sma is indicators_core.sma
    assert ema is indicators_core.ema
    assert rsi is indicators_core.rsi
    assert macd is indicators_core.macd
    assert atr is indicators_core.atr
    assert bollinger_bands is indicators_core.bollinger_bands


def test_all_indicators_handle_empty_input() -> None:
    assert sma([], 5) == []
    assert ema([], 5) == []
    assert rsi([], 14) == []
    assert macd([]) == ([], [], [])
    assert atr([], 14) == []
    assert bollinger_bands([]) == ([], [], [])
