"""Round-trip write -> parse coverage for proposal markdown.

Spec: openspec/changes/phase5-review-mvp/specs/proposal-writer/spec.md
Requirement: validate_template 對既有檔案 round-trip 解析
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ohmystock.proposal import (
    ProposalDraft,
    ProposalParseError,
    parse_proposal,
    write_proposal,
)


_TPE = timezone(timedelta(hours=8))


def _draft() -> ProposalDraft:
    return ProposalDraft(
        topic="vcp-volume-threshold",
        target_section="cheatsheet §6.4",
        created_by="post_trade_review_team",
        created_at=datetime(2026, 4, 30, 19, 30, tzinfo=_TPE),
        review_id="manual-2026-04-01-to-2026-04-30",
        priority="high",
        description="VCP 量能 1.5 → 1.3。",
        motivation="metrics.json#/by_pattern/VCP n=8 win_rate=0.375。",
        diff_draft="```diff\n- a\n+ b\n```",
        expected_impact="vcp.py。",
        risk_assessment="風險:過嚴漏 VCP。",
        validation_plan="WFA 5+1。",
        expected_improvement="0.565 → 0.60。",
    )


def test_round_trip_recovers_draft(tmp_path: Path) -> None:
    draft = _draft()
    path = write_proposal(draft, tmp_path)
    parsed = parse_proposal(path)

    assert parsed.topic == draft.topic
    assert parsed.target_section == draft.target_section
    assert parsed.created_by == draft.created_by
    assert parsed.created_at == draft.created_at
    assert parsed.review_id == draft.review_id
    assert parsed.priority == draft.priority
    assert parsed.description == draft.description
    assert parsed.motivation == draft.motivation
    assert parsed.diff_draft == draft.diff_draft
    assert parsed.expected_impact == draft.expected_impact
    assert parsed.risk_assessment == draft.risk_assessment
    assert parsed.validation_plan == draft.validation_plan
    assert parsed.expected_improvement == draft.expected_improvement


def test_parse_missing_section_raises(tmp_path: Path) -> None:
    path = write_proposal(_draft(), tmp_path)
    text = path.read_text(encoding="utf-8")
    start = text.index("## 5. 風險評估")
    next_header = text.index("## 6. 驗證計畫")
    mutated = text[:start] + text[next_header:]
    path.write_text(mutated, encoding="utf-8")

    with pytest.raises(ProposalParseError) as exc_info:
        parse_proposal(path)
    msg = str(exc_info.value)
    assert "風險評估" in msg or "risk_assessment" in msg


def test_parse_missing_frontmatter_raises(tmp_path: Path) -> None:
    bad = tmp_path / "2026-04-30-no-frontmatter.md"
    bad.write_text("## 1. 改動描述\n\nbody\n", encoding="utf-8")
    with pytest.raises(ProposalParseError) as exc_info:
        parse_proposal(bad)
    assert "frontmatter" in str(exc_info.value).lower()


def test_round_trip_with_review_id_null(tmp_path: Path) -> None:
    draft = _draft().model_copy(update={"review_id": None})
    path = write_proposal(draft, tmp_path)
    parsed = parse_proposal(path)
    assert parsed.review_id is None
