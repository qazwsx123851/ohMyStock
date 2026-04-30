"""Strategy Protocol + reference strategies for the backtest engine.

Spec: openspec/changes/backtest-engine-mvp/specs/backtest-engine/spec.md
"""

from ohmystock.backtest.strategy.base import (
    BarContext,
    IndicatorFn,
    Strategy,
    required_indicators_of,
)
from ohmystock.backtest.strategy.sma_cross import SmaCross

__all__ = [
    "BarContext",
    "IndicatorFn",
    "Strategy",
    "SmaCross",
    "required_indicators_of",
]
