"""`ohmystock score` typer group — Phase 2B scoring subcommands.

`watchlist` calls ``ohmystock.scoring.score_watchlist`` and renders the
envelope to stdout (CSV by default, JSON with --json). Validation/internal
errors print to stderr and exit 1.

Spec: openspec/changes/phase-2b-deferred-cli/specs/cli-and-config/spec.md
("`ohmystock score watchlist` 子命令" requirement).
"""

from __future__ import annotations

import json
import sys

import typer

from ohmystock.scoring import score_watchlist


score_app = typer.Typer(help="Phase 2B scoring 子命令")


_CSV_HEADER = "symbol,final_score,classification,risk_off_applied,tech,chip,fund,sent"


@score_app.command("watchlist", help="跑 Phase 2B 評分並依 final_score 由大到小列印")
def watchlist(
    asof: str = typer.Option(..., "--asof", help="評分日期，格式 YYYY-MM-DD"),
    symbols: str = typer.Option(
        ...,
        "--symbols",
        help="逗號分隔的台股代號（例如 2330,2317,1101）",
    ),
    top_n: int | None = typer.Option(
        None,
        "--top-n",
        help="排序後截斷至前 N 筆；不指定則全部輸出",
    ),
    as_json: bool = typer.Option(
        False,
        "--json/--no-json",
        help="--json 時 stdout 為原始 envelope JSON；--no-json (預設) 為 CSV",
    ),
) -> None:
    candidates = [s.strip() for s in symbols.split(",") if s.strip()]
    env = score_watchlist(asof_date=asof, candidates=candidates, top_n=top_n)

    if not env["ok"]:
        err = env["error"] or {}
        code = err.get("code", "UNKNOWN")
        message = err.get("message", "")
        typer.echo(f"error: {code}: {message}", err=True)
        raise typer.Exit(1)

    if as_json:
        sys.stdout.write(json.dumps(env, ensure_ascii=False) + "\n")
        return

    rows = list(env["data"]["candidates"])
    rows.sort(key=lambda c: (-c["final_score"], c["symbol"]))
    if top_n is not None:
        rows = rows[:top_n]

    sys.stdout.write(_CSV_HEADER + "\n")
    for c in rows:
        sys.stdout.write(
            ",".join(
                [
                    c["symbol"],
                    repr(c["final_score"]),
                    c["classification"],
                    "true" if c["risk_off_applied"] else "false",
                    repr(c["tech_subtotal"]),
                    repr(c["chip_subtotal"]),
                    repr(c["fund_subtotal"]),
                    repr(c["sent_subtotal"]),
                ]
            )
            + "\n"
        )
