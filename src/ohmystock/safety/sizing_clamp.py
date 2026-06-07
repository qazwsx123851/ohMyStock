"""Shared sizing-guard primitives for the human confirm + auto-execute paths.

These are the two defenses described in ``docs/safety-and-simulation.md`` §2.9,
extracted here so the human-confirm ``override_qty`` path and the auto-execute
path apply the *same* SSOT thresholds rather than each re-deriving them:

* **Notional hard limit** — a position whose notional exceeds a fraction of
  account equity is refused outright (Breaker 5 semantics).
* **Formula deviation soft limit** — a value that deviates from the system
  formula by more than a fraction is clamped to the more conservative
  (smaller) value (Step 8 semantics).

All functions are pure; no formula is duplicated elsewhere.
"""

from __future__ import annotations


def exceeds_notional_limit(
    qty_shares: int,
    price: float,
    equity_twd: float,
    max_notional_pct: float,
) -> bool:
    """True iff ``qty_shares * price`` exceeds ``equity_twd * max_notional_pct``."""
    return qty_shares * price > equity_twd * max_notional_pct


def exceeds_deviation(
    value: float, system_value: float, max_deviation: float
) -> bool:
    """True iff ``value`` deviates from ``system_value`` by more than
    ``max_deviation`` (relative). Returns ``False`` when ``system_value`` is 0
    (no formula reference to deviate from)."""
    if system_value == 0:
        return False
    return abs(value - system_value) / abs(system_value) > max_deviation


def clamp_to_conservative(value: float, system_value: float) -> float:
    """Return the more conservative (smaller) of the user value and the system
    value — used after ``exceeds_deviation`` flags an over-aggressive input."""
    return min(value, system_value)
