"""Phase 5 data_loader node — pure-data, no LLM.

Spec: openspec/changes/phase5-review-mvp/specs/post-trade-review-pipeline/spec.md
SSOT: docs/post-trade-review-rubric.md §1
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from typing import Protocol

from ohmystock.review.models import (
    DataLoaderOutput,
    DataLoaderStats,
    ExpireRow,
    Period,
    RejectRow,
    TradeRow,
)


_POST_EXIT_DAYS = 21
_MIN_DAYS_FOR_VALID_RETURN = 20
_RETURN_DECIMALS = 4


class MarketDataLoader(Protocol):
    """Adapter the data_loader uses to fetch post-exit close series.

    Implementations must return up to ``days`` close prices for trading
    days strictly after ``exit_date``, sorted chronologically. An empty
    list (or ``< 20``) triggers ``data_missing=true`` per rubric §1.
    """

    def select_bars(
        self, symbol: str, exit_date: date, days: int
    ) -> list[float]:
        ...


def run_data_loader(
    period_from: date,
    period_to: date,
    db_conn: sqlite3.Connection,
    market_data_loader: MarketDataLoader,
    *,
    limit_trades: int | None = None,
) -> DataLoaderOutput:
    """Build the ``data.json`` payload for ``[period_from, period_to]``.

    ``limit_trades`` (if not ``None``) truncates the trades list to the
    first N items after sorting by ``entry_ts`` ASC. Rejected and expired
    rows are never truncated.
    """

    pf, pt = period_from.isoformat(), period_to.isoformat()

    closed = _query_closed_trades(db_conn, pf, pt)
    rejects = _query_rejects(db_conn, pf, pt)
    expires = _query_expires(db_conn, pf, pt)

    trades: list[TradeRow] = []
    for entry_record, exit_record in closed:
        trades.append(_build_trade_row(entry_record, exit_record, market_data_loader))

    trades.sort(key=lambda t: (t.entry_ts, t.decision_id))
    if limit_trades is not None:
        trades = trades[:limit_trades]

    rejects.sort(key=lambda r: (r.created_at, r.decision_id))
    expires.sort(key=lambda e: (e.created_at, e.decision_id))

    stats = _compute_stats(trades, rejects, expires)

    return DataLoaderOutput(
        period=Period.model_validate({"from": period_from, "to": period_to}),
        trades=trades,
        rejected=rejects,
        expired=expires,
        stats=stats,
    )


def _query_closed_trades(
    conn: sqlite3.Connection, pf: str, pt: str
) -> list[tuple[dict, dict]]:
    rows = conn.execute(
        """
        SELECT
            x.decision_id    AS decision_id,
            x.symbol         AS symbol,
            x.created_at     AS exit_ts,
            x.payload_json   AS exit_payload,
            e.created_at     AS entry_ts,
            e.payload_json   AS entry_payload
        FROM journal_entries x
        JOIN journal_entries e
          ON e.decision_id = x.decision_id AND e.kind = 'entry'
        WHERE x.kind = 'exit'
          AND substr(x.created_at, 1, 10) BETWEEN ? AND ?
        ORDER BY x.created_at ASC, x.id ASC
        """,
        (pf, pt),
    ).fetchall()

    out: list[tuple[dict, dict]] = []
    for decision_id, symbol, exit_ts, exit_pj, entry_ts, entry_pj in rows:
        try:
            exit_payload = json.loads(exit_pj)
            entry_payload = json.loads(entry_pj)
        except json.JSONDecodeError:
            continue
        entry_record = {
            "decision_id": decision_id,
            "symbol": symbol,
            "entry_ts": entry_ts,
            "payload": entry_payload,
        }
        exit_record = {
            "decision_id": decision_id,
            "symbol": symbol,
            "exit_ts": exit_ts,
            "payload": exit_payload,
        }
        out.append((entry_record, exit_record))
    return out


def _query_rejects(
    conn: sqlite3.Connection, pf: str, pt: str
) -> list[RejectRow]:
    rows = conn.execute(
        """
        SELECT decision_id, symbol, created_at, payload_json
        FROM journal_entries
        WHERE kind = 'reject'
          AND substr(created_at, 1, 10) BETWEEN ? AND ?
        ORDER BY created_at ASC, id ASC
        """,
        (pf, pt),
    ).fetchall()

    out: list[RejectRow] = []
    for decision_id, symbol, created_at, payload_json in rows:
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            continue
        out.append(
            RejectRow(
                decision_id=str(decision_id),
                symbol=str(symbol),
                created_at=str(created_at),
                reject_layer=str(payload.get("reject_layer") or "unknown"),
                reject_reason=str(payload.get("reject_reason") or ""),
            )
        )
    return out


def _query_expires(
    conn: sqlite3.Connection, pf: str, pt: str
) -> list[ExpireRow]:
    rows = conn.execute(
        """
        SELECT decision_id, symbol, created_at, payload_json
        FROM journal_entries
        WHERE kind = 'expire'
          AND substr(created_at, 1, 10) BETWEEN ? AND ?
        ORDER BY created_at ASC, id ASC
        """,
        (pf, pt),
    ).fetchall()

    out: list[ExpireRow] = []
    for decision_id, symbol, created_at, payload_json in rows:
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            continue
        out.append(
            ExpireRow(
                decision_id=str(decision_id),
                symbol=str(symbol),
                created_at=str(created_at),
                expire_reason=str(payload.get("expire_reason") or ""),
            )
        )
    return out


def _build_trade_row(
    entry_record: dict,
    exit_record: dict,
    market_data_loader: MarketDataLoader,
) -> TradeRow:
    ep = entry_record["payload"]
    xp = exit_record["payload"]

    entry_price = _opt_float(ep.get("actual_entry_price"))
    exit_price_raw = (
        xp.get("actual_exit_price")
        if xp.get("actual_exit_price") is not None
        else xp.get("close_price_evaluated")
    )
    exit_price = _opt_float(exit_price_raw)
    pnl_pct = _opt_float(xp.get("pnl_pct"))
    hold_days = _opt_int(xp.get("hold_days"))
    exit_tag = xp.get("exit_tag")
    cited_skills = list(ep.get("cited_skills") or [])
    risk_flags = list(ep.get("risk_flags") or [])
    entry_thesis = str(ep.get("entry_thesis") or ep.get("llm_reasoning") or "")
    confidence = _opt_float(ep.get("llm_confidence"))
    sector_value = ep.get("sector")
    sector_str = str(sector_value) if sector_value else None

    exit_date = _parse_iso_date(exit_record["exit_ts"])
    closes = market_data_loader.select_bars(
        exit_record["symbol"], exit_date, _POST_EXIT_DAYS
    )

    if exit_price is None or len(closes) < _MIN_DAYS_FOR_VALID_RETURN:
        data_missing = True
        ret5 = ret10 = ret20 = None
    else:
        data_missing = False
        ret5 = _post_return(exit_price, closes, 5)
        ret10 = _post_return(exit_price, closes, 10)
        ret20 = _post_return(exit_price, closes, 20)

    return TradeRow(
        decision_id=str(entry_record["decision_id"]),
        symbol=str(entry_record["symbol"]),
        entry_ts=str(entry_record["entry_ts"]),
        exit_ts=str(exit_record["exit_ts"]),
        entry_price=entry_price,
        exit_price=exit_price,
        pnl_pct=pnl_pct,
        hold_days=hold_days,
        exit_tag=exit_tag,
        thesis_held=None,
        post_exit_return_5d=ret5,
        post_exit_return_10d=ret10,
        post_exit_return_20d=ret20,
        entry_thesis=entry_thesis,
        cited_skills=cited_skills,
        risk_flags_at_entry=risk_flags,
        confidence=confidence,
        sector=sector_str,
        data_missing=data_missing,
    )


def _post_return(exit_price: float, closes: list[float], n_days: int) -> float:
    target = closes[n_days - 1]
    return round(target / exit_price - 1.0, _RETURN_DECIMALS)


def _opt_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _opt_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _parse_iso_date(ts: str) -> date:
    return datetime.fromisoformat(ts).date()


def _compute_stats(
    trades: list[TradeRow],
    rejects: list[RejectRow],
    expires: list[ExpireRow],
) -> DataLoaderStats:
    total_entries = len(trades)
    total_rejects = len(rejects)
    total_expires = len(expires)
    expire_rate = 0.0
    if total_entries > 0:
        expire_rate = round(total_expires / total_entries, _RETURN_DECIMALS)
    return DataLoaderStats(
        total_entries=total_entries,
        total_rejects=total_rejects,
        total_expires=total_expires,
        expire_rate=expire_rate,
    )
