"""RS Percentile universe loader — swappable provider for `rs_percentile` sub-scorer.

The default seed loader returns 5 TWSE large-caps with synthetic constant-return
close series so the sub-scorer can compute a percentile rank without needing
network access during unit tests. Production code (when it lands) replaces this
with `set_rs_universe_loader(...)` to inject a real TWSE+OTC liquidity-filtered
universe.

Spec: openspec/changes/phase-2b-sepa-subscorers/specs/phase-2b-scoring-engine/spec.md
("rs_percentile sub-scorer (real implementation)" requirement).
"""

from __future__ import annotations

from typing import Callable


UniverseLoader = Callable[[], list[tuple[str, list[float]]]]


_SEED_SYMBOLS: tuple[str, ...] = ("2330", "2317", "2454", "3008", "2412")


def _default_seed_loader() -> list[tuple[str, list[float]]]:
    """Return 5 TWSE large-caps with synthetic 252-bar close series.

    Each symbol gets a deterministic linear ramp at a different growth rate so
    percentile ranks span the universe meaningfully. Used by unit tests and as
    a no-network fallback; production should override via
    ``set_rs_universe_loader``.
    """
    universe: list[tuple[str, list[float]]] = []
    for idx, symbol in enumerate(_SEED_SYMBOLS):
        growth = 1.0 + 0.05 * (idx + 1)
        closes = [100.0 * (1.0 + (growth - 1.0) * (i / 251.0)) for i in range(252)]
        universe.append((symbol, closes))
    return universe


_universe_loader: UniverseLoader = _default_seed_loader


def get_rs_universe_loader() -> UniverseLoader:
    """Return the currently-active universe loader callable."""
    return _universe_loader


def set_rs_universe_loader(loader: UniverseLoader) -> None:
    """Replace the universe loader. Used by tests and production wiring."""
    global _universe_loader
    if not callable(loader):
        raise TypeError(f"loader must be callable, got {loader!r}")
    _universe_loader = loader


def reset_rs_universe_loader() -> None:
    """Restore the default seed loader."""
    global _universe_loader
    _universe_loader = _default_seed_loader
