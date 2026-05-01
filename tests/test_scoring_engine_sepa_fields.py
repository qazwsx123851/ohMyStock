"""End-to-end test that score_watchlist populates SEPA fields when the
real rs_percentile + vcp_pivot sub-scorers ship.

Spec: openspec/changes/phase-2b-sepa-subscorers/specs/phase-2b-scoring-engine/spec.md
("SEPA fields populated end-to-end through score_watchlist" requirement).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch


def _envelope(payload: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "elapsed_ms": 0, "data": payload, "error": None}


def _make_uptrend_bars() -> list[dict]:
    """252-bar synthetic uptrend with a strong breakout on the last bar.

    The last 20 closes form a tight base, and the final bar's volume spikes
    1.5× the prior 20-DMA → vcp_pivot returns ``breakout``. The year-long
    return is large → top decile vs the 5-symbol seed universe → rs_percentile
    awards 7 points.
    """
    closes = [10.0 + (90.0 * i / 251.0) for i in range(252)]
    highs = list(closes)
    lows = [c * 0.99 for c in closes]
    volumes = [1000] * 251 + [1500]
    return [
        {
            "ts": f"2025-{((i // 28) % 12) + 1:02d}-{(i % 28) + 1:02d}",
            "o": closes[i],
            "h": highs[i],
            "l": lows[i],
            "c": closes[i],
            "v": volumes[i],
            "amount": int(closes[i] * volumes[i]),
        }
        for i in range(252)
    ]


def _patch_engine(bars: list[dict]) -> tuple:
    return (
        patch(
            "ohmystock.scoring._engine.get_kline",
            return_value=_envelope({"bars": bars}),
        ),
        patch(
            "ohmystock.scoring._engine.get_three_major_investors",
            return_value=_envelope({"rows": []}),
        ),
        patch(
            "ohmystock.scoring._engine.get_margin_short",
            return_value=_envelope({"rows": []}),
        ),
    )


def test_sufficient_bars_produce_non_none_sepa_fields() -> None:
    bars = _make_uptrend_bars()
    p1, p2, p3 = _patch_engine(bars)
    with p1, p2, p3:
        from ohmystock.scoring import score_watchlist

        env = score_watchlist("2026-04-30", ["2330"])

    assert env["ok"] is True
    candidates = env["data"]["candidates"]
    assert len(candidates) == 1
    c = candidates[0]

    assert c["stage"] is not None, c
    assert c["rs_percentile"] is not None, c
    assert c["trend_template_passed"] is not None, c
    assert c["vcp_quality"] is not None, c

    if c["vcp_quality"] in {"textbook", "breakout"}:
        assert c["pivot_price"] is not None, c
    else:
        assert c["pivot_price"] is None, c


def test_sepa_fields_have_correct_types_and_ranges() -> None:
    """Beyond non-None, SEPA fields must satisfy the Phase2BCandidate
    schema constraints (Field(ge=0, le=99) etc.)."""
    bars = _make_uptrend_bars()
    p1, p2, p3 = _patch_engine(bars)
    with p1, p2, p3:
        from ohmystock.scoring import score_watchlist

        env = score_watchlist("2026-04-30", ["2330"])

    c = env["data"]["candidates"][0]
    assert isinstance(c["rs_percentile"], int)
    assert 0 <= c["rs_percentile"] <= 99
    assert isinstance(c["trend_template_passed"], int)
    assert 0 <= c["trend_template_passed"] <= 8
    assert c["vcp_quality"] in {"none", "forming", "textbook", "breakout"}
    assert c["stage"] in {1, 2, 3, 4}
