"""Unit tests for the FakePaperBroker shim.

Spec: openspec/changes/confirm-gate-v0/specs/confirm-gate/spec.md
- Requirement "PaperBroker Protocol 與 FakePaperBroker 預設實作"
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ohmystock.paper import BrokerError, FakePaperBroker, Fill


@dataclass(frozen=True)
class _FakeClock:
    """Minimal Clock impl for tests; returns the same string on every call."""

    ts: str

    def now_iso(self) -> str:
        return self.ts


def test_fake_broker_normal_fill_returns_fill_at_reference_price() -> None:
    broker = FakePaperBroker(clock=_FakeClock("2026-05-02T10:15:00+08:00"))

    fill = broker.submit_market_order(
        symbol="2330",
        qty=2000,
        side="buy",
        reference_price=832.0,
    )

    assert fill == Fill(
        symbol="2330",
        side="buy",
        requested_qty=2000,
        filled_qty=2000,
        fill_price=832.0,
        fill_ts="2026-05-02T10:15:00+08:00",
    )


def test_fake_broker_raise_on_submit_raises_broker_error() -> None:
    broker = FakePaperBroker(
        clock=_FakeClock("2026-05-02T10:15:00+08:00"),
        raise_on_submit=True,
    )

    with pytest.raises(BrokerError, match="forced failure"):
        broker.submit_market_order(
            symbol="2330",
            qty=1000,
            side="buy",
            reference_price=832.0,
        )


def test_fake_broker_fill_ts_uses_injected_clock() -> None:
    broker = FakePaperBroker(clock=_FakeClock("2026-12-31T23:59:59+08:00"))

    fill = broker.submit_market_order(
        symbol="0050",
        qty=1000,
        side="buy",
        reference_price=150.5,
    )

    assert fill.fill_ts == "2026-12-31T23:59:59+08:00"


def test_fake_broker_filled_qty_equals_requested() -> None:
    """Spec: FakePaperBroker has no slippage / no partial fills (D4)."""
    broker = FakePaperBroker(clock=_FakeClock("2026-05-02T10:00:00+08:00"))

    fill = broker.submit_market_order(
        symbol="2330",
        qty=5000,
        side="buy",
        reference_price=832.0,
    )

    assert fill.requested_qty == fill.filled_qty == 5000
    assert fill.fill_price == 832.0
