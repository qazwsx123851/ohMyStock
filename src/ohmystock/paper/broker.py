"""Paper broker shim for Confirm Gate v0.

Spec: openspec/changes/confirm-gate-v0/specs/confirm-gate/spec.md

Defines the ``PaperBroker`` Protocol that Confirm Gate calls, plus the
deterministic ``FakePaperBroker`` default impl. Real Shioaji simulator
wiring is intentionally out of scope (separate change after the gate is
in place).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


class BrokerError(Exception):
    """Raised by a ``PaperBroker`` when the order cannot be submitted."""


@dataclass(frozen=True)
class Fill:
    symbol: str
    side: Literal["buy"]
    requested_qty: int
    filled_qty: int
    fill_price: float
    fill_ts: str


class _Clock(Protocol):
    def now_iso(self) -> str:
        ...


class PaperBroker(Protocol):
    def submit_market_order(
        self,
        symbol: str,
        qty: int,
        side: Literal["buy"],
        reference_price: float,
    ) -> Fill:
        ...


class FakePaperBroker:
    """Deterministic test/dev broker — fills at ``reference_price`` exactly."""

    def __init__(self, clock: _Clock, raise_on_submit: bool = False) -> None:
        self._clock = clock
        self._raise_on_submit = raise_on_submit

    def submit_market_order(
        self,
        symbol: str,
        qty: int,
        side: Literal["buy"],
        reference_price: float,
    ) -> Fill:
        if self._raise_on_submit:
            raise BrokerError("forced failure (FakePaperBroker.raise_on_submit=True)")
        return Fill(
            symbol=symbol,
            side=side,
            requested_qty=qty,
            filled_qty=qty,
            fill_price=reference_price,
            fill_ts=self._clock.now_iso(),
        )
