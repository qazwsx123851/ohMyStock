"""Shared LLM helper for the Phase 5 review pipeline.

Spec: openspec/changes/phase5-review-mvp/specs/post-trade-review-pipeline/spec.md
Reuses ``ohmystock.decider.node.AnthropicPMConclusionNode`` pattern.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from ohmystock.decider._pricing import compute_cost_usd
from ohmystock.decider.node import LLMUsage


_TPE = timezone(timedelta(hours=8))

T = TypeVar("T", bound=BaseModel)


class ReviewLLMParseError(Exception):
    """Raised when an LLM response cannot be parsed / validated."""

    def __init__(self, raw_text: str, cause: Exception) -> None:
        truncated = (raw_text or "")[:500]
        super().__init__(
            f"failed to parse review LLM output ({type(cause).__name__}): "
            f"{truncated[:120]}"
        )
        self.raw_text = truncated
        self.cause = cause


@dataclass(frozen=True)
class CostRow:
    decision_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    created_at: str


class ReviewLLM(Protocol):
    """Strategy interface used by all three review LLM nodes."""

    model: str

    def complete(
        self,
        system: str,
        user: str,
        *,
        cache_blocks: list[str] | None = None,
        max_tokens: int = 4096,
    ) -> tuple[str, LLMUsage]:
        ...


class AnthropicReviewLLM:
    """Production implementation backed by ``anthropic.Anthropic.messages.create``."""

    def __init__(self, client: Any, model: str) -> None:
        self.client = client
        self.model = model
        self.usages: list[LLMUsage] = []

    def complete(
        self,
        system: str,
        user: str,
        *,
        cache_blocks: list[str] | None = None,
        max_tokens: int = 4096,
    ) -> tuple[str, LLMUsage]:
        if cache_blocks:
            system_payload: list[dict[str, Any]] = [
                {
                    "type": "text",
                    "text": block,
                    "cache_control": {"type": "ephemeral"},
                }
                for block in cache_blocks
            ]
            if system:
                system_payload.append({"type": "text", "text": system})
            response = self.client.messages.create(
                model=self.model,
                system=system_payload,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": user}],
            )
        else:
            response = self.client.messages.create(
                model=self.model,
                system=system,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": user}],
            )

        text = _extract_text(response)
        usage = response.usage
        input_tokens = int(usage.input_tokens)
        output_tokens = int(usage.output_tokens)
        cost = compute_cost_usd(self.model, input_tokens, output_tokens)
        recorded = LLMUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            model=self.model,
        )
        self.usages.append(recorded)
        return text, recorded


class FakeReviewLLM:
    """Test fixture LLM with a queue of pre-baked responses."""

    def __init__(
        self,
        responses: list[Any],
        *,
        model: str = "fake://review",
        input_tokens: int = 100,
        output_tokens: int = 50,
    ) -> None:
        self.responses = list(responses)
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.calls: list[dict[str, Any]] = []
        self.usages: list[LLMUsage] = []

    def complete(
        self,
        system: str,
        user: str,
        *,
        cache_blocks: list[str] | None = None,
        max_tokens: int = 4096,
    ) -> tuple[str, LLMUsage]:
        self.calls.append(
            {
                "system": system,
                "user": user,
                "cache_blocks": list(cache_blocks) if cache_blocks else [],
                "max_tokens": max_tokens,
            }
        )
        if not self.responses:
            raise RuntimeError(
                "FakeReviewLLM exhausted: no more pre-baked responses"
            )
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, str):
            text = item
        else:
            text = json.dumps(item, ensure_ascii=False)
        usage = LLMUsage(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cost_usd=0.0,
            model=self.model,
        )
        self.usages.append(usage)
        return text, usage


def call_llm(
    llm: ReviewLLM,
    *,
    system: str,
    user: str,
    schema: type[T] | None,
    review_id: str,
    db_conn: sqlite3.Connection | None,
    expect_json: bool = True,
    cache_blocks: list[str] | None = None,
    max_tokens: int = 4096,
    dry_run: bool = False,
) -> tuple[T | str, LLMUsage]:
    """Run one LLM call, parse + validate, and (unless dry_run) record cost."""
    text, usage = llm.complete(
        system, user, cache_blocks=cache_blocks, max_tokens=max_tokens
    )

    parsed: T | str
    if expect_json:
        if schema is None:
            raise ValueError("schema is required when expect_json=True")
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ReviewLLMParseError(text, exc) from exc
        try:
            parsed = schema.model_validate(obj)
        except ValidationError as exc:
            raise ReviewLLMParseError(text, exc) from exc
    else:
        parsed = text

    if not dry_run and db_conn is not None:
        write_llm_cost(db_conn, decision_id=review_id, usage=usage)

    return parsed, usage


def write_llm_cost(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    usage: LLMUsage,
    created_at: str | None = None,
) -> None:
    """Insert a single row into the shared ``llm_costs`` table."""
    ts = created_at or datetime.now(_TPE).isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO llm_costs"
        "(decision_id, model, input_tokens, output_tokens, cost_usd, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            decision_id,
            usage.model,
            int(usage.input_tokens),
            int(usage.output_tokens),
            float(usage.cost_usd),
            ts,
        ),
    )
    conn.commit()


def _extract_text(response: Any) -> str:
    content = getattr(response, "content", None)
    if not content:
        raise ReviewLLMParseError(
            "", ValueError("response.content is empty or missing")
        )
    block = content[0]
    text = getattr(block, "text", None)
    if not isinstance(text, str):
        raise ReviewLLMParseError(
            "", ValueError("response.content[0].text is not a string")
        )
    return text
