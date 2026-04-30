"""Strategy Protocol and BarContext for the backtest engine.

Spec: openspec/changes/backtest-engine-mvp/specs/backtest-engine/spec.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable

from ohmystock.backtest.fills import OrderIntent
from ohmystock.data.sources.base import BarRow

IndicatorFn = Callable[[list[BarRow]], list]


@dataclass(frozen=True)
class BarContext:
    date: str
    symbol: str
    bars: list[BarRow]
    indicators: dict[str, list]
    portfolio: dict


@runtime_checkable
class Strategy(Protocol):
    name: str

    def warmup_bars(self) -> int:
        ...

    def on_bar(self, ctx: BarContext) -> list[OrderIntent]:
        ...


def required_indicators_of(strategy: object) -> dict[str, IndicatorFn]:
    fn = getattr(strategy, "required_indicators", None)
    if fn is None:
        return {}
    out = fn()
    if not isinstance(out, dict):
        raise TypeError(
            f"Strategy.required_indicators() must return dict, got {type(out).__name__}"
        )
    return out
