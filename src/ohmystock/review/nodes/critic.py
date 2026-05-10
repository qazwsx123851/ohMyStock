"""Phase 5 critic node — Opus 4.7 with cheatsheet prompt cache.

Spec: openspec/changes/phase5-review-mvp/specs/post-trade-review-pipeline/spec.md
SSOT: docs/post-trade-review-rubric.md §4
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ohmystock.review.llm_client import ReviewLLM, call_llm
from ohmystock.review.models import MetricsOutput


_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "critic.md"
_TOKEN_BUDGET = 80_000
_CHARS_PER_TOKEN_ESTIMATE = 3
_EMPTY_CRITIQUE = (
    "### 高警示\n\n(無)\n\n"
    "### 中警示\n\n(無)\n\n"
    "### 觀察項\n\n本期無交易,無警示。\n"
)


class CriticTokenBudgetExceededError(Exception):
    """Raised when the cheatsheet + metrics + system prompt exceeds 80K tokens."""


def run_critic(
    metrics: MetricsOutput,
    *,
    llm: ReviewLLM,
    db_conn: sqlite3.Connection | None,
    review_id: str,
    cheatsheet_path: Path,
    dry_run: bool = False,
) -> str:
    """Return the ``critique.md`` body string."""

    if metrics.overall.total_trades == 0:
        return _EMPTY_CRITIQUE

    cheatsheet_text = cheatsheet_path.read_text(encoding="utf-8")
    system_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    metrics_payload = json.dumps(
        metrics.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    )
    user_payload = (
        "Here is `metrics.json` for the period (the JSON keys match the "
        "rubric §3 schema):\n\n```json\n"
        + metrics_payload
        + "\n```\n\nWrite the critique now."
    )

    total_chars = len(cheatsheet_text) + len(system_prompt) + len(user_payload)
    estimated_tokens = total_chars // _CHARS_PER_TOKEN_ESTIMATE
    if estimated_tokens > _TOKEN_BUDGET:
        raise CriticTokenBudgetExceededError(
            f"critic input estimated at {estimated_tokens} tokens, exceeds "
            f"budget {_TOKEN_BUDGET}; truncate cheatsheet or split metrics"
        )

    text, _usage = call_llm(
        llm,
        system=system_prompt,
        user=user_payload,
        schema=None,
        review_id=review_id,
        db_conn=db_conn,
        expect_json=False,
        cache_blocks=[cheatsheet_text],
        dry_run=dry_run,
        max_tokens=4096,
    )
    return text  # type: ignore[return-value]
