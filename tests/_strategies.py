"""Test-only helper strategies for the backtest engine."""

from __future__ import annotations

from ohmystock.backtest.fills import OrderIntent
from ohmystock.backtest.strategy.base import BarContext


class BuyAndHold:
    name = "buy_and_hold"

    def __init__(self, symbol: str, qty: int = 1000) -> None:
        self.symbol = symbol
        self.qty = qty
        self._bought = False

    def warmup_bars(self) -> int:
        return 0

    def on_bar(self, ctx: BarContext) -> list[OrderIntent]:
        if self._bought or ctx.symbol != self.symbol:
            return []
        self._bought = True
        return [
            {
                "symbol": self.symbol,
                "side": "buy",
                "qty": self.qty,
                "order_type": "market",
                "limit_price": None,
            }
        ]


class BuyEveryBar:
    """Emits a BUY on every bar — used to test last-bar cancellation."""

    name = "buy_every_bar"

    def __init__(self, symbol: str, qty: int = 100) -> None:
        self.symbol = symbol
        self.qty = qty

    def warmup_bars(self) -> int:
        return 0

    def on_bar(self, ctx: BarContext) -> list[OrderIntent]:
        if ctx.symbol != self.symbol:
            return []
        return [
            {
                "symbol": self.symbol,
                "side": "buy",
                "qty": self.qty,
                "order_type": "market",
                "limit_price": None,
            }
        ]


class RaisingStrategy:
    name = "raises_on_third_bar"

    def __init__(self) -> None:
        self._calls = 0

    def warmup_bars(self) -> int:
        return 0

    def on_bar(self, ctx: BarContext) -> list[OrderIntent]:
        self._calls += 1
        if self._calls == 3:
            raise RuntimeError("boom")
        return []


class NoIndicators:
    """Strategy without `required_indicators` — engine must default to {}."""

    name = "no_indicators"

    def warmup_bars(self) -> int:
        return 0

    def on_bar(self, ctx: BarContext) -> list[OrderIntent]:
        return []
