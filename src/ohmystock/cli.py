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


def main() -> None:
    app()
