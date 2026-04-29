"""Tests for ohmystock.data.finmind_client.

Spec: openspec/changes/external-connectors-and-cost/specs/external-connectors/spec.md
"""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from ohmystock.data.finmind_client import FinMindClient, FinMindConnectionError


def _fake_response(status_code: int, json_body: dict | None = None, text: str = ""):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    if json_body is not None:
        resp.json.return_value = json_body
    else:
        resp.json.side_effect = ValueError("not json")
    return resp


def test_get_taiwan_stock_price_returns_list_of_dicts(monkeypatch) -> None:
    client = FinMindClient()
    body = {
        "data": [
            {"date": "2026-04-29", "stock_id": "2330", "close": 580.0},
            {"date": "2026-04-28", "stock_id": "2330", "close": 575.0},
        ]
    }
    monkeypatch.setattr(
        client._client, "get", lambda *a, **k: _fake_response(200, body)
    )

    rows = client.get_taiwan_stock_price("2330", "2026-04-22", "2026-04-29")
    assert isinstance(rows, list)
    assert len(rows) == 2
    assert rows[0]["stock_id"] == "2330"
    assert rows[0]["close"] == 580.0


def test_http_500_raises_finmind_connection_error(monkeypatch) -> None:
    client = FinMindClient()
    monkeypatch.setattr(
        client._client,
        "get",
        lambda *a, **k: _fake_response(500, None, text="Internal Server Error"),
    )

    with pytest.raises(FinMindConnectionError, match="500"):
        client.get_taiwan_stock_price("2330", "2026-04-22", "2026-04-29")
