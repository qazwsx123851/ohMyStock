"""Tests for FinMindClient.get_taiwan_stock_info.

Spec: openspec/changes/screener-tw-universe/specs/screener-tw-universe/spec.md
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


def _spy_get(captured: dict, status_code: int = 200, body: dict | None = None):
    body = body if body is not None else {"data": []}

    def _get(url, params=None, **kwargs):
        captured["url"] = url
        captured["params"] = params
        return _fake_response(status_code, body)

    return _get


def test_universe_method_uses_correct_dataset(monkeypatch) -> None:
    client = FinMindClient()
    captured: dict = {}
    monkeypatch.setattr(client._client, "get", _spy_get(captured))

    client.get_taiwan_stock_info()

    assert captured["url"] == FinMindClient.BASE_URL
    assert captured["params"]["dataset"] == "TaiwanStockInfo"
    assert "data_id" not in captured["params"]
    assert "start_date" not in captured["params"]
    assert "end_date" not in captured["params"]


def test_universe_token_forwarded_when_present(monkeypatch) -> None:
    client = FinMindClient()
    client._token = "secret-token"
    captured: dict = {}
    monkeypatch.setattr(client._client, "get", _spy_get(captured))

    client.get_taiwan_stock_info()

    assert captured["params"]["token"] == "secret-token"


def test_universe_token_omitted_when_absent(monkeypatch) -> None:
    client = FinMindClient()
    client._token = ""
    captured: dict = {}
    monkeypatch.setattr(client._client, "get", _spy_get(captured))

    client.get_taiwan_stock_info()

    assert "token" not in captured["params"]


def test_universe_http_500_raises(monkeypatch) -> None:
    client = FinMindClient()
    monkeypatch.setattr(
        client._client,
        "get",
        lambda *a, **k: _fake_response(500, None, text="Internal Server Error"),
    )

    with pytest.raises(FinMindConnectionError, match="500"):
        client.get_taiwan_stock_info()


def test_universe_missing_data_key_raises(monkeypatch) -> None:
    client = FinMindClient()
    monkeypatch.setattr(
        client._client,
        "get",
        lambda *a, **k: _fake_response(200, {"msg": "ok but no data"}),
    )

    with pytest.raises(FinMindConnectionError, match="missing 'data'"):
        client.get_taiwan_stock_info()


def test_universe_returns_data_list_on_success(monkeypatch) -> None:
    client = FinMindClient()
    body = {
        "data": [
            {
                "stock_id": "2330",
                "stock_name": "台積電",
                "industry_category": "Semiconductor",
                "type": "twse",
            },
            {
                "stock_id": "6488",
                "stock_name": "環球晶",
                "industry_category": "Semiconductor",
                "type": "tpex",
            },
        ]
    }
    monkeypatch.setattr(
        client._client, "get", lambda *a, **k: _fake_response(200, body)
    )

    rows = client.get_taiwan_stock_info()
    assert rows == body["data"]


def test_universe_http_error_wraps(monkeypatch) -> None:
    client = FinMindClient()

    def _boom(*a, **k):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(client._client, "get", _boom)

    with pytest.raises(FinMindConnectionError, match="request failed"):
        client.get_taiwan_stock_info()
