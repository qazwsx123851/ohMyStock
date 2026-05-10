"""Filename collision suffix coverage for write_proposal.

Spec: openspec/changes/phase5-review-mvp/specs/proposal-writer/spec.md
Requirement: 檔名衝突 auto-suffix 至 -99
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ohmystock.proposal import ProposalDraft, write_proposal


_TPE = timezone(timedelta(hours=8))


def _draft(topic: str = "vcp-volume-threshold") -> ProposalDraft:
    return ProposalDraft(
        topic=topic,
        target_section="cheatsheet §6.4",
        created_by="post_trade_review_team",
        created_at=datetime(2026, 4, 30, 19, 30, tzinfo=_TPE),
        review_id=None,
        priority="medium",
        description="d",
        motivation="see metrics.json#/x.",
        diff_draft="d",
        expected_impact="i",
        risk_assessment="r",
        validation_plan="v",
        expected_improvement="e",
    )


def _occupy(tmp_path: Path, *names: str) -> None:
    for name in names:
        (tmp_path / name).write_text("placeholder", encoding="utf-8")


def test_suffix_2_when_base_exists(tmp_path: Path) -> None:
    _occupy(tmp_path, "2026-04-30-vcp-volume-threshold.md")
    path = write_proposal(_draft(), tmp_path)
    assert path.name == "2026-04-30-vcp-volume-threshold-2.md"
    assert (
        tmp_path / "2026-04-30-vcp-volume-threshold.md"
    ).read_text(encoding="utf-8") == "placeholder"


def test_suffix_3_when_base_and_2_exist(tmp_path: Path) -> None:
    _occupy(
        tmp_path,
        "2026-04-30-vcp-volume-threshold.md",
        "2026-04-30-vcp-volume-threshold-2.md",
    )
    path = write_proposal(_draft(), tmp_path)
    assert path.name == "2026-04-30-vcp-volume-threshold-3.md"


def test_suffix_99_when_2_through_98_exist(tmp_path: Path) -> None:
    _occupy(tmp_path, "2026-04-30-vcp-volume-threshold.md")
    for n in range(2, 99):
        _occupy(tmp_path, f"2026-04-30-vcp-volume-threshold-{n}.md")
    path = write_proposal(_draft(), tmp_path)
    assert path.name == "2026-04-30-vcp-volume-threshold-99.md"


def test_runtime_error_when_99_exhausted(tmp_path: Path) -> None:
    _occupy(tmp_path, "2026-04-30-vcp-volume-threshold.md")
    for n in range(2, 100):
        _occupy(tmp_path, f"2026-04-30-vcp-volume-threshold-{n}.md")
    with pytest.raises(RuntimeError) as exc_info:
        write_proposal(_draft(), tmp_path)
    assert "too many proposals" in str(exc_info.value)
