"""Reference SMA-cross strategy (test/example only, not a production strategy).

Spec: openspec/changes/backtest-engine-mvp/specs/backtest-engine/spec.md
"""

from __future__ import annotations

from ohmystock.backtest.fills import OrderIntent
from ohmystock.backtest.strategy.base import BarContext
from ohmystock.indicators import sma


class SmaCross:
    name = "sma_cross"

    def __init__(self, fast: int = 5, slow: int = 20, qty: int = 1000) -> None:
        if not (0 < fast < slow):
            raise ValueError(f"need 0 < fast < slow, got {fast=}, {slow=}")
        if qty <= 0:
            raise ValueError(f"qty must be positive, got {qty}")
        self.fast = fast
        self.slow = slow
        self.qty = qty

    def warmup_bars(self) -> int:
        return self.slow

    def required_indicators(self) -> dict:
        fast, slow = self.fast, self.slow
        return {
            "sma_fast": lambda bars: sma([b["c"] for b in bars], fast),
            "sma_slow": lambda bars: sma([b["c"] for b in bars], slow),
        }

    def on_bar(self, ctx: BarContext) -> list[OrderIntent]:
        f = ctx.indicators["sma_fast"]
        s = ctx.indicators["sma_slow"]
        if len(f) < 2 or f[-1] is None or f[-2] is None or s[-1] is None or s[-2] is None:
            return []
        held = ctx.portfolio["positions"].get(ctx.symbol, 0)
        prev_diff = f[-2] - s[-2]
        cur_diff = f[-1] - s[-1]
        if prev_diff <= 0 < cur_diff and held == 0:
            return [
                {
                    "symbol": ctx.symbol,
                    "side": "buy",
                    "qty": self.qty,
                    "order_type": "market",
                    "limit_price": None,
                }
            ]
        if prev_diff >= 0 > cur_diff and held > 0:
            return [
                {
                    "symbol": ctx.symbol,
                    "side": "sell",
                    "qty": held,
                    "order_type": "market",
                    "limit_price": None,
                }
            ]
        return []
