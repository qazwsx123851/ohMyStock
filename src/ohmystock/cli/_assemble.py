"""``oms assemble-entry-input`` — emit a v3.1 EntryDecisionInput JSON for a symbol.

Used both by humans for sanity-checking and by tests for fixture capture.
Live providers (``Live{Market,Portfolio,Journal}SnapshotProvider``) read
from the cached SQLite DB; the five candidate technical metrics are
derived via ``live_candidate_snapshot``. Tests inject fakes via the
``_run_assemble`` helper.

Specs:
- openspec/changes/phase-2b-swarm-input-assembler/specs/swarm-input-assembler/spec.md
- openspec/changes/live-providers/specs/live-providers/spec.md
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
    LiveProviderError,
    MarketSnapshotProvider,
    PortfolioSnapshotProvider,
    build_entry_decision_input,
    discover_available_skills,
    discover_available_tools,
    live_candidate_snapshot,
    load_rules_digest,
)


_ERROR_CODE_EXIT_CODES = {
    "DATA_UNAVAILABLE": 4,
    "STALE_DATA": 5,
    "UPSTREAM_ERROR": 6,
    "AUTH_FAILED": 7,
}


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
    current_price: float | None = None,
    ema20_distance_pct: float | None = None,
    atr_14_pct: float | None = None,
    distance_from_52w_high_pct: float | None = None,
    distance_from_52w_low_pct: float | None = None,
) -> EntryDecisionInput:
    """Internal assembler runner exposed for tests.

    Parameters mirror ``build_entry_decision_input``. When providers or
    technical metrics are omitted, the live providers + the
    ``live_candidate_snapshot`` helper supply real values. Tests inject
    fakes via these kwargs.

    Side-effects: emits ``warning:`` lines to stderr (does not change
    exit code) for ``未分類`` open positions and unwired Risk-Off signals.
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

    if any(
        v is None
        for v in (
            current_price,
            ema20_distance_pct,
            atr_14_pct,
            distance_from_52w_high_pct,
            distance_from_52w_low_pct,
        )
    ):
        snap = live_candidate_snapshot(symbol, asof)
        if current_price is None:
            current_price = snap.current_price
        if ema20_distance_pct is None:
            ema20_distance_pct = snap.ema20_distance_pct
        if atr_14_pct is None:
            atr_14_pct = snap.atr_14_pct
        if distance_from_52w_high_pct is None:
            distance_from_52w_high_pct = snap.distance_from_52w_high_pct
        if distance_from_52w_low_pct is None:
            distance_from_52w_low_pct = snap.distance_from_52w_low_pct

    resolved_market_provider = market_provider or LiveMarketSnapshotProvider(
        asof=asof
    )
    resolved_portfolio_provider = (
        portfolio_provider or LivePortfolioSnapshotProvider(asof=asof)
    )
    journal = journal_provider or LiveJournalStatsProvider(asof=asof)

    market = resolved_market_provider.get()
    portfolio = resolved_portfolio_provider.get()

    diagnostics = getattr(resolved_market_provider, "last_diagnostics", {}) or {}
    if not bool(market.risk_off) and any(
        v == "unknown" for v in diagnostics.values()
    ):
        unknown_signals = sorted(
            k for k, v in diagnostics.items() if v == "unknown"
        )
        sys.stderr.write(
            "warning: risk_off=False with unwired signals: "
            + ", ".join(unknown_signals)
            + "\n"
        )
    unclassified = [p for p in portfolio.positions if p.sector == "未分類"]
    if unclassified:
        symbols = sorted({p.symbol for p in unclassified})
        sys.stderr.write(
            "warning: open position(s) with sector=未分類: "
            + ", ".join(symbols)
            + "\n"
        )

    return build_entry_decision_input(
        candidate=candidate,
        candidate_name=candidate_name or candidate.symbol,
        candidate_sector=candidate_sector,
        current_price=float(current_price),
        ema20_distance_pct=float(ema20_distance_pct),
        atr_14_pct=float(atr_14_pct),
        distance_from_52w_high_pct=float(distance_from_52w_high_pct),
        distance_from_52w_low_pct=float(distance_from_52w_low_pct),
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
    except LiveProviderError as exc:
        exit_code = _ERROR_CODE_EXIT_CODES.get(exc.code, 1)
        typer.echo(f"error: {exc.code}: {exc.message}", err=True)
        raise typer.Exit(exit_code)
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
