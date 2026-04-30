"""twstock adapter for the DataSource protocol.

Spec: openspec/changes/market-data-fetch-cache/specs/market-data-cache/spec.md
"""

from __future__ import annotations

from datetime import date as date_type, datetime

from twstock import Stock

from ohmystock.data.sources.base import BarRow


class TwstockSource:
    name = "twstock"

    def fetch_daily(self, symbol: str, start: str, end: str) -> list[BarRow]:
        try:
            year, month = _parse_year_month(start)
            stock = Stock(symbol)
            raw = stock.fetch_from(year, month)
        except Exception as exc:
            raise RuntimeError(f"twstock failed for {symbol}: {exc}") from exc

        out: list[BarRow] = []
        for row in raw:
            ts = _row_date_iso(row.date)
            if ts < start or ts > end:
                continue
            # capacity is in shares; //1000 to 張 for cache consistency.
            out.append(
                BarRow(
                    ts=ts,
                    o=float(row.open),
                    h=float(row.high),
                    l=float(row.low),
                    c=float(row.close),
                    v=int(row.capacity) // 1000,
                    amount=int(row.turnover),
                )
            )
        return out


def _parse_year_month(iso_date: str) -> tuple[int, int]:
    dt = datetime.strptime(iso_date, "%Y-%m-%d")
    return dt.year, dt.month


def _row_date_iso(value: datetime | date_type) -> str:
    return value.strftime("%Y-%m-%d")
