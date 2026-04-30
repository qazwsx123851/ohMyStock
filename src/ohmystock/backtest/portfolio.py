"""Portfolio state with T+2 cash settlement.

Spec: openspec/changes/backtest-engine-mvp/specs/backtest-engine/spec.md
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ohmystock.backtest.costs import CostBreakdown


@dataclass
class Portfolio:
    cash: float
    available_cash: float
    positions: dict[str, int] = field(default_factory=dict)
    pending_settlements: dict[str, float] = field(default_factory=dict)

    @classmethod
    def with_initial(cls, initial_capital: float) -> "Portfolio":
        return cls(cash=float(initial_capital), available_cash=float(initial_capital))

    def advance_to(self, today: str) -> None:
        ready = [d for d in self.pending_settlements if d < today]
        for d in ready:
            self.available_cash += self.pending_settlements.pop(d)

    def can_afford_buy(self, fill_price: float, qty: int, cost: CostBreakdown) -> bool:
        return self.available_cash >= fill_price * qty + cost["total"]

    def apply_buy(
        self,
        symbol: str,
        qty: int,
        fill_price: float,
        cost: CostBreakdown,
        fill_date: str,
    ) -> None:
        del fill_date
        outflow = fill_price * qty + cost["total"]
        self.cash -= outflow
        self.available_cash -= outflow
        self.positions[symbol] = self.positions.get(symbol, 0) + qty

    def apply_sell(
        self,
        symbol: str,
        qty: int,
        fill_price: float,
        cost: CostBreakdown,
        fill_date: str,
        settlement_date: str,
    ) -> None:
        del fill_date
        held = self.positions.get(symbol, 0)
        if qty > held:
            raise ValueError(f"sell qty {qty} exceeds holdings {held} for {symbol}")
        net = fill_price * qty - cost["total"]
        self.cash += net
        self.pending_settlements[settlement_date] = (
            self.pending_settlements.get(settlement_date, 0.0) + net
        )
        self.positions[symbol] = held - qty
        if self.positions[symbol] == 0:
            del self.positions[symbol]

    def view(self) -> dict:
        return {
            "cash": self.cash,
            "available_cash": self.available_cash,
            "positions": dict(self.positions),
        }
