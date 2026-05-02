"""``ohmystock confirm`` — Confirm Gate v0 CLI driver.

Wraps ``ohmystock.safety.confirm_gate``: list pending entries, confirm a
specific decision (paper broker fill), reject (human), or sweep expired rows.

Spec: openspec/changes/confirm-gate-v0/specs/cli-and-config/spec.md

Exit codes (per spec table):
- 0 — confirm / list / sweep success
- 1 — reject success (semantic non-zero, mirrors ``decide`` exit 1)
- 2 — usage error / not_found / not_pending / payload_invalid
- 3 — broker_failed

Lifecycle warning: this gate writes ``confirmed`` / ``rejected`` / ``expired``
into the kind=entry payload. Auto-execute mode requires the Phase 3.5
breaker; this CLI always runs in human mode and emits a warning if
``OHMYSTOCK_AUTO_EXECUTE=true``.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path

import typer

from ohmystock.config import Settings
from ohmystock.journal.schema import init_schema
from ohmystock.paper import FakePaperBroker
from ohmystock.safety import (
    ConfirmGateError,
    confirm,
    list_pending,
    reject,
    sweep_expired,
    system_clock,
)


_AUTO_WARNING = (
    "warning: auto mode requires the Phase 3.5 breaker, "
    "falling back to human confirm"
)


def _open_journal_db(db_override: str | None, settings: Settings) -> sqlite3.Connection:
    raw = db_override or settings.ohmystock_db_path
    path = Path(raw).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    init_schema(conn)
    return conn


def _emit_auto_warning() -> None:
    if (os.getenv("OHMYSTOCK_AUTO_EXECUTE") or "").strip().lower() == "true":
        typer.echo(_AUTO_WARNING, err=True)


def _emit_json(payload: dict, exit_code: int) -> None:
    sys.stdout.write(
        json.dumps({**payload, "exit_code": exit_code}, ensure_ascii=False) + "\n"
    )


def confirm_command(
    decision_id: str | None = typer.Argument(
        None,
        help="決策 ID (dec_<...>); 帶此參數時 confirm 或 reject 該筆 pending_confirm entry",
    ),
    list_pending_flag: bool = typer.Option(
        False,
        "--list",
        help="列出所有 pending_confirm entry (含 age / TTL); 不接受 decision_id",
    ),
    sweep_expired_flag: bool = typer.Option(
        False,
        "--sweep-expired",
        help=(
            "Sweep 所有逾時 (>timeout-minutes) 的 pending_confirm entry，"
            "寫 kind=expire row 並翻 status=expired"
        ),
    ),
    reject_flag: bool = typer.Option(
        False,
        "--reject",
        help="人工 reject 模式 (需傳 decision_id)；寫 kind=reject reject_layer=human",
    ),
    reason: str = typer.Option(
        "human rejected via confirm gate",
        "--reason",
        help="--reject 時的 reject_reason 字串",
    ),
    user: str | None = typer.Option(
        None,
        "--user",
        help=(
            "寫入 human_confirmed_by / rejected_by 的帳號；"
            "預設讀 $USER 環境變數 (fallback 'unknown')"
        ),
    ),
    db: str | None = typer.Option(
        None,
        "--db",
        help="SQLite 路徑；預設讀 OHMYSTOCK_DB_PATH",
    ),
    timeout_minutes: int | None = typer.Option(
        None,
        "--timeout-minutes",
        help="--list / --sweep-expired 用的 TTL (分鐘); 預設讀 OHMYSTOCK_CONFIRM_TIMEOUT_MINUTES",
    ),
    default_capital_twd: int | None = typer.Option(
        None,
        "--default-capital-twd",
        help="confirm 計算 qty 用的資本 (TWD); 預設讀 OHMYSTOCK_DEFAULT_CAPITAL_TWD",
    ),
    json_out: bool = typer.Option(
        False,
        "--json/--no-json",
        help="JSON dump 輸出 (含 action / decision_id / payload / exit_code)",
    ),
) -> None:
    """Drive the Confirm Gate v0 — pending_confirm → confirmed/rejected/expired."""

    _emit_auto_warning()

    settings = Settings()
    effective_timeout = timeout_minutes or settings.ohmystock_confirm_timeout_minutes
    effective_capital = default_capital_twd or settings.ohmystock_default_capital_twd
    effective_user = user or os.getenv("USER", "unknown")

    # Mutual-exclusion check (only one mode at a time).
    mode_count = sum(
        [
            bool(list_pending_flag),
            bool(sweep_expired_flag),
            bool(decision_id),
        ]
    )
    if mode_count != 1:
        typer.echo(
            "usage: pass exactly one of <decision_id>, --list, or --sweep-expired "
            "(these flags are mutually exclusive)",
            err=True,
        )
        raise typer.Exit(2)

    if reject_flag and not decision_id:
        typer.echo("--reject requires a <decision_id> argument", err=True)
        raise typer.Exit(2)

    conn = _open_journal_db(db, settings)
    try:
        if list_pending_flag:
            _do_list(conn, effective_timeout, json_out=json_out)
            return
        if sweep_expired_flag:
            _do_sweep(conn, effective_timeout, json_out=json_out)
            return

        # decision_id-based action
        assert decision_id is not None  # guarded above
        if reject_flag:
            _do_reject(
                conn,
                decision_id=decision_id,
                reason=reason,
                user=effective_user,
                json_out=json_out,
            )
            return
        _do_confirm(
            conn,
            decision_id=decision_id,
            user=effective_user,
            default_capital_twd=effective_capital,
            json_out=json_out,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# action handlers
# ---------------------------------------------------------------------------


def _do_list(
    conn: sqlite3.Connection, timeout_minutes: int, *, json_out: bool
) -> None:
    rows = list_pending(conn, clock=system_clock, timeout_minutes=timeout_minutes)
    if json_out:
        _emit_json(
            {
                "action": "list",
                "pending": [asdict(r) for r in rows],
            },
            exit_code=0,
        )
        raise typer.Exit(0)

    if not rows:
        typer.echo("no pending_confirm entries")
        raise typer.Exit(0)

    typer.echo(
        f"{'decision_id':<40} {'symbol':<8} {'price':>10} {'sizing%':>8} "
        f"{'age(s)':>8} {'ttl(s)':>8}"
    )
    for r in rows:
        typer.echo(
            f"{r.decision_id:<40} {r.symbol:<8} {r.current_price:>10.2f} "
            f"{r.final_sizing_pct:>8.2f} {r.age_seconds:>8} {r.ttl_seconds:>8}"
        )
    raise typer.Exit(0)


def _do_sweep(
    conn: sqlite3.Connection, timeout_minutes: int, *, json_out: bool
) -> None:
    swept = sweep_expired(
        conn, timeout_minutes=timeout_minutes, clock=system_clock
    )
    if json_out:
        _emit_json(
            {"action": "sweep_expired", "expired": list(swept)},
            exit_code=0,
        )
        raise typer.Exit(0)

    typer.echo(f"{len(swept)} expired")
    for d in swept:
        typer.echo(d)
    raise typer.Exit(0)


def _do_confirm(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    user: str,
    default_capital_twd: int,
    json_out: bool,
) -> None:
    broker = FakePaperBroker(clock=system_clock)
    try:
        result = confirm(
            conn,
            decision_id=decision_id,
            broker=broker,
            default_capital_twd=default_capital_twd,
            user=user,
            clock=system_clock,
        )
    except ConfirmGateError as exc:
        typer.echo(f"{exc.code}: {exc}", err=True)
        if exc.code == "broker_failed":
            raise typer.Exit(3)
        raise typer.Exit(2)

    if json_out:
        _emit_json(
            {
                "action": "confirm",
                "decision_id": result.decision_id,
                "fill": asdict(result.fill),
                "qty": result.qty,
                "status": "confirmed",
            },
            exit_code=0,
        )
        raise typer.Exit(0)

    typer.echo(f"decision_id: {result.decision_id}")
    typer.echo(f"symbol: {result.fill.symbol}")
    typer.echo(f"qty: {result.qty}")
    typer.echo(f"fill_price: {result.fill.fill_price}")
    typer.echo(f"fill_ts: {result.fill.fill_ts}")
    typer.echo("status: confirmed")
    raise typer.Exit(0)


def _do_reject(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    reason: str,
    user: str,
    json_out: bool,
) -> None:
    try:
        result = reject(
            conn,
            decision_id=decision_id,
            reason=reason,
            user=user,
            clock=system_clock,
        )
    except ConfirmGateError as exc:
        typer.echo(f"{exc.code}: {exc}", err=True)
        raise typer.Exit(2)
    except ValueError as exc:
        typer.echo(f"usage: {exc}", err=True)
        raise typer.Exit(2)

    if json_out:
        _emit_json(
            {
                "action": "reject",
                "decision_id": result.decision_id,
                "reject_reason": reason,
                "rejected_by": user,
                "status": "rejected",
            },
            exit_code=1,
        )
        raise typer.Exit(1)

    typer.echo(f"decision_id: {result.decision_id}")
    typer.echo(f"reject_reason: {reason}")
    typer.echo(f"rejected_by: {user}")
    typer.echo("status: rejected")
    raise typer.Exit(1)
