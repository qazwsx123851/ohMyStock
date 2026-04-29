"""Thin Shioaji simulation-mode client (smoke-test scope only).

Spec: openspec/changes/external-connectors-and-cost/specs/external-connectors/spec.md

Live mode is intentionally not supported in this class — going live requires a
separate ``ShioajiLiveClient`` that takes CA credentials. Simulation is
hardcoded so it cannot be flipped via parameter.
"""

from __future__ import annotations

from typing import Any

import shioaji as sj

from ohmystock.config import Settings


class ShioajiConnectionError(RuntimeError):
    """Raised on connection / login / snapshot fetch failures."""


class ShioajiPaperClient:
    def __init__(self) -> None:
        settings = Settings()
        self._api_key = settings.shioaji_api_key
        self._secret_key = settings.shioaji_secret_key
        self._api = sj.Shioaji(simulation=True)
        self._logged_in = False

    def login(self) -> None:
        try:
            self._api.login(
                api_key=self._api_key,
                secret_key=self._secret_key,
            )
        except Exception as exc:
            raise ShioajiConnectionError(
                f"Shioaji login failed: {exc}"
            ) from exc
        self._logged_in = True

    def get_snapshot(self, symbol: str) -> dict[str, Any]:
        if not self._logged_in:
            raise ShioajiConnectionError(
                "Shioaji client must call login() before get_snapshot()"
            )
        try:
            contract = self._api.Contracts.Stocks[symbol]
            snapshots = self._api.snapshots([contract])
        except Exception as exc:
            raise ShioajiConnectionError(
                f"Shioaji snapshot failed for {symbol}: {exc}"
            ) from exc

        if not snapshots:
            raise ShioajiConnectionError(
                f"Shioaji returned no snapshot for {symbol}"
            )
        snap = snapshots[0]
        return {
            "symbol": symbol,
            "close": getattr(snap, "close", None),
            "ts": getattr(snap, "ts", None),
        }
