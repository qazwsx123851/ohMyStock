"""ohMyStock CLI — typer app with eight subcommands.

Five stubs (run/backtest/review/propose/screen) print "not implemented" and
exit 1 — real logic lands in later changes. ``api`` launches uvicorn against
``ohmystock.api.app:create_app``. ``smoke-test`` verifies FinMind / Shioaji /
Anthropic connectivity for Phase 0d acceptance. ``score`` is a typer group
backed by ``_score.score_app``; ``score watchlist`` runs Phase 2B scoring.
"""

from __future__ import annotations

from datetime import date, timedelta

import typer

app = typer.Typer(help="ohMyStock — 台股 AI 交易代理人 CLI")


@app.command(
    help="跑一輪完整流程：訊號偵測 → 進場決策 → Confirm Gate → Trade Journal（後續 change 實作）"
)
def run() -> None:
    typer.echo("not implemented")
    raise typer.Exit(1)


@app.command(help="對指定策略跑歷史回測（後續 change 實作）")
def backtest() -> None:
    typer.echo("not implemented")
    raise typer.Exit(1)


@app.command(help="生成策略改動提案，走 WFA 樣本外驗證（後續 change 實作）")
def propose() -> None:
    typer.echo("not implemented")
    raise typer.Exit(1)


@app.command(help="跑 Screener 篩選候選標的（後續 change 實作）")
def screen() -> None:
    typer.echo("not implemented")
    raise typer.Exit(1)


@app.command(help="啟動 FastAPI backend（uvicorn + factory mode；本機 dev 預設 reload）")
def api(
    host: str = typer.Option(
        "127.0.0.1",
        help="監聽主機；預設 127.0.0.1 僅本機可達，供 Cloudflare Tunnel 暴露給 admin",
    ),
    port: int = typer.Option(8000, help="監聽 port；預設 8000"),
    reload: bool = typer.Option(
        True,
        "--reload/--no-reload",
        help="開發模式自動 reload；測試 / smoke test 請用 --no-reload",
    ),
) -> None:
    import uvicorn

    uvicorn.run(
        "ohmystock.api.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )


@app.command(
    "smoke-test",
    help=(
        "驗證三方連線：依序檢查 finmind / shioaji / anthropic，"
        "每項獨立 try/except，全跑完彙總；任一 FAIL exit 1，全 PASS exit 0"
    ),
)
def smoke_test() -> None:
    results: list[tuple[str, bool, str]] = []

    try:
        from ohmystock.data.finmind_client import FinMindClient

        end = date.today()
        start = end - timedelta(days=10)
        rows = FinMindClient().get_taiwan_stock_price(
            "2330", start.isoformat(), end.isoformat()
        )
        results.append(("finmind", True, f"{len(rows)} rows"))
    except Exception as exc:
        results.append(("finmind", False, str(exc)))

    try:
        from ohmystock.paper.shioaji_client import ShioajiPaperClient

        sj_client = ShioajiPaperClient()
        sj_client.login()
        snap = sj_client.get_snapshot("2330")
        results.append(("shioaji", True, f"close={snap.get('close')}"))
    except Exception as exc:
        results.append(("shioaji", False, str(exc)))

    try:
        from anthropic import Anthropic

        from ohmystock.config import Settings

        settings = Settings()
        anthro = Anthropic(api_key=settings.anthropic_api_key)
        msg = anthro.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
        results.append(("anthropic", True, f"model={msg.model}"))
    except Exception as exc:
        results.append(("anthropic", False, str(exc)))

    any_fail = False
    for name, ok, detail in results:
        if ok:
            typer.echo(f"[PASS] {name}: {detail}")
        else:
            any_fail = True
            typer.echo(f"[FAIL] {name}: {detail}")

    if any_fail:
        raise typer.Exit(1)


from ohmystock.cli._score import score_app  # noqa: E402

app.add_typer(score_app, name="score", help="Phase 2B scoring 子命令")


from ohmystock.cli._assemble import assemble_entry_input  # noqa: E402

app.command(
    "assemble-entry-input",
    help="組裝 Phase 2B 候選 + 市況快照 → entry_decision_team v3.1 LLM 輸入 JSON",
)(assemble_entry_input)


from ohmystock.cli._decide import decide  # noqa: E402

app.command(
    "decide",
    help=(
        "Phase 3 PM Decider — assemble candidate, call Claude Opus 4.7, "
        "validate §2.1, write kind=entry (pending_confirm) or kind=reject "
        "(reject_layer=llm). WARNING: writes pending_confirm entries; "
        "broker submission is not yet wired (Confirm Gate is Phase 3.5)."
    ),
)(decide)


from ohmystock.cli._confirm import confirm_command  # noqa: E402

app.command(
    "confirm",
    help=(
        "Confirm Gate v0 (human-only) — drive pending_confirm entries to "
        "confirmed/rejected/expired. Modes: --list, <decision_id> [--reject], "
        "--sweep-expired. Auto mode requires the Phase 3.5 breaker; this "
        "command always runs human-mode and warns if OHMYSTOCK_AUTO_EXECUTE=true."
    ),
)(confirm_command)


from ohmystock.cli._evaluate_exits import evaluate_exits  # noqa: E402

app.command(
    "evaluate-exits",
    help=(
        "Exit Engine v0 — daily, full-position evaluator. Scans confirmed "
        "entries, evaluates v0 conditions (hit_stop_loss / hit_t1 / time_stop) "
        "against today's close, writes kind=exit rows and flips entry "
        "decision_status to closed for triggered positions."
    ),
)(evaluate_exits)


from ohmystock.cli._review import review_cmd  # noqa: E402

app.command(
    "review",
    help=(
        "Phase 5 post-trade review — sequential 5-node pipeline "
        "(data_loader → attributor → aggregator → critic → proposer). "
        "Writes reviews/<period>/ + proposals/<id>.md per spec. "
        "Use --dry-run to estimate token cost."
    ),
)(review_cmd)


def main() -> None:
    app()
