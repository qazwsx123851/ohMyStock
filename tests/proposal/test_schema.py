"""ProposalDraft validator coverage.

Spec: openspec/changes/phase5-review-mvp/specs/proposal-writer/spec.md
Requirement: 提供 ProposalDraft frozen pydantic model
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from ohmystock.proposal import ProposalDraft


_TPE = timezone(timedelta(hours=8))


def _kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "topic": "vcp-volume-threshold",
        "target_section": "cheatsheet §6.4",
        "created_by": "post_trade_review_team",
        "created_at": datetime(2026, 4, 30, 19, 30, tzinfo=_TPE),
        "review_id": "manual-2026-04-01-to-2026-04-30",
        "priority": "high",
        "description": "VCP 量能門檻 1.5x → 1.3x。",
        "motivation": "metrics.json#/by_pattern/VCP win_rate=0.375 太低。",
        "diff_draft": "```diff\n- a\n+ b\n```",
        "expected_impact": "影響 vcp.py。",
        "risk_assessment": "風險:過嚴漏 VCP。",
        "validation_plan": "WFA 5+1 滾動。",
        "expected_improvement": "win_rate 0.565 → 0.60。",
    }
    base.update(overrides)
    return base


def test_minimal_valid_draft_constructs() -> None:
    draft = ProposalDraft(**_kwargs())  # type: ignore[arg-type]
    assert draft.topic == "vcp-volume-threshold"
    assert draft.priority == "high"


def test_extra_field_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ProposalDraft(**_kwargs(status="approved"))  # type: ignore[arg-type]
    assert "status" in str(exc_info.value)


def test_topic_non_kebab_case_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ProposalDraft(**_kwargs(topic="VCP_volume_threshold"))  # type: ignore[arg-type]
    assert "kebab-case" in str(exc_info.value)


def test_topic_too_long_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ProposalDraft(**_kwargs(topic="x" * 41))  # type: ignore[arg-type]
    assert "40" in str(exc_info.value)


def test_motivation_without_metrics_pointer_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ProposalDraft(
            **_kwargs(motivation="VCP 命中率太低,建議放寬。")  # type: ignore[arg-type]
        )
    assert "metrics.json#" in str(exc_info.value)


def test_naive_datetime_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ProposalDraft(
            **_kwargs(created_at=datetime(2026, 4, 30, 19, 30))  # type: ignore[arg-type]
        )
    assert (
        "timezone" in str(exc_info.value).lower()
        or "tzinfo" in str(exc_info.value).lower()
    )
