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

    def get_futures_institutional_investors(
        self, futures_id: str, start: str, end: str
    ) -> list[dict[str, Any]]:
        """TaiwanFuturesInstitutionalInvestors rows for a futures contract
        (e.g. ``TX`` for the TAIFEX index future). Used by the dashboard
        market Risk-Off gate to read foreign net-short open interest."""
        return self._fetch_dataset(
            "TaiwanFuturesInstitutionalInvestors", futures_id, start, end
        )

    def get_taiwan_stock_info(self) -> list[dict[str, Any]]:
        """Full TW market symbol roster (TaiwanStockInfo). No symbol/date filter."""
        params: dict[str, str] = {"dataset": "TaiwanStockInfo"}
        if self._token:
            params["token"] = self._token
        return self._dispatch(params, label="TaiwanStockInfo")

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
        return self._dispatch(params, label=symbol)

    def _dispatch(
        self, params: dict[str, str], *, label: str
    ) -> list[dict[str, Any]]:
        try:
            response = self._client.get(self.BASE_URL, params=params)
        except httpx.HTTPError as exc:
            raise FinMindConnectionError(
                f"FinMind request failed for {label}: {exc}"
            ) from exc

        if response.status_code != 200:
            raise FinMindConnectionError(
                f"FinMind returned HTTP {response.status_code} for {label}: "
                f"{response.text[:200]}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise FinMindConnectionError(
                f"FinMind returned non-JSON body for {label}: {exc}"
            ) from exc

        data = payload.get("data")
        if not isinstance(data, list):
            raise FinMindConnectionError(
                f"FinMind response missing 'data' list for {label}: "
                f"keys={list(payload)[:5]}"
            )
        return data
