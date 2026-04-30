"""Thin FinMind REST client (smoke-test scope only).

Spec: openspec/changes/external-connectors-and-cost/specs/external-connectors/spec.md

No fallback chain, no caching, no retry. Phase 1 ``data_pipeline_skill`` will
add fallback to TWSE OpenAPI / twstock / Parquet cache.
"""

from __future__ import annotations

from typing import Any

import httpx

from ohmystock.config import Settings


class FinMindConnectionError(RuntimeError):
    """Raised on connection / non-2xx / JSON parse failures."""


class FinMindClient:
    BASE_URL = "https://api.finmindtrade.com/api/v4/data"

    def __init__(self) -> None:
        self._token = Settings().finmind_token
        self._client = httpx.Client(timeout=10.0)

    def get_taiwan_stock_price(
        self, symbol: str, start: str, end: str
    ) -> list[dict[str, Any]]:
        return self._fetch_dataset("TaiwanStockPrice", symbol, start, end)

    def get_institutional_investors_buy_sell(
        self, symbol: str, start: str, end: str
    ) -> list[dict[str, Any]]:
        return self._fetch_dataset(
            "TaiwanStockInstitutionalInvestorsBuySell", symbol, start, end
        )

    def get_margin_purchase_short_sale(
        self, symbol: str, start: str, end: str
    ) -> list[dict[str, Any]]:
        return self._fetch_dataset(
            "TaiwanStockMarginPurchaseShortSale", symbol, start, end
        )

    def _fetch_dataset(
        self, dataset: str, symbol: str, start: str, end: str
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {
            "dataset": dataset,
            "data_id": symbol,
            "start_date": start,
            "end_date": end,
        }
        if self._token:
            params["token"] = self._token

        try:
            response = self._client.get(self.BASE_URL, params=params)
        except httpx.HTTPError as exc:
            raise FinMindConnectionError(
                f"FinMind request failed for {symbol}: {exc}"
            ) from exc

        if response.status_code != 200:
            raise FinMindConnectionError(
                f"FinMind returned HTTP {response.status_code} for {symbol}: "
                f"{response.text[:200]}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise FinMindConnectionError(
                f"FinMind returned non-JSON body for {symbol}: {exc}"
            ) from exc

        data = payload.get("data")
        if not isinstance(data, list):
            raise FinMindConnectionError(
                f"FinMind response missing 'data' list for {symbol}: "
                f"keys={list(payload)[:5]}"
            )
        return data
