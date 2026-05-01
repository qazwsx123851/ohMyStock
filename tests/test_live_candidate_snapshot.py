"""Tests for live_candidate_snapshot.

Spec: openspec/changes/live-providers/specs/live-providers/spec.md
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any

import pytest

from ohmystock.data.sources.base import BarRow
from ohmystock.swarm import (
    CandidateLiveSnapshot,
    LiveProviderError,
    live_candidate_snapshot,
)


def _bar(ts: str, c: float) -> BarRow:
    # Use small h-l spread so ATR is non-trivial but bounded.
    return BarRow(
        ts=ts,
        o=c,
        h=c * 1.01,
        l=c * 0.99,
        c=c,
        v=1000,
        amount=int(c * 1000),
    )


def _ramp_bars(n: int, start: float = 100.0, step: float = 1.0) -> list[BarRow]:
    return [
        _bar(f"2026-01-{(d % 28) + 1:02d}", start + step * d) for d in range(n)
    ]


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
        "ohmystock.swarm._live_candidate.get_kline",
        lambda symbol, bars, end_date: env,
    )


def test_full_window_populates_all_five_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get_kline(monkeypatch, _envelope_ok(_ramp_bars(260)))
    snap = live_candidate_snapshot("2330", "2026-04-30")
    assert isinstance(snap, CandidateLiveSnapshot)
    assert snap.current_price > 0
    # Ramp ends above EMA20, so EMA20 distance should be positive.
    assert snap.ema20_distance_pct > 0
    # ATR is positive over a non-flat ramp.
    assert snap.atr_14_pct > 0
    # End is the 52w high — distance should be 0.
    assert snap.distance_from_52w_high_pct == pytest.approx(0.0, abs=1e-9)
    # End is far above the 52w low — distance should be positive.
    assert snap.distance_from_52w_low_pct > 0
    # All four percentages are finite floats.
    for v in (
        snap.ema20_distance_pct,
        snap.atr_14_pct,
        snap.distance_from_52w_high_pct,
        snap.distance_from_52w_low_pct,
    ):
        assert math.isfinite(v)


def test_fewer_than_252_bars_no_padding(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_get_kline(monkeypatch, _envelope_ok(_ramp_bars(50)))
    snap = live_candidate_snapshot("2330", "2026-04-30")
    # Window is only 50 bars; 52w computations operate on what exists.
    assert snap.current_price > 0
    # Distance from high = 0 (still ramping up to current).
    assert snap.distance_from_52w_high_pct == pytest.approx(0.0, abs=1e-9)


def test_get_kline_error_propagates_with_same_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get_kline(monkeypatch, _envelope_err("STALE_DATA", "old cache"))
    with pytest.raises(LiveProviderError) as exc:
        live_candidate_snapshot("2330", "2026-04-30")
    assert exc.value.code == "STALE_DATA"
    assert "old cache" in str(exc.value)


def test_get_kline_data_unavailable_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get_kline(monkeypatch, _envelope_err("DATA_UNAVAILABLE", "no bars"))
    with pytest.raises(LiveProviderError) as exc:
        live_candidate_snapshot("2330", "2026-04-30")
    assert exc.value.code == "DATA_UNAVAILABLE"


def test_invalid_input_mapped_to_upstream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get_kline(monkeypatch, _envelope_err("INVALID_INPUT", "bad symbol"))
    with pytest.raises(LiveProviderError) as exc:
        live_candidate_snapshot("@@@", "2026-04-30")
    # INVALID_INPUT is not in LiveProviderError's closed set; mapped to UPSTREAM_ERROR.
    assert exc.value.code == "UPSTREAM_ERROR"


def test_rate_limit_mapped_to_upstream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get_kline(monkeypatch, _envelope_err("RATE_LIMIT", "429"))
    with pytest.raises(LiveProviderError) as exc:
        live_candidate_snapshot("2330", "2026-04-30")
    assert exc.value.code == "UPSTREAM_ERROR"


def test_empty_bars_raises_data_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get_kline(monkeypatch, _envelope_ok([]))
    with pytest.raises(LiveProviderError) as exc:
        live_candidate_snapshot("2330", "2026-04-30")
    assert exc.value.code == "DATA_UNAVAILABLE"


def test_frozen_dataclass_cannot_be_mutated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get_kline(monkeypatch, _envelope_ok(_ramp_bars(50)))
    snap = live_candidate_snapshot("2330", "2026-04-30")
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.current_price = 999.0  # type: ignore[misc]
