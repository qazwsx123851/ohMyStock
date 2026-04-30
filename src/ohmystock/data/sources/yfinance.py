"""yfinance adapter for the DataSource protocol.

Spec: openspec/changes/market-data-fetch-cache/specs/market-data-cache/spec.md
"""

from __future__ import annotations

from yfinance import Ticker

from ohmystock.data.sources.base import BarRow


class YFinanceSource:
    name = "yfinance"

    def fetch_daily(self, symbol: str, start: str, end: str) -> list[BarRow]:
        try:
            df = self._to_yahoo_symbol(symbol, start, end)
        except Exception as exc:
            raise RuntimeError(f"yfinance failed for {symbol}: {exc}") from exc

        if df is None or df.empty:
            return []

        out: list[BarRow] = []
        for ts, row in df.iterrows():
            iso = ts.strftime("%Y-%m-%d")
            close = float(row["Close"])
            volume_shares = int(row["Volume"])
            # Volume is shares → //1000 to 張. yfinance has no turnover field;
            # estimate as close * shares (TWD).
            out.append(
                BarRow(
                    ts=iso,
                    o=float(row["Open"]),
                    h=float(row["High"]),
                    l=float(row["Low"]),
                    c=close,
                    v=volume_shares // 1000,
                    amount=int(close * volume_shares),
                )
            )
        return out

    @staticmethod
    def _to_yahoo_symbol(symbol: str, start: str, end: str):
        """Try `.TW` (TWSE) then `.TWO` (OTC). Returns the first non-empty df, else None."""
        for suffix in (".TW", ".TWO"):
            df = Ticker(f"{symbol}{suffix}").history(
                start=start, end=end, interval="1d"
            )
            if not df.empty:
                return df
        return None
