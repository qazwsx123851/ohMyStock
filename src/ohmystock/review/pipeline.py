"""Phase 5 pipeline runner — sequential 5-node post-trade review.

Spec: openspec/changes/phase5-review-mvp/specs/post-trade-review-pipeline/spec.md
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from anthropic import Anthropic

from ohmystock.config import Settings
from ohmystock.review.index import upsert_index_entry
from ohmystock.review.llm_client import AnthropicReviewLLM, ReviewLLM
from ohmystock.review.models import (
    DataLoaderOutput,
    IndexEntry,
    MetricsOutput,
    Period,
)
from ohmystock.review.nodes.aggregator import run_aggregator
from ohmystock.review.nodes.attributor import run_attributor
from ohmystock.review.nodes.critic import run_critic
from ohmystock.review.nodes.data_loader import MarketDataLoader, run_data_loader
from ohmystock.review.nodes.proposer import ProposerResult, run_proposer


_TPE = timezone(timedelta(hours=8))
ReviewKind = Literal["manual"]


class ReviewAlreadyExistsError(Exception):
    """Raised when ``out_dir/<review_id>/`` exists and ``force=False``."""


@dataclass(frozen=True)
class ReviewResult:
    review_id: str
    period_from: date
    period_to: date
    trade_count: int
    proposals_created: int
    proposals_files: list[str]
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    out_dir: str
    proposals_dir: str
    dry_run: bool


@dataclass
class _Files:
    review_dir: Path
    data_json: Path
    attribution_json: Path
    metrics_json: Path
    critique_md: Path
    report_md: Path
    proposals_created_md: Path

    @classmethod
    def for_review(cls, out_dir: Path, review_id: str) -> "_Files":
        review_dir = out_dir / review_id
        return cls(
            review_dir=review_dir,
            data_json=review_dir / "data.json",
            attribution_json=review_dir / "attribution.json",
            metrics_json=review_dir / "metrics.json",
            critique_md=review_dir / "critique.md",
            report_md=review_dir / "report.md",
            proposals_created_md=review_dir / "proposals_created.md",
        )


def run_review(
    period_from: date,
    period_to: date,
    db_conn: sqlite3.Connection,
    *,
    out_dir: Path,
    proposals_dir: Path,
    market_data_loader: MarketDataLoader,
    cheatsheet_path: Path,
    llm_factory: Callable[[str], ReviewLLM] | None = None,
    kind: ReviewKind = "manual",
    force: bool = False,
    limit_trades: int | None = None,
    dry_run: bool = False,
    now: datetime | None = None,
) -> ReviewResult:
    """Run the 5-node sequential pipeline and return a summary."""

    if period_from > period_to:
        raise ValueError(
            f"period_from must be <= period_to, got {period_from} > {period_to}"
        )

    review_id = f"manual-{period_from.isoformat()}-to-{period_to.isoformat()}"
    files = _Files.for_review(out_dir, review_id)

    if not dry_run and not force and files.review_dir.exists():
        raise ReviewAlreadyExistsError(
            f"review folder already exists at {files.review_dir} — pass "
            f"force=True to overwrite"
        )

    if not dry_run:
        files.review_dir.mkdir(parents=True, exist_ok=True)
        proposals_dir.mkdir(parents=True, exist_ok=True)

    factory = llm_factory or _default_llm_factory()
    timestamp = now or datetime.now(_TPE)

    data_output = run_data_loader(
        period_from,
        period_to,
        db_conn,
        market_data_loader,
        limit_trades=limit_trades,
    )
    if not dry_run:
        _write_json(files.data_json, data_output.model_dump(mode="json", by_alias=True))

    attributor_llm = factory("attributor")
    attribution_output = run_attributor(
        data_output,
        llm=attributor_llm,
        db_conn=db_conn,
        review_id=review_id,
        dry_run=dry_run,
    )
    if not dry_run:
        _write_json(
            files.attribution_json, attribution_output.model_dump(mode="json")
        )

    metrics_output = run_aggregator(data_output, attribution_output)
    if not dry_run:
        _write_json(files.metrics_json, metrics_output.model_dump(mode="json"))

    critic_llm = factory("critic")
    critique_md = run_critic(
        metrics_output,
        llm=critic_llm,
        db_conn=db_conn,
        review_id=review_id,
        cheatsheet_path=cheatsheet_path,
        dry_run=dry_run,
    )
    if not dry_run:
        files.critique_md.write_text(critique_md, encoding="utf-8", newline="\n")

    proposer_llm = factory("proposer")
    proposer_result = run_proposer(
        critique_md,
        metrics_output,
        llm=proposer_llm,
        db_conn=db_conn,
        review_id=review_id,
        proposals_dir=proposals_dir,
        now=timestamp,
        dry_run=dry_run,
    )
    if not dry_run:
        files.proposals_created_md.write_text(
            proposer_result.proposals_created_md,
            encoding="utf-8",
            newline="\n",
        )

    report_md = _render_report_md(
        review_id=review_id,
        period_from=period_from,
        period_to=period_to,
        data_output=data_output,
        metrics_output=metrics_output,
        proposer_result=proposer_result,
    )
    if not dry_run:
        files.report_md.write_text(report_md, encoding="utf-8", newline="\n")

    total_in = total_out = 0
    total_cost = 0.0
    for llm in (attributor_llm, critic_llm, proposer_llm):
        for usage in getattr(llm, "usages", []):
            total_in += int(usage.input_tokens)
            total_out += int(usage.output_tokens)
            total_cost += float(usage.cost_usd)

    completed_at = datetime.now(_TPE).isoformat(timespec="seconds")
    proposals_created = len(proposer_result.written_paths)

    if not dry_run:
        upsert_index_entry(
            out_dir,
            IndexEntry(
                review_id=review_id,
                kind=kind,
                period=Period.model_validate(
                    {"from": period_from, "to": period_to}
                ),
                trade_count=metrics_output.overall.total_trades,
                win_rate=metrics_output.overall.win_rate,
                pf=metrics_output.overall.profit_factor,
                proposals_created=proposals_created,
                completed_at=completed_at,
            ),
        )

    return ReviewResult(
        review_id=review_id,
        period_from=period_from,
        period_to=period_to,
        trade_count=metrics_output.overall.total_trades,
        proposals_created=proposals_created,
        proposals_files=[p.name for p in proposer_result.written_paths],
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        total_cost_usd=round(total_cost, 6),
        out_dir=str(out_dir),
        proposals_dir=str(proposals_dir),
        dry_run=dry_run,
    )


def _default_llm_factory() -> Callable[[str], ReviewLLM]:
    """Factory wired to the live Anthropic API."""
    settings = Settings()
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set; either configure it or pass an "
            "llm_factory to run_review"
        )
    client = Anthropic(api_key=settings.anthropic_api_key)
    model_map = {
        "attributor": "claude-sonnet-4-6",
        "critic": "claude-opus-4-7",
        "proposer": "claude-opus-4-7",
    }

    def _factory(node: str) -> ReviewLLM:
        if node not in model_map:
            raise KeyError(f"unknown review node: {node!r}")
        return AnthropicReviewLLM(client, model_map[node])

    return _factory


def _write_json(path: Path, payload: object) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    path.write_text(body + "\n", encoding="utf-8", newline="\n")


def _render_report_md(
    *,
    review_id: str,
    period_from: date,
    period_to: date,
    data_output: DataLoaderOutput,
    metrics_output: MetricsOutput,
    proposer_result: ProposerResult,
) -> str:
    lines = [
        f"# 復盤報告 — {review_id}",
        "",
        f"- 期間: {period_from.isoformat()} ~ {period_to.isoformat()}",
        f"- 交易筆數: {metrics_output.overall.total_trades}",
        f"- 拒絕筆數: {data_output.stats.total_rejects}",
        f"- 過期筆數: {data_output.stats.total_expires}",
        f"- 勝率: {metrics_output.overall.win_rate}",
        f"- Profit Factor: {metrics_output.overall.profit_factor}",
        f"- 期望值 (%): {metrics_output.overall.expectancy_pct}",
        f"- Max Drawdown (%): {metrics_output.overall.max_drawdown_pct}",
        f"- 提案數: {len(proposer_result.written_paths)}",
        "",
        "## 摘要",
        "",
        _render_summary(data_output, metrics_output, proposer_result),
        "",
        "## 連結",
        "",
        "- [attribution.json](./attribution.json)",
        "- [metrics.json](./metrics.json)",
        "- [critique.md](./critique.md)",
        "- [proposals_created.md](./proposals_created.md)",
        "",
    ]
    return "\n".join(lines)


def _render_summary(
    data_output: DataLoaderOutput,
    metrics: MetricsOutput,
    proposer_result: ProposerResult,
) -> str:
    if metrics.overall.total_trades == 0:
        return "本期區間內無已關閉交易,無歸因 / 提案產出。"
    parts = [
        (
            f"本期共 {metrics.overall.total_trades} 筆交易, 勝率 "
            f"{metrics.overall.win_rate}, profit factor {metrics.overall.profit_factor},"
            f" 期望值 {metrics.overall.expectancy_pct}%。"
        ),
        (
            f"另有 {data_output.stats.total_rejects} 筆拒絕、"
            f"{data_output.stats.total_expires} 筆 confirm 過期。"
        ),
    ]
    if proposer_result.written_paths:
        parts.append(
            f"批判節點驅動 {len(proposer_result.written_paths)} 份提案,"
            "詳見 proposals_created.md。"
        )
    else:
        parts.append("批判無高/中警示,本期未產出提案。")
    return "\n".join(parts)
