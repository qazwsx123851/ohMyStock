"""``ohmystock evaluate-exits`` — daily exit evaluation CLI driver.

Wraps ``ohmystock.exit_engine.evaluate_open_positions``: scan all
``decision_status="confirmed"`` entries, evaluate the v0 stop_loss / T1 /
time_stop conditions against today's close price, and write ``kind=exit``
rows for any that triggered (atomically flipping the entry to
``decision_status="closed"``).

Spec: openspec/changes/exit-engine-v0/specs/cli-and-config/spec.md

Exit codes:
- ``0`` — evaluation finished (regardless of how many positions closed)
- ``2`` — usage error (bad ``--asof``, missing flag, ``--price`` w/o ``--symbol``)
- ``3`` — ``ExitEngineError`` (e.g. ``market_data_unavailable``); failed
  symbols listed on stderr
"""

from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import typer

from ohmystock.config import Settings
from ohmystock.exit_engine import (
    ExitEngineError,
    ExitResult,
    MarketDataLookup,
    evaluate_open_positions,
)
from ohmystock.journal.schema import init_schema


_TPE_TZ = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class _SystemClock:
    def now_iso(self) -> str:
        return datetime.now(_TPE_TZ).isoformat(timespec="seconds")


_SYSTEM_CLOCK = _SystemClock()


class _OverrideMarketData:
    """In-memory ``MarketDataLookup`` used when ``--price`` overrides lookup."""

    def __init__(self, prices: dict[str, float]) -> None:
        self._prices = dict(prices)

    def get_close(self, symbol: str, asof: date) -> float | None:  # noqa: ARG002
        return self._prices.get(symbol)


class _LiveMarketData:
    """Default ``MarketDataLookup`` backed by ``data.market_data.get_kline``."""

    def get_close(self, symbol: str, asof: date) -> float | None:
        from ohmystock.data.market_data import get_kline

        env = get_kline(symbol, period="1d", bars=5, end_date=asof.isoformat())
        if not env.get("ok"):
            return None
        bars = env.get("data", {}).get("bars") or []
        for bar in reversed(bars):
            if str(bar.get("ts")) <= asof.isoformat():
                try:
                    return float(bar["c"])
                except (KeyError, TypeError, ValueError):
                    return None
        return None


def _open_journal_db(
    db_override: str | None, settings: Settings
) -> sqlite3.Connection:
    raw = db_override or settings.ohmystock_db_path
    path = Path(raw).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    init_schema(conn)
    return conn


def _result_to_dict(r: ExitResult) -> dict:
    base = {
        "decision_id": r.decision_id,
        "action": r.action,
    }
    if r.decision is not None:
        base.update(
            {
                "exit_tag": r.decision.exit_tag,
                "actual_exit_price": r.decision.actual_exit_price,
                "pnl_pct": r.decision.pnl_pct,
                "hold_days": r.decision.hold_days,
            }
        )
    return base


def evaluate_exits(
    asof: str = typer.Option(
        ...,
        "--asof",
        help="評估的交易日 YYYY-MM-DD（用於 lookup close price 與計算 hold_days）",
    ),
    symbol: str | None = typer.Option(
        None,
        "--symbol",
        help="限定評估單一 symbol（人工 spot-check 用）",
    ),
    price: float | None = typer.Option(
        None,
        "--price",
        help="覆寫 market_data lookup 的 close 價（必須與 --symbol 同時提供）",
    ),
    db: str | None = typer.Option(
        None,
        "--db",
        help="SQLite 路徑；預設讀 OHMYSTOCK_DB_PATH",
    ),
    json_out: bool = typer.Option(
        False,
        "--json/--no-json",
        help="JSON dump 輸出（含 asof / evaluated / exit_code）",
    ),
) -> None:
    """Evaluate exits for all confirmed entries — write kind=exit rows."""

    try:
        asof_date = date.fromisoformat(asof)
    except ValueError as exc:
        typer.echo(f"--asof must be YYYY-MM-DD date: {exc}", err=True)
        raise typer.Exit(2) from exc

    if price is not None and symbol is None:
        typer.echo("--price requires --symbol", err=True)
        raise typer.Exit(2)

    if price is not None:
        market_data: MarketDataLookup = _OverrideMarketData({symbol: price})  # type: ignore[dict-item]
    else:
        market_data = _LiveMarketData()

    settings = Settings()
    conn = _open_journal_db(db, settings)
    try:
        try:
            results = evaluate_open_positions(
                conn,
                market_data=market_data,
                asof=asof_date,
                clock=_SYSTEM_CLOCK,
                symbol_filter=symbol,
            )
        except ExitEngineError as exc:
            typer.echo(f"{exc.code}: {exc}", err=True)
            if exc.failed_symbols:
                typer.echo(
                    f"failed_symbols: {', '.join(exc.failed_symbols)}", err=True
                )
            raise typer.Exit(3) from exc
    finally:
        conn.close()

    if json_out:
        sys.stdout.write(
            json.dumps(
                {
                    "asof": asof_date.isoformat(),
                    "evaluated": [_result_to_dict(r) for r in results],
                    "exit_code": 0,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        raise typer.Exit(0)

    closed = [r for r in results if r.action == "closed"]
    held = [r for r in results if r.action == "held"]
    typer.echo(f"asof: {asof_date.isoformat()}")
    typer.echo(f"{len(closed)} closed, {len(held)} held")
    for r in results:
        if r.decision is not None:
            typer.echo(
                f"{r.decision_id} {r.action} {r.decision.exit_tag} "
                f"exit_price={r.decision.actual_exit_price} "
                f"pnl_pct={r.decision.pnl_pct:.2f} "
                f"hold_days={r.decision.hold_days}"
            )
        else:
            typer.echo(f"{r.decision_id} {r.action}")
    raise typer.Exit(0)
