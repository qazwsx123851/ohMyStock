"""score_watchlist — Phase 2B engine.

Spec: openspec/changes/phase-2b-scoring-engine/specs/phase-2b-scoring-engine/spec.md
"""

from __future__ import annotations

import re
import sqlite3
import time
from datetime import datetime
from typing import Any, Callable

from ohmystock.chip.margin_short import get_margin_short
from ohmystock.chip.three_major import get_three_major_investors
from ohmystock.data.market_data import get_kline
from ohmystock.scoring.context import ScoringContext
from ohmystock.scoring.models import Phase2BCandidate, SubScoreResult
from ohmystock.scoring.registry import dispatch, list_subscorers


CODE_INVALID_INPUT = "INVALID_INPUT"
CODE_DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
CODE_INTERNAL_ERROR = "INTERNAL_ERROR"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SYMBOL_RE = re.compile(r"^\d{4,6}(KY)?$")

_CATEGORY_CAPS = {
    "technical": 40.0,
    "chip": 25.0,
    "fundamental": 25.0,
    "sentiment": 10.0,
}

_FINAL_CAP = 100.0
_RISK_OFF_CEILING = 50.0
_GREEN_THRESHOLD = 65.0
_YELLOW_THRESHOLD = 50.0


def score_watchlist(
    asof_date: str,
    candidates: list[str],
    *,
    risk_off_resolver: Callable[[], bool] = lambda: False,
    top_n: int | None = None,
    _conn: sqlite3.Connection | None = None,
    _today: str | None = None,
) -> dict:
    started = time.perf_counter()
    try:
        err = _validate_inputs(asof_date, candidates, risk_off_resolver, top_n)
        if err is not None:
            return _error_envelope(CODE_INVALID_INPUT, err, False, started)

        risk_off = bool(risk_off_resolver())

        scored_candidates: list[Phase2BCandidate] = []
        for symbol in candidates:
            ctx = _build_context(symbol, asof_date, _conn, _today)
            subscores = _run_subscorers(ctx)
            cand = _aggregate(symbol, asof_date, subscores, risk_off)
            scored_candidates.append(cand)

        scored_candidates.sort(key=lambda c: (-c.final_score, c.symbol))
        if top_n is not None:
            scored_candidates = scored_candidates[:top_n]

        payload = {
            "asof_date": asof_date,
            "candidates": [c.model_dump() for c in scored_candidates],
        }
        return _success_envelope(payload, started)
    except Exception as exc:  # noqa: BLE001 — translate to envelope
        return _error_envelope(
            CODE_INTERNAL_ERROR, f"unexpected: {exc}", True, started
        )


def _validate_inputs(
    asof_date: Any,
    candidates: Any,
    risk_off_resolver: Any,
    top_n: Any,
) -> str | None:
    if not isinstance(asof_date, str) or not _DATE_RE.match(asof_date):
        return f"asof_date must match YYYY-MM-DD, got {asof_date!r}"
    try:
        datetime.strptime(asof_date, "%Y-%m-%d")
    except ValueError:
        return f"asof_date is not a valid date: {asof_date!r}"

    if not isinstance(candidates, list) or len(candidates) == 0:
        return "candidates must be a non-empty list"
    for c in candidates:
        if not isinstance(c, str) or not _SYMBOL_RE.match(c):
            return f"candidate symbol must match ^\\d{{4,6}}(KY)?$, got {c!r}"

    if top_n is not None:
        if isinstance(top_n, bool) or not isinstance(top_n, int):
            return f"top_n must be int >= 1 or None, got {top_n!r}"
        if top_n < 1:
            return f"top_n must be int >= 1 or None, got {top_n!r}"

    if not callable(risk_off_resolver):
        return f"risk_off_resolver must be callable, got {risk_off_resolver!r}"

    return None


def _build_context(
    symbol: str,
    asof_date: str,
    conn: sqlite3.Connection | None,
    today: str | None,
) -> ScoringContext:
    bars_env = get_kline(
        symbol,
        period="1d",
        bars=250,
        end_date=asof_date,
        _conn=conn,
        _today=today,
    )
    chip_env = get_three_major_investors(
        symbol,
        days=30,
        end_date=asof_date,
        _conn=conn,
        _today=today,
    )
    margin_env = get_margin_short(
        symbol,
        days=30,
        end_date=asof_date,
        _conn=conn,
        _today=today,
    )

    bars = bars_env["data"]["bars"] if bars_env.get("ok") else []
    chip_rows = chip_env["data"]["rows"] if chip_env.get("ok") else []
    margin_rows = margin_env["data"]["rows"] if margin_env.get("ok") else []

    return ScoringContext(
        asof_date=asof_date,
        symbol=symbol,
        bars=bars,
        three_major=chip_rows,
        margin_short=margin_rows,
    )


def _run_subscorers(ctx: ScoringContext) -> list[SubScoreResult]:
    results: list[SubScoreResult] = []
    metas = list_subscorers()
    meta_by_name = {name: (cat, mp) for name, cat, mp in metas}
    for name, _category, _max in metas:
        try:
            results.append(dispatch(name, ctx))
        except Exception as exc:  # noqa: BLE001 — sub-scorer error → status="error"
            cat, mp = meta_by_name.get(name, ("technical", 0.0))
            results.append(
                SubScoreResult(
                    name=name,
                    category=cat,
                    points=0.0,
                    max_points=float(mp),
                    status="error",
                    error_message=str(exc),
                )
            )
    return results


def _aggregate(
    symbol: str,
    asof_date: str,
    subscores: list[SubScoreResult],
    risk_off: bool,
) -> Phase2BCandidate:
    sums = {"technical": 0.0, "chip": 0.0, "fundamental": 0.0, "sentiment": 0.0}
    for s in subscores:
        if s.status == "scored":
            sums[s.category] += s.points

    subtotals = {
        cat: max(0.0, min(_CATEGORY_CAPS[cat], total)) for cat, total in sums.items()
    }
    final_score = min(_FINAL_CAP, sum(subtotals.values()))
    if risk_off:
        final_score = min(final_score, _RISK_OFF_CEILING)

    if final_score >= _GREEN_THRESHOLD:
        classification = "green"
    elif final_score >= _YELLOW_THRESHOLD:
        classification = "yellow"
    else:
        classification = "red"

    return Phase2BCandidate(
        symbol=symbol,
        asof_date=asof_date,
        final_score=final_score,
        tech_subtotal=subtotals["technical"],
        chip_subtotal=subtotals["chip"],
        fund_subtotal=subtotals["fundamental"],
        sent_subtotal=subtotals["sentiment"],
        classification=classification,
        risk_off_applied=risk_off,
        subscores=subscores,
    )


def _success_envelope(data: dict, started: float) -> dict:
    return {
        "ok": True,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "data": data,
        "error": None,
    }


def _error_envelope(code: str, message: str, retriable: bool, started: float) -> dict:
    return {
        "ok": False,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "data": None,
        "error": {"code": code, "message": message, "retriable": retriable},
    }
