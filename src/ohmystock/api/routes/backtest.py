"""Admin HTTP surface for the backtest engine.

Endpoints (all require Bearer auth via ``require_admin``, share the
``{ok, data, error}`` envelope, and use a per-request SQLite connection
from ``Depends(get_db)``):

* ``GET  /api/admin/backtest/strategies`` — registry-driven strategy list.
* ``POST /api/admin/backtest/run``        — synchronous run, persists row.
* ``GET  /api/admin/backtest/jobs``       — paginated history (no result_json).
* ``GET  /api/admin/backtest/jobs/{id}``  — full detail incl. derived drawdown.

Spec: openspec/changes/web-admin-backtest-pages/specs/admin-backtest-endpoints/spec.md
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ohmystock.api.auth import require_admin
from ohmystock.api.routes._deps import get_db
from ohmystock.api.routes._envelope import (
    map_exception_to_envelope,
    to_error,
    to_success,
)
from ohmystock.backtest import storage as backtest_storage
from ohmystock.backtest.engine import run_backtest
from ohmystock.backtest.strategy.registry import available_strategies
from ohmystock.backtest.strategy.sma_cross import SmaCross
from ohmystock.data.cache import init_market_data_schema, select_bars


router = APIRouter(dependencies=[Depends(require_admin)])

_TPE = ZoneInfo("Asia/Taipei")
_MAX_SYMBOLS = 50
_MAX_PERIOD_DAYS = 1830  # ~5 years
_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100


_STRATEGY_FACTORIES: dict[str, Any] = {
    "sma_cross": SmaCross,
}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class BacktestRunInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy: str
    symbols: list[str] = Field(min_length=1)
    period_from: str
    period_to: str
    initial_capital: float = 1_000_000.0
    fee_discount: float = 0.28
    slippage_bps: int = 30
    day_trade: bool = False


class BacktestRunResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_id: str
    status: str
    elapsed_ms: int


class JobSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    strategy: str
    period_from: str
    period_to: str
    status: str
    elapsed_ms: int
    created_at: str
    annual_return_pct: float | None
    sharpe: float | None
    max_drawdown_pct: float | None
    win_rate_pct: float | None


class EquityPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: str
    equity: float


class DrawdownPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: str
    dd: float


class BacktestTrade(BaseModel):
    model_config = ConfigDict(frozen=True)

    entry_date: str
    exit_date: str
    symbol: str
    side: str
    qty: int
    entry_price: float
    exit_price: float
    pnl_twd: float
    hold_days: int
    pattern: str | None = None


class JobDetailMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    annual_return_pct: float | None
    sharpe: float | None
    max_drawdown_pct: float | None
    win_rate_pct: float | None
    total_return_pct: float | None = None
    sortino: float | None = None
    profit_factor: float | None = None
    expectancy: float | None = None
    total_trades: int | None = None


class JobDetail(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    strategy: str
    period_from: str
    period_to: str
    custom_symbols: list[str]
    initial_capital: float
    status: str
    elapsed_ms: int
    created_at: str
    metrics: JobDetailMetrics | None
    equity_curve: list[EquityPoint]
    drawdown: list[DrawdownPoint]
    trades: list[BacktestTrade]
    error: dict[str, Any] | None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


_DATE_FMT = "%Y-%m-%d"


def _parse_date(value: str, field: str) -> date:
    try:
        return datetime.strptime(value, _DATE_FMT).date()
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD, got {value!r}") from exc


class _InvalidInputError(Exception):
    pass


class _InputTooLargeError(Exception):
    pass


class _MissingBarsError(Exception):
    def __init__(self, symbol: str) -> None:
        super().__init__(symbol)
        self.symbol = symbol


def _validate_run_input(payload: BacktestRunInput) -> tuple[date, date]:
    if payload.strategy not in _STRATEGY_FACTORIES:
        raise _InvalidInputError(
            f"strategy {payload.strategy!r} is not registered"
        )
    if len(payload.symbols) > _MAX_SYMBOLS:
        raise _InputTooLargeError(
            f"symbols.length must be <= {_MAX_SYMBOLS}, got {len(payload.symbols)}"
        )
    for sym in payload.symbols:
        if not (sym.isdigit() and 4 <= len(sym) <= 6):
            raise _InvalidInputError(f"symbol {sym!r} must be 4-6 digits")
    if payload.initial_capital <= 0:
        raise _InvalidInputError("initial_capital must be > 0")
    if not (0 < payload.fee_discount <= 1):
        raise _InvalidInputError("fee_discount must be in (0, 1]")
    if payload.slippage_bps < 0:
        raise _InvalidInputError("slippage_bps must be >= 0")

    pf = _parse_date(payload.period_from, "period_from")
    pt = _parse_date(payload.period_to, "period_to")
    if pt < pf:
        raise _InvalidInputError(
            f"period_to {payload.period_to} < period_from {payload.period_from}"
        )
    if (pt - pf).days > _MAX_PERIOD_DAYS:
        raise _InputTooLargeError(
            f"period spans {(pt - pf).days} days; max is {_MAX_PERIOD_DAYS}"
        )
    return pf, pt


# ---------------------------------------------------------------------------
# Result-payload helpers
# ---------------------------------------------------------------------------


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _summary_metrics_from_result(
    status: str, result_json: str
) -> dict[str, float | None]:
    if status != "completed":
        return {
            "annual_return_pct": None,
            "sharpe": None,
            "max_drawdown_pct": None,
            "win_rate_pct": None,
        }
    try:
        payload = json.loads(result_json)
    except (TypeError, ValueError):
        return {
            "annual_return_pct": None,
            "sharpe": None,
            "max_drawdown_pct": None,
            "win_rate_pct": None,
        }
    metrics = payload.get("metrics") if isinstance(payload, dict) else None
    if not isinstance(metrics, dict):
        return {
            "annual_return_pct": None,
            "sharpe": None,
            "max_drawdown_pct": None,
            "win_rate_pct": None,
        }
    return {
        "annual_return_pct": _safe_float(metrics.get("cagr")),
        "sharpe": _safe_float(metrics.get("sharpe")),
        "max_drawdown_pct": _safe_float(metrics.get("max_drawdown")),
        "win_rate_pct": _safe_float(metrics.get("win_rate")),
    }


def _detail_metrics_from_result(metrics_obj: dict[str, Any]) -> JobDetailMetrics:
    total_trades_raw = metrics_obj.get("total_trades")
    return JobDetailMetrics(
        annual_return_pct=_safe_float(metrics_obj.get("cagr")),
        sharpe=_safe_float(metrics_obj.get("sharpe")),
        max_drawdown_pct=_safe_float(metrics_obj.get("max_drawdown")),
        win_rate_pct=_safe_float(metrics_obj.get("win_rate")),
        total_return_pct=_safe_float(metrics_obj.get("total_return")),
        sortino=_safe_float(metrics_obj.get("sortino")),
        profit_factor=_safe_float(metrics_obj.get("profit_factor")),
        expectancy=_safe_float(metrics_obj.get("expectancy")),
        total_trades=int(total_trades_raw)
        if isinstance(total_trades_raw, (int, float))
        else None,
    )


def _derive_drawdown(
    equity_curve: list[dict[str, Any]],
) -> list[DrawdownPoint]:
    out: list[DrawdownPoint] = []
    peak = float("-inf")
    for point in equity_curve:
        equity = float(point.get("equity", 0.0))
        if equity > peak:
            peak = equity
        dd = 0.0 if peak <= 0 else equity / peak - 1.0
        out.append(DrawdownPoint(date=str(point.get("date", "")), dd=dd))
    return out


def _pair_trades(raw: list[dict[str, Any]]) -> list[BacktestTrade]:
    """FIFO-pair filled buys and sells per symbol into round-trip trades."""
    open_lots: dict[str, list[dict[str, Any]]] = {}
    out: list[BacktestTrade] = []
    for fill in raw:
        if fill.get("status") != "filled":
            continue
        sym = str(fill.get("symbol", ""))
        side = str(fill.get("side", ""))
        qty = int(fill.get("qty", 0))
        price = float(fill.get("fill_price", 0.0))
        fill_date = str(fill.get("fill_date", "")) or ""
        if not sym or qty <= 0 or not fill_date:
            continue
        if side == "buy":
            open_lots.setdefault(sym, []).append(
                {"qty": qty, "price": price, "date": fill_date}
            )
            continue
        if side != "sell":
            continue
        remaining = qty
        lots = open_lots.get(sym, [])
        while remaining > 0 and lots:
            lot = lots[0]
            used = min(remaining, lot["qty"])
            entry_date = lot["date"]
            try:
                hold_days = (
                    _parse_date(fill_date, "exit_date")
                    - _parse_date(entry_date, "entry_date")
                ).days
            except ValueError:
                hold_days = 0
            pnl = (price - lot["price"]) * used
            out.append(
                BacktestTrade(
                    entry_date=entry_date,
                    exit_date=fill_date,
                    symbol=sym,
                    side="long",
                    qty=used,
                    entry_price=lot["price"],
                    exit_price=price,
                    pnl_twd=pnl,
                    hold_days=hold_days,
                )
            )
            remaining -= used
            if used == lot["qty"]:
                lots.pop(0)
            else:
                lot["qty"] -= used
        if not lots:
            open_lots.pop(sym, None)
    return out


def _summarise_validation(exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()))
        msg = err.get("msg", "invalid value")
        parts.append(f"{loc}: {msg}" if loc else str(msg))
    return "; ".join(parts) if parts else "invalid request body"


def _hydrate_bars(
    conn: sqlite3.Connection,
    symbols: list[str],
    start: str,
    end: str,
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for sym in symbols:
        bars = select_bars(conn, sym, start, end)
        if not bars:
            raise _MissingBarsError(sym)
        out[sym] = list(bars)
    return out


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/api/admin/backtest/strategies")
def get_strategies() -> JSONResponse:
    try:
        entries = available_strategies()
    except Exception as exc:  # noqa: BLE001
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)
    return JSONResponse(
        status_code=200, content=to_success({"strategies": entries})
    )


@router.post("/api/admin/backtest/run")
def post_run(
    payload: dict[str, Any],
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    try:
        try:
            run_input = BacktestRunInput.model_validate(payload)
        except ValidationError as exc:
            return JSONResponse(
                status_code=400,
                content=to_error("invalid_input", _summarise_validation(exc)),
            )

        try:
            pf, pt = _validate_run_input(run_input)
        except _InvalidInputError as exc:
            return JSONResponse(
                status_code=400,
                content=to_error("invalid_input", str(exc)),
            )
        except _InputTooLargeError as exc:
            return JSONResponse(
                status_code=400,
                content=to_error("input_too_large", str(exc)),
            )

        backtest_storage.init_schema(conn)
        init_market_data_schema(conn)

        try:
            bars_by_symbol = _hydrate_bars(
                conn, list(run_input.symbols), pf.isoformat(), pt.isoformat()
            )
        except _MissingBarsError as exc:
            return JSONResponse(
                status_code=400,
                content=to_error(
                    "missing_bars",
                    f"no bars_daily rows for symbol {exc.symbol!r} "
                    f"in {pf.isoformat()}..{pt.isoformat()}",
                ),
            )

        strategy_factory = _STRATEGY_FACTORIES[run_input.strategy]
        strategy = strategy_factory()
        envelope = run_backtest(
            strategy,
            bars_by_symbol,
            period={"from": pf.isoformat(), "to": pt.isoformat()},
            initial_capital=run_input.initial_capital,
            fee_discount=run_input.fee_discount,
            slippage_bps=run_input.slippage_bps,
            day_trade=run_input.day_trade,
        )

        job_id = uuid.uuid4().hex
        created_at = datetime.now(_TPE).isoformat(timespec="seconds")
        if envelope.get("ok"):
            status_value = "completed"
            result_json = json.dumps(envelope.get("data") or {})
        else:
            status_value = "failed"
            result_json = json.dumps({"error": envelope.get("error") or {}})

        elapsed_ms = int(envelope.get("elapsed_ms") or 0)
        backtest_storage.insert_job(
            conn,
            backtest_storage.BacktestJobRow(
                id=job_id,
                strategy=run_input.strategy,
                period_from=pf.isoformat(),
                period_to=pt.isoformat(),
                custom_symbols_json=json.dumps(list(run_input.symbols)),
                initial_capital=float(run_input.initial_capital),
                status=status_value,
                elapsed_ms=elapsed_ms,
                result_json=result_json,
                created_at=created_at,
            ),
        )
        return JSONResponse(
            status_code=200,
            content=to_success(
                {
                    "job_id": job_id,
                    "status": status_value,
                    "elapsed_ms": elapsed_ms,
                }
            ),
        )
    except Exception as exc:  # noqa: BLE001
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)


@router.get("/api/admin/backtest/jobs")
def get_jobs(
    limit: int = Query(default=_DEFAULT_LIMIT),
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    try:
        clamped = max(1, min(int(limit), _MAX_LIMIT))
        backtest_storage.init_schema(conn)
        rows = backtest_storage.select_recent(conn, limit=clamped)
        items: list[dict[str, Any]] = []
        for row in rows:
            metrics = _summary_metrics_from_result(
                row["status"], row["result_json"]
            )
            summary = JobSummary(
                id=row["id"],
                strategy=row["strategy"],
                period_from=row["period_from"],
                period_to=row["period_to"],
                status=row["status"],
                elapsed_ms=row["elapsed_ms"],
                created_at=row["created_at"],
                annual_return_pct=metrics["annual_return_pct"],
                sharpe=metrics["sharpe"],
                max_drawdown_pct=metrics["max_drawdown_pct"],
                win_rate_pct=metrics["win_rate_pct"],
            )
            items.append(summary.model_dump(mode="json"))
    except Exception as exc:  # noqa: BLE001
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)
    return JSONResponse(
        status_code=200,
        content=to_success({"items": items, "count": len(items)}),
    )


@router.get("/api/admin/backtest/jobs/{job_id}")
def get_job_detail(
    job_id: str,
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    try:
        backtest_storage.init_schema(conn)
        row = backtest_storage.select_by_id(conn, job_id)
        if row is None:
            return JSONResponse(
                status_code=404,
                content=to_error(
                    "not_found", f"backtest job {job_id!r} does not exist"
                ),
            )

        try:
            payload = json.loads(row["result_json"])
        except (TypeError, ValueError):
            payload = {}

        try:
            symbols = json.loads(row["custom_symbols_json"])
        except (TypeError, ValueError):
            symbols = []
        if not isinstance(symbols, list):
            symbols = []

        if row["status"] == "completed":
            metrics_obj = (
                payload.get("metrics") if isinstance(payload, dict) else None
            )
            metrics = (
                _detail_metrics_from_result(metrics_obj)
                if isinstance(metrics_obj, dict)
                else None
            )
            equity_raw = (
                payload.get("equity_curve") if isinstance(payload, dict) else []
            )
            if not isinstance(equity_raw, list):
                equity_raw = []
            equity_curve = [
                EquityPoint(
                    date=str(p.get("date", "")),
                    equity=float(p.get("equity", 0.0)),
                )
                for p in equity_raw
                if isinstance(p, dict)
            ]
            drawdown = _derive_drawdown(
                [p.model_dump() for p in equity_curve]
            )
            trades_raw = (
                payload.get("trades") if isinstance(payload, dict) else []
            )
            if not isinstance(trades_raw, list):
                trades_raw = []
            trades = _pair_trades(
                [t for t in trades_raw if isinstance(t, dict)]
            )
            error_obj: dict[str, Any] | None = None
        else:
            metrics = None
            equity_curve = []
            drawdown = []
            trades = []
            err_blob = (
                payload.get("error") if isinstance(payload, dict) else None
            )
            if isinstance(err_blob, dict):
                code = str(err_blob.get("code") or "engine_error")
                message = str(err_blob.get("message") or "engine reported failure")
            else:
                code = "engine_error"
                message = "engine reported failure"
            error_obj = {"code": code, "message": message}

        detail = JobDetail(
            id=row["id"],
            strategy=row["strategy"],
            period_from=row["period_from"],
            period_to=row["period_to"],
            custom_symbols=[str(s) for s in symbols],
            initial_capital=row["initial_capital"],
            status=row["status"],
            elapsed_ms=row["elapsed_ms"],
            created_at=row["created_at"],
            metrics=metrics,
            equity_curve=equity_curve,
            drawdown=drawdown,
            trades=trades,
            error=error_obj,
        )
    except Exception as exc:  # noqa: BLE001
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)

    return JSONResponse(
        status_code=200, content=to_success(detail.model_dump(mode="json"))
    )
