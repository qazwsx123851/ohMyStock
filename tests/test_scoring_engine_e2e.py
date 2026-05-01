"""End-to-end engine test using the real placeholder sub-scorer.

Spec: openspec/changes/phase-2b-scoring-engine/specs/phase-2b-scoring-engine/spec.md
"""

from __future__ import annotations

from unittest.mock import patch


def test_score_watchlist_e2e_with_placeholder_only() -> None:
    """No registry mutation: rely on the real placeholder loaded at import time."""

    ok_envelope = {
        "ok": True,
        "elapsed_ms": 0,
        "data": {"bars": [], "rows": []},
        "error": None,
    }

    with (
        patch(
            "ohmystock.scoring._engine.get_kline", return_value=ok_envelope
        ),
        patch(
            "ohmystock.scoring._engine.get_three_major_investors",
            return_value=ok_envelope,
        ),
        patch(
            "ohmystock.scoring._engine.get_margin_short", return_value=ok_envelope
        ),
    ):
        from ohmystock.scoring import score_watchlist

        env = score_watchlist("2026-04-30", ["2330"])

    assert env["ok"] is True
    assert env["error"] is None
    assert env["data"]["asof_date"] == "2026-04-30"

    candidates = env["data"]["candidates"]
    assert len(candidates) == 1
    c = candidates[0]
    assert c["symbol"] == "2330"
    assert c["final_score"] == 0
    assert c["classification"] == "red"
    assert c["risk_off_applied"] is False

    placeholder = next(
        s for s in c["subscores"] if s["name"] == "_always_zero_placeholder"
    )
    assert placeholder["status"] == "scored"
    assert placeholder["points"] == 0
    assert placeholder["max_points"] == 0
    assert placeholder["evidence"] == {"placeholder": True}
