"""Tests for FinMindClient chip dataset methods.

Spec: openspec/changes/chip-data-skill/specs/chip-data-skill/spec.md
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


def test_institutional_method_uses_correct_dataset(monkeypatch) -> None:
    client = FinMindClient()
    captured: dict = {}
    monkeypatch.setattr(client._client, "get", _spy_get(captured))

    client.get_institutional_investors_buy_sell("2330", "2026-04-01", "2026-04-29")

    assert captured["url"] == FinMindClient.BASE_URL
    assert captured["params"]["dataset"] == "TaiwanStockInstitutionalInvestorsBuySell"
    assert captured["params"]["data_id"] == "2330"
    assert captured["params"]["start_date"] == "2026-04-01"
    assert captured["params"]["end_date"] == "2026-04-29"


def test_margin_method_uses_correct_dataset(monkeypatch) -> None:
    client = FinMindClient()
    captured: dict = {}
    monkeypatch.setattr(client._client, "get", _spy_get(captured))

    client.get_margin_purchase_short_sale("2330", "2026-04-01", "2026-04-29")

    assert captured["params"]["dataset"] == "TaiwanStockMarginPurchaseShortSale"
    assert captured["params"]["data_id"] == "2330"


def test_token_is_forwarded_when_present(monkeypatch) -> None:
    client = FinMindClient()
    client._token = "secret-token"
    captured: dict = {}
    monkeypatch.setattr(client._client, "get", _spy_get(captured))

    client.get_institutional_investors_buy_sell("2330", "2026-04-01", "2026-04-29")

    assert captured["params"]["token"] == "secret-token"


def test_token_not_sent_when_absent(monkeypatch) -> None:
    client = FinMindClient()
    client._token = ""
    captured: dict = {}
    monkeypatch.setattr(client._client, "get", _spy_get(captured))

    client.get_margin_purchase_short_sale("2330", "2026-04-01", "2026-04-29")

    assert "token" not in captured["params"]


def test_institutional_http_500_raises(monkeypatch) -> None:
    client = FinMindClient()
    monkeypatch.setattr(
        client._client,
        "get",
        lambda *a, **k: _fake_response(500, None, text="Internal Server Error"),
    )

    with pytest.raises(FinMindConnectionError, match="500"):
        client.get_institutional_investors_buy_sell(
            "2330", "2026-04-01", "2026-04-29"
        )


def test_margin_http_500_raises(monkeypatch) -> None:
    client = FinMindClient()
    monkeypatch.setattr(
        client._client,
        "get",
        lambda *a, **k: _fake_response(500, None, text="Internal Server Error"),
    )

    with pytest.raises(FinMindConnectionError, match="500"):
        client.get_margin_purchase_short_sale("2330", "2026-04-01", "2026-04-29")


def test_missing_data_list_raises(monkeypatch) -> None:
    client = FinMindClient()
    monkeypatch.setattr(
        client._client,
        "get",
        lambda *a, **k: _fake_response(200, {"msg": "ok but no data"}),
    )

    with pytest.raises(FinMindConnectionError, match="missing 'data'"):
        client.get_institutional_investors_buy_sell(
            "2330", "2026-04-01", "2026-04-29"
        )


def test_returns_data_list_on_success(monkeypatch) -> None:
    client = FinMindClient()
    body = {
        "data": [
            {
                "date": "2026-04-29",
                "stock_id": "2330",
                "name": "Foreign_Investor",
                "buy": 10_000_000,
                "sell": 2_000_000,
            }
        ]
    }
    monkeypatch.setattr(client._client, "get", lambda *a, **k: _fake_response(200, body))

    rows = client.get_institutional_investors_buy_sell(
        "2330", "2026-04-29", "2026-04-29"
    )
    assert rows == body["data"]
