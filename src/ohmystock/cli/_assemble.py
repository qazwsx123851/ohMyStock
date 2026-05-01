"""``oms assemble-entry-input`` — emit a v3.1 EntryDecisionInput JSON for a symbol.

Used both by humans for sanity-checking and by tests for fixture capture.
The live ``MarketSnapshot`` / ``PortfolioSnapshot`` / ``JournalStats``
providers raise ``NotImplementedError`` until the underlying tools are
wired (Phase 0d/2 work). Tests inject fakes via the ``_run_assemble``
helper.

Spec: openspec/changes/phase-2b-swarm-input-assembler/specs/swarm-input-assembler/spec.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable

import typer

from ohmystock.scoring import (
    Phase2BCandidate,
    iter_qualified_candidates,
    score_watchlist,
)
from ohmystock.swarm import (
    AssemblerInputError,
    EntryDecisionInput,
    JournalStatsProvider,
    LiveJournalStatsProvider,
    LiveMarketSnapshotProvider,
    LivePortfolioSnapshotProvider,
    MarketSnapshotProvider,
    PortfolioSnapshotProvider,
    build_entry_decision_input,
    discover_available_skills,
    discover_available_tools,
    load_rules_digest,
)


def _candidates_via_score_watchlist(
    asof: str, symbol: str
) -> list[Phase2BCandidate]:
    env = score_watchlist(asof_date=asof, candidates=[symbol])
    if not env.get("ok"):
        err = env.get("error") or {}
        raise RuntimeError(
            f"score_watchlist failed: {err.get('code')}: {err.get('message')}"
        )
    return [Phase2BCandidate(**c) for c in env["data"]["candidates"]]


def _run_assemble(
    *,
    symbol: str,
    asof: str,
    trigger_at: str,
    candidates: Iterable[Phase2BCandidate] | None = None,
    market_provider: MarketSnapshotProvider | None = None,
    portfolio_provider: PortfolioSnapshotProvider | None = None,
    journal_provider: JournalStatsProvider | None = None,
    candidate_name: str = "",
    candidate_sector: str = "",
    current_price: float = 0.0,
    ema20_distance_pct: float = 0.0,
    atr_14_pct: float = 0.0,
    distance_from_52w_high_pct: float = 0.0,
    distance_from_52w_low_pct: float = 0.0,
) -> EntryDecisionInput:
    """Internal assembler runner exposed for tests.

    Parameters mirror ``build_entry_decision_input``. When providers are
    omitted, the live (NotImplementedError) stubs run. Tests inject
    fakes here.
    """
    cand_list = (
        list(candidates)
        if candidates is not None
        else _candidates_via_score_watchlist(asof, symbol)
    )
    qualified = list(iter_qualified_candidates(asof, candidates=cand_list))
    matching = [c for c in qualified if c.symbol == symbol]
    if not matching:
        raise AssemblerInputError(
            f"no qualifying Phase 2B candidate for symbol={symbol!r} on {asof}"
        )
    candidate = matching[0]

    market = (market_provider or LiveMarketSnapshotProvider()).get()
    portfolio = (portfolio_provider or LivePortfolioSnapshotProvider()).get()
    journal = journal_provider or LiveJournalStatsProvider()

    return build_entry_decision_input(
        candidate=candidate,
        candidate_name=candidate_name or candidate.symbol,
        candidate_sector=candidate_sector,
        current_price=current_price,
        ema20_distance_pct=ema20_distance_pct,
        atr_14_pct=atr_14_pct,
        distance_from_52w_high_pct=distance_from_52w_high_pct,
        distance_from_52w_low_pct=distance_from_52w_low_pct,
        market=market,
        portfolio=portfolio,
        journal_stats=journal,
        rules_digest=load_rules_digest(),
        available_tools=discover_available_tools(),
        available_skills=discover_available_skills(),
        trigger_at=trigger_at,
    )


def assemble_entry_input(
    symbol: str = typer.Argument(..., help="台股代號（例如 2330）"),
    asof: str = typer.Option(..., "--asof", help="評分日期 YYYY-MM-DD"),
    trigger_at: str = typer.Option(
        ...,
        "--trigger-at",
        help="觸發時間，ISO-8601 含時區（例如 2026-04-30T14:30:00+08:00）",
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        help="輸出 JSON 檔案路徑；未指定則輸出至 stdout",
    ),
) -> None:
    """Build the v3.1 EntryDecisionInput for SYMBOL and emit JSON."""
    try:
        result = _run_assemble(symbol=symbol, asof=asof, trigger_at=trigger_at)
    except AssemblerInputError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2)
    except NotImplementedError as exc:
        typer.echo(f"error: live provider not wired: {exc}", err=True)
        raise typer.Exit(3)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)

    payload = json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)
    if out is not None:
        out.write_text(payload + "\n", encoding="utf-8")
    else:
        sys.stdout.write(payload + "\n")
