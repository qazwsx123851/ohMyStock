"""``ohmystock validate-proposal`` — Typer handler for the WFA validation gate.

Spec: openspec/changes/wfa-validation-engine/specs/wfa-validation-engine/spec.md
(Requirement "CLI validate-proposal subcommand")

Resolves a proposal slug against ``Settings().proposals_dir`` (probing the 4
sub-locations), enforces the ``status == validating`` precondition, parses
``--param key=value`` pairs via ``ast.literal_eval``, builds a synthetic
``market_data_loader`` from ``get_connection() + select_bars``, and delegates
to ``run_validation``. Exit codes follow design D6 (0=pass, 1=fail,
2=input-error, dry-run always 0).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Callable

import typer

from ohmystock.api.db import get_connection
from ohmystock.config import Settings
from ohmystock.data.cache import select_bars
from ohmystock.data.sources.base import BarRow
from ohmystock.proposal import ProposalParseError, parse_proposal
from ohmystock.validation import WfaValidationError, run_validation


_SINK_SUBDIRS: tuple[str, ...] = ("", "PENDING_REVIEW", "merged", "rejected")


# Test override seam (mirrors ``api.routes.proposals._PROPOSALS_ROOT_FACTORY``).
# Pattern: ``monkeypatch.setattr(cli._validate_proposal,
# "_PROPOSALS_ROOT_FACTORY", lambda: tmp_path / "proposals")``.
_PROPOSALS_ROOT_FACTORY: Callable[[], Path] = lambda: Settings().proposals_dir


# Test override seam for the market data loader. CLI default builds the
# loader from ``get_connection() + select_bars``; tests inject a synthetic
# loader so they don't need a SQLite cache or fixture bars on disk.
_MARKET_DATA_LOADER_FACTORY: Callable[
    [], Callable[[str, str, str], list[BarRow]]
] = lambda: (lambda sym, s, e: select_bars(get_connection(), sym, s, e))


def _resolve_proposal_path(slug: str) -> Path | None:
    """Probe the 4 proposal sub-locations for ``<slug>.md``; return first hit."""
    root = _PROPOSALS_ROOT_FACTORY()
    filename = f"{slug}.md"
    for sub in _SINK_SUBDIRS:
        candidate = root / sub / filename if sub else root / filename
        if candidate.is_file():
            return candidate
    return None


def _parse_period(raw: str) -> dict[str, str]:
    """Parse ``from=YYYY-MM-DD,to=YYYY-MM-DD`` into ``{"from", "to"}`` dict."""
    parts = [p.strip() for p in raw.split(",")]
    out: dict[str, str] = {}
    for part in parts:
        if not part:
            continue
        key, sep, value = part.partition("=")
        if sep != "=":
            raise ValueError(f"period segment {part!r} must be key=value")
        out[key.strip()] = value.strip()
    if "from" not in out or "to" not in out:
        raise ValueError(
            f"period must contain both from= and to=, got {raw!r}"
        )
    return {"from": out["from"], "to": out["to"]}


def _parse_param_pairs(pairs: list[str]) -> dict[str, Any]:
    """Parse ``["key=value", ...]`` into a dict via ``ast.literal_eval`` on values."""
    out: dict[str, Any] = {}
    for raw in pairs:
        if not raw:
            continue
        key, sep, value = raw.partition("=")
        if sep != "=" or not key.strip():
            raise ValueError(f"unparseable_param: {raw!r} (need key=value)")
        key_stripped = key.strip()
        value_stripped = value.strip()
        try:
            out[key_stripped] = ast.literal_eval(value_stripped)
        except (ValueError, SyntaxError) as exc:
            raise ValueError(
                f"unparseable_param: {key_stripped}={value_stripped} ({exc})"
            ) from exc
    return out


def validate_proposal(
    slug: str = typer.Argument(..., help="proposal slug — filename stem"),
    strategy: str = typer.Option(
        ...,
        "--strategy",
        help="registered strategy name (e.g. sma_cross)",
    ),
    period: str = typer.Option(
        ...,
        "--period",
        help="from=YYYY-MM-DD,to=YYYY-MM-DD",
    ),
    param: list[str] = typer.Option(
        None,
        "--param",
        help="key=value override (repeatable; value parsed via ast.literal_eval)",
    ),
    wfa_windows: int = typer.Option(
        5, "--wfa-windows", help="number of disjoint windows (default 5)"
    ),
    in_sample_ratio: float = typer.Option(
        0.7,
        "--in-sample-ratio",
        help="IS fraction of each chunk (default 0.7)",
    ),
    universe: str = typer.Option(
        "2330,0050,2317",
        "--universe",
        help="comma-separated symbols (default TWSE staples)",
    ),
    initial_capital: int = typer.Option(
        None,
        "--initial-capital",
        help="starting capital (default Settings().starting_equity_twd)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="compute verdict without writing report or transitioning state",
    ),
) -> None:
    """Run walk-forward validation against a ``validating`` proposal."""
    try:
        period_dict = _parse_period(period)
    except ValueError as exc:
        typer.echo(f"invalid_period: {exc}")
        raise typer.Exit(2)

    proposal_path = _resolve_proposal_path(slug)
    if proposal_path is None:
        typer.echo(f"proposal not found: {slug}")
        raise typer.Exit(2)

    try:
        text = proposal_path.read_text(encoding="utf-8")
    except OSError as exc:
        typer.echo(f"proposal_read_failed: {exc}")
        raise typer.Exit(2)

    if not text.startswith("---"):
        typer.echo(f"malformed_proposal: {slug}.md missing frontmatter")
        raise typer.Exit(2)

    fm: dict[str, str] = {}
    in_fm = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "---":
            if in_fm:
                break
            in_fm = True
            continue
        if not in_fm:
            continue
        if not stripped:
            continue
        key, sep, value = stripped.partition(":")
        if sep != ":":
            continue
        fm[key.strip()] = value.strip()
    current_status = fm.get("status", "")
    if current_status != "validating":
        typer.echo(
            f"proposal status must be 'validating', got '{current_status}'"
        )
        raise typer.Exit(2)

    try:
        parse_proposal(proposal_path)
    except ProposalParseError as exc:
        typer.echo(f"malformed_proposal: {exc}")
        raise typer.Exit(2)

    try:
        param_overrides = _parse_param_pairs(list(param or []))
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2)

    from ohmystock.backtest.strategy.registry import available_strategies

    registered = {entry["name"] for entry in available_strategies()}
    if strategy not in registered:
        typer.echo(f"unknown_strategy: {strategy}")
        raise typer.Exit(2)

    universe_list = [s.strip() for s in universe.split(",") if s.strip()]
    if not universe_list:
        typer.echo("invalid_universe: --universe must list at least one symbol")
        raise typer.Exit(2)

    if initial_capital is None:
        initial_capital = Settings().starting_equity_twd

    market_data_loader = _MARKET_DATA_LOADER_FACTORY()

    try:
        report = run_validation(
            proposal_path,
            strategy_name=strategy,
            period=period_dict,
            param_overrides=param_overrides,
            universe=universe_list,
            wfa_windows=wfa_windows,
            in_sample_ratio=in_sample_ratio,
            initial_capital=initial_capital,
            market_data_loader=market_data_loader,
            dry_run=dry_run,
        )
    except WfaValidationError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2)
    except TypeError as exc:
        typer.echo(f"unknown_param: {exc}")
        raise typer.Exit(2)

    sharpe_delta_pct = report.deltas["sharpe"] * 100.0
    mdd_delta_pct = report.deltas["max_drawdown"] * 100.0
    summary = (
        f"verdict={report.verdict} slug={slug} "
        f"sharpe_delta={sharpe_delta_pct:+.2f}% "
        f"mdd_delta={mdd_delta_pct:+.2f}%"
    )
    if dry_run:
        summary += " dry_run=true"
    typer.echo(summary)
    if report.failures:
        for failure in report.failures:
            typer.echo(f"  - {failure}")

    if dry_run:
        raise typer.Exit(0)
    if report.verdict == "pass":
        raise typer.Exit(0)
    raise typer.Exit(1)
