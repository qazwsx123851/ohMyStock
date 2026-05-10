"""Unit tests for proposal state machine.

Spec: openspec/changes/proposal-state-machine/specs/proposal-state-machine/spec.md
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import get_args

import pytest

from ohmystock.proposal import (
    ProposalDraft,
    ProposalStateError,
    ProposalStatus,
    parse_proposal,
    transition_proposal,
    write_proposal,
)


_TPE = timezone(timedelta(hours=8))


def _draft(topic: str = "vcp-volume-threshold") -> ProposalDraft:
    return ProposalDraft(
        topic=topic,
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


def _make_md(
    tmp_path: Path,
    status: ProposalStatus,
    *,
    topic: str = "vcp-volume-threshold",
) -> Path:
    """Write a pending proposal then walk it through the legal edges
    until it reaches ``status``. Returns the final path.
    """
    draft = _draft(topic=topic)
    path = write_proposal(draft, tmp_path)
    if status == "pending":
        return path
    path = transition_proposal(path, "validating", actor="setup")
    if status == "validating":
        return path
    if status == "approved":
        return transition_proposal(
            path,
            "approved",
            actor="setup",
            validation_report_path=Path("v.json"),
        )
    if status == "rejected":
        return transition_proposal(
            path,
            "rejected",
            actor="setup",
            reason="setup-fixture",
        )
    if status == "merged":
        path = transition_proposal(
            path,
            "approved",
            actor="setup",
            validation_report_path=Path("v.json"),
        )
        return transition_proposal(
            path,
            "merged",
            actor="setup",
            merged_to_version="v3.1",
        )
    raise ValueError(f"unexpected fixture status: {status}")


# ---- Spec: Requirement 提供 ProposalStatus 與 ProposalStateError ----


def test_proposal_status_has_five_values() -> None:
    assert get_args(ProposalStatus) == (
        "pending",
        "validating",
        "approved",
        "merged",
        "rejected",
    )


def test_unknown_status_raises(tmp_path: Path) -> None:
    pending = _make_md(tmp_path, "pending")
    with pytest.raises(ProposalStateError) as exc_info:
        transition_proposal(pending, "approve", actor="mark")
    assert "unknown_status" in str(exc_info.value)


def test_case_variant_status_raises(tmp_path: Path) -> None:
    pending = _make_md(tmp_path, "pending")
    with pytest.raises(ProposalStateError) as exc_info:
        transition_proposal(pending, "Pending", actor="mark")
    assert "unknown_status" in str(exc_info.value)


# ---- Spec: Requirement 強制 5 條合法 transition edge ----


def test_legal_pending_to_validating(tmp_path: Path) -> None:
    pending = _make_md(tmp_path, "pending")
    new_path = transition_proposal(pending, "validating", actor="mark")
    assert new_path.exists()


def test_legal_validating_to_approved(tmp_path: Path) -> None:
    validating = _make_md(tmp_path, "validating")
    new_path = transition_proposal(
        validating,
        "approved",
        actor="mark",
        validation_report_path=Path("v.json"),
    )
    assert new_path.exists()


def test_legal_validating_to_rejected(tmp_path: Path) -> None:
    validating = _make_md(tmp_path, "validating")
    new_path = transition_proposal(
        validating, "rejected", actor="mark", reason="WFA fail"
    )
    assert new_path.exists()


def test_legal_approved_to_merged(tmp_path: Path) -> None:
    approved = _make_md(tmp_path, "approved")
    new_path = transition_proposal(
        approved,
        "merged",
        actor="mark",
        merged_to_version="v3.1",
    )
    assert new_path.exists()


def test_legal_approved_to_rejected(tmp_path: Path) -> None:
    approved = _make_md(tmp_path, "approved")
    new_path = transition_proposal(
        approved, "rejected", actor="mark", reason="rolled back"
    )
    assert new_path.exists()


def test_pending_to_approved_skip_raises(tmp_path: Path) -> None:
    pending = _make_md(tmp_path, "pending")
    with pytest.raises(ProposalStateError) as exc_info:
        transition_proposal(
            pending,
            "approved",
            actor="mark",
            validation_report_path=Path("v.json"),
        )
    assert "illegal_transition" in str(exc_info.value)


def test_same_state_raises(tmp_path: Path) -> None:
    validating = _make_md(tmp_path, "validating")
    with pytest.raises(ProposalStateError) as exc_info:
        transition_proposal(validating, "validating", actor="mark")
    assert "illegal_transition" in str(exc_info.value)


def test_merged_is_terminal(tmp_path: Path) -> None:
    merged = _make_md(tmp_path, "merged")
    with pytest.raises(ProposalStateError) as exc_info:
        transition_proposal(
            merged, "rejected", actor="mark", reason="found bug"
        )
    assert "illegal_transition" in str(exc_info.value)


def test_rejected_is_terminal(tmp_path: Path) -> None:
    rejected = _make_md(tmp_path, "rejected")
    with pytest.raises(ProposalStateError) as exc_info:
        transition_proposal(rejected, "validating", actor="mark")
    assert "illegal_transition" in str(exc_info.value)


# ---- Spec: Requirement required-args 由 new_status 決定 ----


def test_approved_missing_validation_report(tmp_path: Path) -> None:
    validating = _make_md(tmp_path, "validating")
    with pytest.raises(ProposalStateError) as exc_info:
        transition_proposal(validating, "approved", actor="mark")
    assert "missing_validation_report" in str(exc_info.value)


def test_merged_missing_version(tmp_path: Path) -> None:
    approved = _make_md(tmp_path, "approved")
    with pytest.raises(ProposalStateError) as exc_info:
        transition_proposal(approved, "merged", actor="mark")
    assert "missing_merged_to_version" in str(exc_info.value)


def test_rejected_missing_reason(tmp_path: Path) -> None:
    validating = _make_md(tmp_path, "validating")
    with pytest.raises(ProposalStateError) as exc_info:
        transition_proposal(validating, "rejected", actor="mark")
    assert "missing_rejection_reason" in str(exc_info.value)


def test_rejected_empty_reason_raises(tmp_path: Path) -> None:
    validating = _make_md(tmp_path, "validating")
    with pytest.raises(ProposalStateError) as exc_info:
        transition_proposal(validating, "rejected", actor="mark", reason="")
    assert "missing_rejection_reason" in str(exc_info.value)


def test_actor_empty_raises(tmp_path: Path) -> None:
    pending = _make_md(tmp_path, "pending")
    with pytest.raises(ProposalStateError) as exc_info:
        transition_proposal(pending, "validating", actor="")
    assert "missing_actor" in str(exc_info.value)


def test_validating_no_extra_args_required(tmp_path: Path) -> None:
    pending = _make_md(tmp_path, "pending")
    new_path = transition_proposal(pending, "validating", actor="mark")
    assert new_path.exists()


# ---- Spec: Requirement 自動搬到 status 對應的子資料夾 ----


def test_validating_to_approved_moves_to_pending_review(tmp_path: Path) -> None:
    validating = _make_md(tmp_path, "validating")
    new_path = transition_proposal(
        validating,
        "approved",
        actor="mark",
        validation_report_path=Path("v.json"),
    )
    assert new_path == tmp_path / "PENDING_REVIEW" / "2026-04-30-vcp-volume-threshold.md"
    assert not validating.exists()
    assert new_path.exists()


def test_approved_to_merged_moves_to_merged(tmp_path: Path) -> None:
    approved = _make_md(tmp_path, "approved")
    new_path = transition_proposal(
        approved,
        "merged",
        actor="mark",
        merged_to_version="v3.1",
    )
    assert new_path == tmp_path / "merged" / "2026-04-30-vcp-volume-threshold.md"
    assert not approved.exists()


def test_validating_to_rejected_moves_to_rejected(tmp_path: Path) -> None:
    validating = _make_md(tmp_path, "validating")
    new_path = transition_proposal(
        validating, "rejected", actor="mark", reason="WFA fail"
    )
    assert new_path == tmp_path / "rejected" / "2026-04-30-vcp-volume-threshold.md"
    assert not validating.exists()


def test_pending_to_validating_stays_in_root(tmp_path: Path) -> None:
    pending = _make_md(tmp_path, "pending")
    new_path = transition_proposal(pending, "validating", actor="mark")
    assert new_path == pending
    assert new_path.exists()


def test_sink_dir_lazy_created(tmp_path: Path) -> None:
    approved = _make_md(tmp_path, "approved")
    assert (tmp_path / "PENDING_REVIEW").exists()
    new_path = transition_proposal(
        approved, "merged", actor="mark", merged_to_version="v3.1"
    )
    assert (tmp_path / "merged").exists()
    assert new_path.exists()


def test_destination_exists_raises(tmp_path: Path) -> None:
    validating = _make_md(tmp_path, "validating")
    sink = tmp_path / "PENDING_REVIEW"
    sink.mkdir()
    leftover = sink / "2026-04-30-vcp-volume-threshold.md"
    leftover.write_text("preexisting\n", encoding="utf-8")

    with pytest.raises(ProposalStateError) as exc_info:
        transition_proposal(
            validating,
            "approved",
            actor="mark",
            validation_report_path=Path("v.json"),
        )
    assert "destination_exists" in str(exc_info.value)
    assert validating.exists()
    assert leftover.read_text(encoding="utf-8") == "preexisting\n"


# ---- Spec: Requirement frontmatter status 與 metadata 寫入 ----


def _read_frontmatter_block(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    assert len(parts) >= 3
    return parts[1]


def test_approved_writes_validation_report_path(tmp_path: Path) -> None:
    validating = _make_md(tmp_path, "validating")
    rpt = Path("proposals/2026-04-30-x.validation.json")
    new_path = transition_proposal(
        validating, "approved", actor="mark", validation_report_path=rpt
    )
    fm = _read_frontmatter_block(new_path)
    assert "status: approved" in fm
    assert "validation_report_path:" in fm
    assert str(rpt) in fm


def test_merged_writes_version_and_merged_at(tmp_path: Path) -> None:
    approved = _make_md(tmp_path, "approved")
    new_path = transition_proposal(
        approved, "merged", actor="mark", merged_to_version="v3.1"
    )
    fm = _read_frontmatter_block(new_path)
    assert "status: merged" in fm
    assert "merged_to_version: v3.1" in fm
    iso_re = re.compile(
        r"merged_at: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}"
    )
    assert iso_re.search(fm) is not None


def test_rejected_writes_rejected_reason(tmp_path: Path) -> None:
    validating = _make_md(tmp_path, "validating")
    new_path = transition_proposal(
        validating,
        "rejected",
        actor="mark",
        reason="WFA Sharpe drop > 30%",
    )
    fm = _read_frontmatter_block(new_path)
    assert "status: rejected" in fm
    assert "rejected_reason: WFA Sharpe drop > 30%" in fm


def test_existing_seven_keys_order_preserved(tmp_path: Path) -> None:
    pending = _make_md(tmp_path, "pending")
    new_path = transition_proposal(pending, "validating", actor="mark")
    fm = _read_frontmatter_block(new_path)

    keys = [
        line.split(":", 1)[0].strip()
        for line in fm.strip().splitlines()
        if line.strip() and ":" in line
    ]
    assert keys[:7] == [
        "proposal_id",
        "target_section",
        "status",
        "created_by",
        "created_at",
        "review_id",
        "priority",
    ]


def test_body_seven_sections_byte_identical(tmp_path: Path) -> None:
    pending = _make_md(tmp_path, "pending")
    original = pending.read_text(encoding="utf-8")
    new_path = transition_proposal(pending, "validating", actor="mark")
    after = new_path.read_text(encoding="utf-8")

    def _slice(text: str) -> str:
        start = text.index("## 1. 改動描述")
        end = text.index("## 8. 變更紀錄")
        return text[start:end]

    assert _slice(original) == _slice(after)


# ---- Spec: Requirement 變更紀錄追加格式 ----


def test_changelog_appends_basic_line(tmp_path: Path) -> None:
    pending = _make_md(tmp_path, "pending")
    new_path = transition_proposal(pending, "validating", actor="mark")
    text = new_path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"^- \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2} "
        r"status: pending → validating by mark$",
        re.MULTILINE,
    )
    assert pattern.search(text) is not None
    assert "- 2026-04-30T19:30:00+08:00 created by post_trade_review_team" in text


def test_changelog_appends_reason_in_parens(tmp_path: Path) -> None:
    validating = _make_md(tmp_path, "validating")
    new_path = transition_proposal(
        validating, "rejected", actor="mark", reason="WFA fail"
    )
    text = new_path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"^- \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2} "
        r"status: validating → rejected by mark \(WFA fail\)$",
        re.MULTILINE,
    )
    assert pattern.search(text) is not None


def test_malformed_changelog_raises_and_does_not_mutate(tmp_path: Path) -> None:
    pending = _make_md(tmp_path, "pending")
    text = pending.read_text(encoding="utf-8")
    mutated = text.replace("## 8. 變更紀錄", "## 8. removed-heading")
    pending.write_text(mutated, encoding="utf-8")
    snapshot = pending.read_text(encoding="utf-8")

    with pytest.raises(ProposalStateError) as exc_info:
        transition_proposal(pending, "validating", actor="mark")
    assert "malformed_changelog" in str(exc_info.value)
    assert pending.read_text(encoding="utf-8") == snapshot


# ---- Spec: Requirement 寫入原子性 ----


def test_no_tmp_residue_after_success(tmp_path: Path) -> None:
    pending = _make_md(tmp_path, "pending")
    transition_proposal(pending, "validating", actor="mark")
    leftovers = list(tmp_path.glob("**/*.md.tmp"))
    assert leftovers == []


def test_replace_failure_cleans_tmp_and_preserves_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pending = _make_md(tmp_path, "pending")
    snapshot = pending.read_text(encoding="utf-8")

    def _boom(src: str, dst: str) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr("ohmystock.proposal.state.os.replace", _boom)
    with pytest.raises(OSError, match="simulated replace failure"):
        transition_proposal(pending, "validating", actor="mark")

    assert list(tmp_path.glob("**/*.md.tmp")) == []
    assert pending.read_text(encoding="utf-8") == snapshot


# ---- Spec: Requirement parse_proposal round-trip 相容 ----


def test_parse_proposal_after_validating(tmp_path: Path) -> None:
    pending = _make_md(tmp_path, "pending")
    new_path = transition_proposal(pending, "validating", actor="mark")
    parsed = parse_proposal(new_path)
    assert parsed.topic == "vcp-volume-threshold"


def test_parse_proposal_after_merged_ignores_new_keys(tmp_path: Path) -> None:
    approved = _make_md(tmp_path, "approved")
    new_path = transition_proposal(
        approved, "merged", actor="mark", merged_to_version="v3.1"
    )
    parsed = parse_proposal(new_path)
    assert parsed.priority == "high"
