"""Tests that the always-zero placeholder is registered at package import.

Spec: openspec/changes/phase-2b-scoring-engine/specs/phase-2b-scoring-engine/spec.md
("Always-zero placeholder sub-scorer is registered" requirement).
"""

from __future__ import annotations


def test_placeholder_in_registry_after_package_import() -> None:
    import ohmystock.scoring  # noqa: F401 — import for side effect
    from ohmystock.scoring.registry import list_subscorers

    metas = list_subscorers()
    assert ("_always_zero_placeholder", "technical", 0) in metas


def test_placeholder_dispatch_produces_evidence() -> None:
    import ohmystock.scoring  # noqa: F401
    from ohmystock.scoring.context import ScoringContext
    from ohmystock.scoring.registry import dispatch

    ctx = ScoringContext(
        asof_date="2026-04-30",
        symbol="2330",
        bars=[],
        three_major=[],
        margin_short=[],
    )
    result = dispatch("_always_zero_placeholder", ctx)
    assert result.status == "scored"
    assert result.points == 0
    assert result.max_points == 0
    assert result.category == "technical"
    assert result.evidence == {"placeholder": True}
