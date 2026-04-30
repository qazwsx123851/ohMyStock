"""Daily-bar fill model with ±10% price-limit gate.

Spec: openspec/changes/backtest-engine-mvp/specs/backtest-engine/spec.md
"""

from __future__ import annotations

from typing import Literal, TypedDict

from ohmystock.data.sources.base import BarRow

LIMIT_UP_FACTOR = 1.10
LIMIT_DOWN_FACTOR = 0.90
LIMIT_TOL = 0.005
LIMIT_DAY_SLIPPAGE = 0.010


class OrderIntent(TypedDict):
    symbol: str
    side: Literal["buy", "sell"]
    qty: int
    order_type: Literal["market", "limit"]
    limit_price: float | None


class FillResult(TypedDict):
    status: Literal["filled", "rejected_limit_up", "rejected_limit_down"]
    fill_price: float | None
    reason: str | None


def compute_fill(
    order: OrderIntent,
    fill_bar: BarRow,
    prev_close: float | None,
    *,
    slippage_bps: int = 30,
) -> FillResult:
    side = order["side"]
    open_px = fill_bar["o"]
    slip = slippage_bps / 10_000.0

    if prev_close is not None and prev_close > 0:
        limit_up = prev_close * LIMIT_UP_FACTOR
        limit_down = prev_close * LIMIT_DOWN_FACTOR
        if abs(open_px - limit_up) < LIMIT_TOL:
            if side == "buy":
                return {
                    "status": "rejected_limit_up",
                    "fill_price": None,
                    "reason": f"open {open_px} at limit-up {limit_up}",
                }
            return {
                "status": "filled",
                "fill_price": open_px * (1 - LIMIT_DAY_SLIPPAGE),
                "reason": None,
            }
        if abs(open_px - limit_down) < LIMIT_TOL:
            if side == "sell":
                return {
                    "status": "rejected_limit_down",
                    "fill_price": None,
                    "reason": f"open {open_px} at limit-down {limit_down}",
                }
            return {
                "status": "filled",
                "fill_price": open_px * (1 + LIMIT_DAY_SLIPPAGE),
                "reason": None,
            }

    if side == "buy":
        return {"status": "filled", "fill_price": open_px * (1 + slip), "reason": None}
    return {"status": "filled", "fill_price": open_px * (1 - slip), "reason": None}
