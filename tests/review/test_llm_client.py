"""Coverage for review.llm_client.

Spec: openspec/changes/phase5-review-mvp/specs/post-trade-review-pipeline/spec.md
Requirement: LLM 呼叫成本寫入 llm_costs 表
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

from ohmystock.review.llm_client import (
    AnthropicReviewLLM,
    FakeReviewLLM,
    ReviewLLMParseError,
    call_llm,
)


class _DemoSchema(BaseModel):
    answer: str


def test_cost_row_written_on_success(journal_conn) -> None:
    fake = FakeReviewLLM(responses=[{"answer": "ok"}], model="fake://attributor")
    parsed, usage = call_llm(
        fake,
        system="sys",
        user="u",
        schema=_DemoSchema,
        review_id="manual-2026-04-01-to-2026-04-30",
        db_conn=journal_conn,
    )
    assert parsed.answer == "ok"  # type: ignore[union-attr]
    assert usage.model == "fake://attributor"

    rows = journal_conn.execute(
        "SELECT decision_id, model, input_tokens, output_tokens FROM llm_costs"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "manual-2026-04-01-to-2026-04-30"
    assert rows[0][1] == "fake://attributor"
    assert rows[0][2] == 100
    assert rows[0][3] == 50


def test_dry_run_does_not_write_cost(journal_conn) -> None:
    fake = FakeReviewLLM(responses=[{"answer": "ok"}])
    call_llm(
        fake,
        system="sys",
        user="u",
        schema=_DemoSchema,
        review_id="manual-2026-04-01-to-2026-04-30",
        db_conn=journal_conn,
        dry_run=True,
    )
    rows = journal_conn.execute("SELECT COUNT(*) FROM llm_costs").fetchone()
    assert rows[0] == 0


def test_parse_error_on_invalid_json(journal_conn) -> None:
    fake = FakeReviewLLM(responses=["{not-json"])
    with pytest.raises(ReviewLLMParseError):
        call_llm(
            fake,
            system="s",
            user="u",
            schema=_DemoSchema,
            review_id="r",
            db_conn=journal_conn,
        )


def test_validation_error_on_schema_mismatch(journal_conn) -> None:
    fake = FakeReviewLLM(responses=[{"unexpected": 1}])
    with pytest.raises(ReviewLLMParseError):
        call_llm(
            fake,
            system="s",
            user="u",
            schema=_DemoSchema,
            review_id="r",
            db_conn=journal_conn,
        )


def test_cache_blocks_propagate_to_anthropic_payload() -> None:
    captured: dict[str, Any] = {}

    class _MockAnthropic:
        def __init__(self) -> None:
            self.messages = MagicMock()
            response = MagicMock()
            response.content = [MagicMock(text='{"answer": "ok"}')]
            response.usage = MagicMock(input_tokens=10, output_tokens=5)
            self.messages.create = MagicMock(return_value=response)

    client = _MockAnthropic()
    llm = AnthropicReviewLLM(client, model="claude-opus-4-7")
    text, usage = llm.complete(
        "instructions",
        "user payload",
        cache_blocks=["cheatsheet text"],
    )
    captured.update(client.messages.create.call_args.kwargs)

    assert isinstance(captured["system"], list)
    assert captured["system"][0]["type"] == "text"
    assert captured["system"][0]["text"] == "cheatsheet text"
    assert captured["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert captured["system"][1]["text"] == "instructions"
    assert text == '{"answer": "ok"}'
    assert usage.input_tokens == 10


def test_expect_json_false_returns_raw_text(journal_conn) -> None:
    fake = FakeReviewLLM(responses=["plain text"])
    result, _ = call_llm(
        fake,
        system="s",
        user="u",
        schema=None,
        review_id="r",
        db_conn=journal_conn,
        expect_json=False,
    )
    assert result == "plain text"
