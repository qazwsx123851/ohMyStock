"""write_proposal output shape coverage.

Spec: openspec/changes/phase5-review-mvp/specs/proposal-writer/spec.md
Requirement: write_proposal 寫出 markdown 並強制 status=pending
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from ohmystock.proposal import ProposalDraft, write_proposal


_TPE = timezone(timedelta(hours=8))


def _draft() -> ProposalDraft:
    return ProposalDraft(
        topic="vcp-volume-threshold",
        target_section="cheatsheet §6.4 加分項 + §9 K 線型態庫",
        created_by="post_trade_review_team",
        created_at=datetime(2026, 4, 30, 19, 30, tzinfo=_TPE),
        review_id="manual-2026-04-01-to-2026-04-30",
        priority="high",
        description="VCP 量能門檻 1.5x → 1.3x,新增收盤站穩 EMA10。",
        motivation="metrics.json#/by_pattern/VCP n=8 win_rate=0.375。",
        diff_draft="```diff\n- VCP_VOLUME=1.5\n+ VCP_VOLUME=1.3\n```",
        expected_impact="vcp.py + scoring.py + breakout.md。",
        risk_assessment="風險:過嚴漏 VCP,需 WFA 驗。",
        validation_plan="WFA 5+1 滾動。樣本內外 Sharpe 落差 < 30%。",
        expected_improvement="win_rate 0.565 → 0.60。",
    )


def test_status_forced_pending(tmp_path: Path) -> None:
    path = write_proposal(_draft(), tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "status: pending" in text
    assert "status: approved" not in text
    assert "status: validating" not in text


def test_eight_section_headers_in_order(tmp_path: Path) -> None:
    path = write_proposal(_draft(), tmp_path)
    text = path.read_text(encoding="utf-8")
    expected = [
        "## 1. 改動描述",
        "## 2. 動機與佐證",
        "## 3. 改動 diff 草稿",
        "## 4. 預期影響範圍",
        "## 5. 風險評估",
        "## 6. 驗證計畫",
        "## 7. 預期改善幅度",
        "## 8. 變更紀錄",
    ]
    last = -1
    for header in expected:
        idx = text.find(header)
        assert idx != -1, f"missing header {header}"
        assert idx > last, f"header out of order: {header}"
        last = idx


def test_changelog_includes_created_line(tmp_path: Path) -> None:
    path = write_proposal(_draft(), tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "- 2026-04-30T19:30:00+08:00 created by post_trade_review_team" in text


def test_proposal_id_matches_filename(tmp_path: Path) -> None:
    path = write_proposal(_draft(), tmp_path)
    assert path.name == "2026-04-30-vcp-volume-threshold.md"
    text = path.read_text(encoding="utf-8")
    assert "proposal_id: 2026-04-30-vcp-volume-threshold" in text
