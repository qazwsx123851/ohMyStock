"""Stable iterator surface for Phase 2B qualified candidates.

The swarm input assembler (and the CLI) need a deterministic way to
enumerate Phase 2B candidates above the qualifying threshold. This
module exposes ``iter_qualified_candidates`` plus a swap-in
``set_candidate_loader`` hook for tests and future persistence wiring.

Spec: openspec/changes/phase-2b-swarm-input-assembler/specs/phase-2b-scoring-engine/spec.md
"""

from __future__ import annotations

from typing import Callable, Iterable, Iterator, Sequence

from ohmystock.scoring.models import Phase2BCandidate


CandidateLoader = Callable[[str], Sequence[Phase2BCandidate]]


def _default_loader(asof_date: str) -> Sequence[Phase2BCandidate]:
    raise NotImplementedError(
        "no Phase 2B candidate loader is registered. "
        "Call set_candidate_loader(loader) once persistence is wired, "
        "or call iter_qualified_candidates(..., candidates=<seq>) explicitly."
    )


_loader: CandidateLoader = _default_loader


def set_candidate_loader(loader: CandidateLoader) -> None:
    """Register a loader callable for the default ``iter_qualified_candidates`` path."""
    global _loader
    _loader = loader


def reset_candidate_loader() -> None:
    """Restore the default (raises) loader. Test helper."""
    global _loader
    _loader = _default_loader


def iter_qualified_candidates(
    asof_date: str,
    *,
    threshold: float = 65.0,
    candidates: Iterable[Phase2BCandidate] | None = None,
) -> Iterator[Phase2BCandidate]:
    """Yield Phase 2B candidates with ``final_score >= threshold``.

    Order: ``-final_score`` then ``symbol`` ascending. Empty input yields
    nothing — never raises on the empty case.

    If ``candidates`` is supplied, the loader is bypassed (handy for the
    CLI which already has them in hand). Otherwise the registered loader
    runs against ``asof_date``.
    """
    if candidates is None:
        loaded = _loader(asof_date)
    else:
        loaded = list(candidates)

    qualifying = [c for c in loaded if c.final_score >= threshold]
    qualifying.sort(key=lambda c: (-c.final_score, c.symbol))
    for c in qualifying:
        yield c
