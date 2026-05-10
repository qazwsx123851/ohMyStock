"""Phase 5 attributor node — rule-first + LLM fallback.

Spec: openspec/changes/phase5-review-mvp/specs/post-trade-review-pipeline/spec.md
SSOT: docs/post-trade-review-rubric.md §2
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ohmystock.review.llm_client import ReviewLLM, ReviewLLMParseError, call_llm
from ohmystock.review.models import (
    AttributionCategory,
    AttributionOutput,
    AttributionRow,
    CategoryDistribution,
    DataLoaderOutput,
    TradeRow,
)


_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "attributor.md"
_LLM_TIME_STOP_THRESHOLD = 0.05
_LLM_STOP_SAVED_THRESHOLD = -0.05
_RULE_EXIT_TAGS = {
    "time_stop",
    "hit_stop_loss",
    "hit_t1",
    "hit_t1_5",
    "chandelier",
    "thesis_invalid",
}


class AttributorOutputParseError(Exception):
    """Raised when the LLM response category is not in the six-Literal set."""


class _LLMAttributionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision_id: str
    category: AttributionCategory
    evidence: str


class _LLMAttributionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[_LLMAttributionItem]


def run_attributor(
    data_output: DataLoaderOutput,
    *,
    llm: ReviewLLM,
    db_conn: sqlite3.Connection | None,
    review_id: str,
    dry_run: bool = False,
) -> AttributionOutput:
    """Classify each trade and emit ``AttributionOutput``."""

    trades = list(data_output.trades)
    if not trades:
        return AttributionOutput(
            review_id=review_id,
            attribution=[],
            category_distribution=CategoryDistribution(),
        )

    rule_categories: dict[str, AttributionCategory | None] = {
        t.decision_id: _rule_classify(t) for t in trades
    }

    user_payload = json.dumps(
        {
            "trades": [
                _trade_to_llm_input(t, rule_categories[t.decision_id])
                for t in trades
            ]
        },
        ensure_ascii=False,
    )

    system_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    try:
        parsed_obj, _usage = call_llm(
            llm,
            system=system_prompt,
            user=user_payload,
            schema=_LLMAttributionResponse,
            review_id=review_id,
            db_conn=db_conn,
            dry_run=dry_run,
            max_tokens=8192,
        )
    except ReviewLLMParseError as exc:
        raise AttributorOutputParseError(str(exc)) from exc

    parsed: _LLMAttributionResponse = parsed_obj  # type: ignore[assignment]
    by_id = {item.decision_id: item for item in parsed.items}

    rows: list[AttributionRow] = []
    counters: dict[str, int] = {
        "thesis_held": 0,
        "thesis_failed_but_profit": 0,
        "thesis_failed_loss": 0,
        "stop_saved": 0,
        "time_stop_correct": 0,
        "time_stop_wrong": 0,
    }

    for trade in trades:
        rule_cat = rule_categories[trade.decision_id]
        llm_item = by_id.get(trade.decision_id)
        if llm_item is None:
            raise AttributorOutputParseError(
                f"LLM did not return an item for decision_id={trade.decision_id}"
            )
        category: AttributionCategory = (
            rule_cat if rule_cat is not None else llm_item.category
        )
        rows.append(
            AttributionRow(
                decision_id=trade.decision_id,
                category=category,
                evidence=llm_item.evidence,
                post_exit_return_5d=trade.post_exit_return_5d,
                rule_based=rule_cat is not None,
            )
        )
        counters[category] += 1

    return AttributionOutput(
        review_id=review_id,
        attribution=rows,
        category_distribution=CategoryDistribution(**counters),
    )


def _rule_classify(t: TradeRow) -> AttributionCategory | None:
    """Return the rule-determined category, or ``None`` to force LLM."""

    if t.data_missing:
        return None
    if t.exit_tag is None or t.exit_tag not in _RULE_EXIT_TAGS:
        return None

    if t.exit_tag == "time_stop":
        if t.post_exit_return_5d is None:
            return None
        return (
            "time_stop_wrong"
            if t.post_exit_return_5d > _LLM_TIME_STOP_THRESHOLD
            else "time_stop_correct"
        )

    if t.exit_tag == "hit_stop_loss":
        if t.post_exit_return_10d is None:
            return None
        return (
            "stop_saved"
            if t.post_exit_return_10d < _LLM_STOP_SAVED_THRESHOLD
            else "thesis_failed_loss"
        )

    if t.exit_tag == "thesis_invalid":
        if t.pnl_pct is None:
            return None
        return "thesis_failed_loss" if t.pnl_pct < 0 else "thesis_failed_but_profit"

    return None


def _trade_to_llm_input(
    t: TradeRow, rule_category: AttributionCategory | None
) -> dict:
    return {
        "decision_id": t.decision_id,
        "symbol": t.symbol,
        "exit_tag": t.exit_tag,
        "pnl_pct": t.pnl_pct,
        "hold_days": t.hold_days,
        "post_exit_return_5d": t.post_exit_return_5d,
        "post_exit_return_10d": t.post_exit_return_10d,
        "post_exit_return_20d": t.post_exit_return_20d,
        "entry_thesis": t.entry_thesis,
        "cited_skills": list(t.cited_skills),
        "data_missing": t.data_missing,
        "rule_suggested_category": rule_category,
    }
