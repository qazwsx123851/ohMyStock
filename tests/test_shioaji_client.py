"""Tests for ohmystock.paper.shioaji_client.

Spec: openspec/changes/external-connectors-and-cost/specs/external-connectors/spec.md
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pytest

import ohmystock.paper.shioaji_client as shioaji_module
from ohmystock.paper.shioaji_client import (
    ShioajiConnectionError,
    ShioajiPaperClient,
)


@pytest.fixture
def mock_sdk(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(shioaji_module.sj, "Shioaji", lambda **kwargs: fake)
    return fake


def test_login_success(mock_sdk) -> None:
    snap = MagicMock(close=580.0, ts=1714000000)
    mock_sdk.snapshots.return_value = [snap]
    mock_sdk.Contracts.Stocks = {"2330": MagicMock()}

    client = ShioajiPaperClient()
    client.login()

    result = client.get_snapshot("2330")
    assert result == {"symbol": "2330", "close": 580.0, "ts": 1714000000}
    mock_sdk.login.assert_called_once()


def test_login_failure_chains_original_exception(mock_sdk) -> None:
    mock_sdk.login.side_effect = ConnectionError("network down")

    client = ShioajiPaperClient()
    with pytest.raises(ShioajiConnectionError, match="login failed") as exc_info:
        client.login()

    assert isinstance(exc_info.value.__cause__, ConnectionError)
    assert "network down" in str(exc_info.value.__cause__)


def test_init_signature_does_not_accept_simulation_param() -> None:
    sig = inspect.signature(ShioajiPaperClient.__init__)
    assert "simulation" not in sig.parameters
