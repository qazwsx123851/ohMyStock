"""Sub-scorer registry: decorator + dispatch + list.

Spec: openspec/changes/phase-2b-scoring-engine/specs/phase-2b-scoring-engine/spec.md
("Sub-scorer registry contract" requirement).
"""

from __future__ import annotations

from typing import Callable

from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.models import SubScoreCategory, SubScoreResult


SubScorerFn = Callable[[ScoringContext], SubScoreResult]

_REGISTRY: dict[str, tuple[SubScorerFn, SubScoreCategory, float]] = {}


def register_subscorer(
    *,
    category: SubScoreCategory,
    name: str,
    max_points: float,
) -> Callable[[SubScorerFn], SubScorerFn]:
    """Decorator: register a sub-scorer function under (category, name, max_points)."""

    def _wrap(fn: SubScorerFn) -> SubScorerFn:
        if name in _REGISTRY:
            raise ValueError(f"sub-scorer already registered: {name}")
        _REGISTRY[name] = (fn, category, max_points)
        return fn

    return _wrap


def dispatch(name: str, ctx: ScoringContext) -> SubScoreResult:
    """Invoke the registered sub-scorer; overwrite contract metadata; clamp points."""
    if name not in _REGISTRY:
        raise KeyError(f"sub-scorer not registered: {name}")

    fn, category, max_points = _REGISTRY[name]
    raw = fn(ctx)
    clamped_points = max(0.0, min(float(max_points), float(raw.points)))
    return SubScoreResult(
        name=name,
        category=category,
        points=clamped_points,
        max_points=float(max_points),
        status=raw.status,
        evidence=raw.evidence,
        error_message=raw.error_message,
    )


def list_subscorers() -> list[tuple[str, SubScoreCategory, float]]:
    """Return registered sub-scorers as (name, category, max_points), alphabetical by name."""
    return sorted(
        ((n, cat, mp) for n, (_, cat, mp) in _REGISTRY.items()),
        key=lambda t: t[0],
    )


def _reset_registry() -> None:
    """Test-only helper to clear registry state between tests."""
    _REGISTRY.clear()
