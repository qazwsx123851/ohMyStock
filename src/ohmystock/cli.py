"""ohMyStock CLI — typer app with five stub subcommands.

Each subcommand is a placeholder that prints "not implemented" and exits 1.
Real logic lands in later changes (fastapi-bootstrap, core-agent-and-base-skills, etc.).
"""

from __future__ import annotations

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


@app.command(help="跑 Phase 5 月度復盤五節點 swarm（後續 change 實作）")
def review() -> None:
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


def main() -> None:
    app()
