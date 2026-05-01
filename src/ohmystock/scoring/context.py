"""ScoringContext dataclass — pre-loaded inputs for one candidate.

Spec: openspec/changes/phase-2b-scoring-engine/specs/phase-2b-scoring-engine/spec.md
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringContext:
    asof_date: str
    symbol: str
    bars: list[dict]
    three_major: list[dict]
    margin_short: list[dict]
