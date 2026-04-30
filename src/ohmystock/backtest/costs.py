"""Taiwan transaction-cost model.

Spec: openspec/changes/backtest-engine-mvp/specs/backtest-engine/spec.md
"""

from __future__ import annotations

import warnings
from typing import Literal, TypedDict

FEE_RATE = 0.001425
TAX_RATE_REGULAR = 0.0030
TAX_RATE_DAYTRADE = 0.0015
FEE_FLOOR_TWD = 20.0
DAYTRADE_TAX_SUNSET = "2027-12-31"

_warned_sunset = False


class CostBreakdown(TypedDict):
    fee: float
    tax: float
    total: float


def transaction_cost(
    side: Literal["buy", "sell"],
    price: float,
    qty: int,
    *,
    day_trade: bool,
    fee_discount: float = 0.28,
    trade_date: str | None = None,
) -> CostBreakdown:
    if side not in ("buy", "sell"):
        raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
    if price < 0 or qty < 0:
        raise ValueError(f"price and qty must be non-negative, got {price=}, {qty=}")
    if not (0 < fee_discount <= 1):
        raise ValueError(f"fee_discount must be in (0, 1], got {fee_discount}")

    notional = price * qty
    fee_raw = notional * FEE_RATE * fee_discount
    fee = max(FEE_FLOOR_TWD, fee_raw) if notional > 0 else 0.0

    if side == "buy":
        tax = 0.0
    elif day_trade:
        if trade_date is not None and trade_date > DAYTRADE_TAX_SUNSET:
            global _warned_sunset
            if not _warned_sunset:
                warnings.warn(
                    f"day-trade tax sunset clause expired ({DAYTRADE_TAX_SUNSET}); "
                    f"falling back to regular {TAX_RATE_REGULAR:.4f} rate.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                _warned_sunset = True
            tax = notional * TAX_RATE_REGULAR
        else:
            tax = notional * TAX_RATE_DAYTRADE
    else:
        tax = notional * TAX_RATE_REGULAR

    return {"fee": fee, "tax": tax, "total": fee + tax}
