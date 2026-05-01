"""End-to-end engine test against the real registered sub-scorers.

Replaces tests/test_scoring_engine_e2e.py (placeholder-only) once the
placeholder is deleted in section 10 of the change.

Spec: openspec/changes/phase-2b-shipped-subscorers/specs/phase-2b-scoring-engine/spec.md
("End-to-end engine output with real sub-scorers" requirement).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch


def _make_max_score_data() -> tuple[list[dict], list[dict], list[dict]]:
    """Synthetic context that drives all 6 real sub-scorers to full points.

    Six sub-scorers × max_points = 10 + 5 + 5 + 5 + 5 + 4 = 34.
    """

    closes = [10.0 + (90.0 * i / 251.0) for i in range(252)]
    highs = list(closes)
    lows = [c * 0.99 for c in closes]
    volumes = [1000] * 251 + [1500]  # last bar 1.5× the 20-day average

    bars = [
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
    # 5 strong-buy rows: foreign 5d sum = 1250 (>1000 → 5 pts), trust 5d sum = 350 (>300 → 4 pts).
    three_major_rows = [
        {
            "date": f"2026-04-{i + 1:02d}",
            "foreign_net": 250,
            "invest_trust_net": 70,
            "prop_dealer_net": 0,
        }
        for i in range(5)
    ]
    margin_short_rows = [
        {
            "date": f"2026-04-{i + 1:02d}",
            "margin_balance": 50000,
            "margin_change": -100,
            "short_balance": 800,
            "short_change": 50,
            "short_to_margin_ratio": 0.016,
        }
        for i in range(5)
    ]
    return bars, three_major_rows, margin_short_rows


def _envelope(payload: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "elapsed_ms": 0, "data": payload, "error": None}


def _patch_engine(bars: list[dict], chip_rows: list[dict], margin_rows: list[dict]) -> tuple:
    return (
        patch(
            "ohmystock.scoring._engine.get_kline",
            return_value=_envelope({"bars": bars}),
        ),
        patch(
            "ohmystock.scoring._engine.get_three_major_investors",
            return_value=_envelope({"rows": chip_rows}),
        ),
        patch(
            "ohmystock.scoring._engine.get_margin_short",
            return_value=_envelope({"rows": margin_rows}),
        ),
    )


def test_full_max_score_with_real_subscorers() -> None:
    bars, chip_rows, margin_rows = _make_max_score_data()
    p1, p2, p3 = _patch_engine(bars, chip_rows, margin_rows)
    with p1, p2, p3:
        from ohmystock.scoring import score_watchlist

        env = score_watchlist("2026-04-30", ["2330"])

    assert env["ok"] is True
    assert env["error"] is None
    candidates = env["data"]["candidates"]
    assert len(candidates) == 1
    c = candidates[0]

    # Final score = 34 (placeholder removed; only the 6 real sub-scorers contribute).
    assert c["final_score"] == 34
    assert c["classification"] == "red"
    assert c["risk_off_applied"] is False

    # Exactly 6 sub-scorers — no placeholder.
    assert len(c["subscores"]) == 6
    assert all(s["name"] != "_always_zero_placeholder" for s in c["subscores"])

    by_name = {s["name"]: s for s in c["subscores"]}
    expected_full_points = {
        "trend_structure_ma": 10.0,
        "trend_template_8": 5.0,
        "stage_2_confirmed": 5.0,
        "volume_breakout_obv": 5.0,
        "foreign_5d_net_buy": 5.0,
        "trust_5d_net_buy": 4.0,
    }
    for name, pts in expected_full_points.items():
        assert name in by_name, f"missing sub-scorer {name}"
        s = by_name[name]
        assert s["status"] == "scored", f"{name} status={s['status']}"
        assert s["points"] == pts, f"{name} points={s['points']}"


def test_mixed_status_with_short_history() -> None:
    """Few bars (<21) skip every technical sub-scorer; chip rows still score."""
    closes = [100.0 + i for i in range(20)]
    bars = [
        {"ts": f"2026-04-{i + 1:02d}", "o": closes[i], "h": closes[i], "l": closes[i], "c": closes[i], "v": 1000, "amount": 100000}
        for i in range(20)
    ]
    chip_rows = [
        {"date": f"2026-04-{i + 1:02d}", "foreign_net": 300, "invest_trust_net": 0, "prop_dealer_net": 0}
        for i in range(5)
    ]
    margin_rows: list[dict] = []

    p1, p2, p3 = _patch_engine(bars, chip_rows, margin_rows)
    with p1, p2, p3:
        from ohmystock.scoring import score_watchlist

        env = score_watchlist("2026-04-30", ["2330"])

    assert env["ok"] is True
    by_name = {s["name"]: s for s in env["data"]["candidates"][0]["subscores"]}

    for name in ("trend_structure_ma", "trend_template_8", "stage_2_confirmed", "volume_breakout_obv"):
        assert by_name[name]["status"] == "skipped", f"{name} should skip"
        assert by_name[name]["points"] == 0

    f = by_name["foreign_5d_net_buy"]
    assert f["status"] == "scored"
    assert f["points"] > 0  # 1500 lots → 5 pts
