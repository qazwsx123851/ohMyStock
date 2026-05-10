"""``ohmystock review`` Typer command.

Spec: openspec/changes/phase5-review-mvp/specs/post-trade-review-cli/spec.md
"""

from __future__ import annotations

import json
import re
import sqlite3
import traceback
from collections.abc import Callable
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

import typer

from ohmystock.config import Settings
from ohmystock.data import cache as data_cache
from ohmystock.review import (
    MarketDataLoader,
    ReviewAlreadyExistsError,
    ReviewLLM,
    ReviewResult,
    run_review,
)


_LLM_FACTORY_OVERRIDE: Optional[Callable[[str], ReviewLLM]] = None
_MARKET_DATA_OVERRIDE: Optional[MarketDataLoader] = None


_SK_ANT_RE = re.compile(r"sk-ant-[A-Za-z0-9_\-]+")


class _CachedMarketData:
    """Default ``MarketDataLoader`` reading cached daily bars only."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def select_bars(
        self, symbol: str, exit_date: date, days: int
    ) -> list[float]:
        start = (exit_date + timedelta(days=1)).isoformat()
        end = (exit_date + timedelta(days=days * 2 + 7)).isoformat()
        bars = data_cache.select_bars(self.conn, symbol, start, end)
        closes = [float(b["c"]) for b in bars]
        return closes[:days]


def review_cmd(
    period_from: str = typer.Option(
        ..., "--from", help="期間開始日(ISO,YYYY-MM-DD)",
    ),
    period_to: str = typer.Option(
        ..., "--to", help="期間結束日(ISO,YYYY-MM-DD)",
    ),
    out_dir: Path = typer.Option(
        Path("reviews"), "--out-dir", help="復盤輸出資料夾(預設 reviews/)",
    ),
    proposals_dir: Path = typer.Option(
        Path("proposals"), "--proposals-dir", help="提案輸出資料夾(預設 proposals/)",
    ),
    limit_trades: Optional[int] = typer.Option(
        None, "--limit-trades", help="把 trades 截到前 N 筆(debug 用,須 >= 1)",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="跑全 pipeline 但不寫任何檔(印 token/cost 估算)",
    ),
    force: bool = typer.Option(
        False, "--force", help="覆寫已存在的 reviews/<period>/(不覆寫 proposals/)",
    ),
    json_out: bool = typer.Option(
        False, "--json", help="以 JSON 格式印 summary 到 stdout",
    ),
) -> None:
    """Phase 5 月度復盤 — sequential 5-node pipeline."""

    pf = _parse_iso_date_or_exit(period_from, "--from")
    pt = _parse_iso_date_or_exit(period_to, "--to")
    if pf > pt:
        typer.echo("period_from must be <= period_to", err=True)
        raise typer.Exit(code=2)

    if limit_trades is not None and limit_trades < 1:
        typer.echo("--limit-trades must be >= 1", err=True)
        raise typer.Exit(code=2)

    out_dir.mkdir(parents=True, exist_ok=True)
    proposals_dir.mkdir(parents=True, exist_ok=True)

    settings = Settings()
    db_path = Path(settings.ohmystock_db_path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    cheatsheet_path = Path("docs/workflow-cheatsheet.md")

    conn = sqlite3.connect(str(db_path))
    try:
        market_data = _MARKET_DATA_OVERRIDE or _CachedMarketData(conn)
        try:
            result = run_review(
                pf,
                pt,
                conn,
                out_dir=out_dir,
                proposals_dir=proposals_dir,
                market_data_loader=market_data,
                cheatsheet_path=cheatsheet_path,
                llm_factory=_LLM_FACTORY_OVERRIDE,
                force=force,
                limit_trades=limit_trades,
                dry_run=dry_run,
            )
        except ReviewAlreadyExistsError as exc:
            typer.echo(
                f"review already exists; pass --force to overwrite ({exc})",
                err=True,
            )
            raise typer.Exit(code=2) from exc
        except Exception as exc:  # noqa: BLE001
            _print_redacted_traceback(exc, settings)
            raise typer.Exit(code=3) from exc
    finally:
        conn.close()

    if json_out:
        typer.echo(json.dumps(_summary_dict(result), ensure_ascii=False))
    else:
        _print_human_summary(result, dry_run=dry_run)


def _parse_iso_date_or_exit(value: str, flag: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        typer.echo(
            f"{flag} must be YYYY-MM-DD ISO date, got {value!r}",
            err=True,
        )
        raise typer.Exit(code=2) from exc


def _summary_dict(result: ReviewResult) -> dict[str, Any]:
    payload = asdict(result)
    payload["period"] = {
        "from": result.period_from.isoformat(),
        "to": result.period_to.isoformat(),
    }
    payload["period_from"] = result.period_from.isoformat()
    payload["period_to"] = result.period_to.isoformat()
    return payload


def _print_human_summary(result: ReviewResult, *, dry_run: bool) -> None:
    label = "DRY RUN" if dry_run else "OK"
    typer.echo(f"[{label}] review_id={result.review_id}")
    typer.echo(
        f"  period   : {result.period_from.isoformat()} ~ "
        f"{result.period_to.isoformat()}"
    )
    typer.echo(f"  trades   : {result.trade_count}")
    typer.echo(f"  proposals: {result.proposals_created}")
    typer.echo(f"  input tokens : {result.total_input_tokens}")
    typer.echo(f"  output tokens: {result.total_output_tokens}")
    typer.echo(f"  estimated cost (USD): {result.total_cost_usd:.6f}")
    typer.echo(f"  out_dir       : {result.out_dir}")
    typer.echo(f"  proposals_dir : {result.proposals_dir}")


def _print_redacted_traceback(exc: BaseException, settings: Settings) -> None:
    tb = traceback.format_exception(exc)
    raw = "".join(tb)
    redacted = _SK_ANT_RE.sub("<redacted>", raw)
    if settings.anthropic_api_key:
        redacted = redacted.replace(settings.anthropic_api_key, "<redacted>")
    typer.echo(redacted, err=True)
