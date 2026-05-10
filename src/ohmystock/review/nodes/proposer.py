"""Phase 5 proposer node — Opus 4.7 → ProposalDraft markdown writes.

Spec: openspec/changes/phase5-review-mvp/specs/post-trade-review-pipeline/spec.md
SSOT: docs/post-trade-review-rubric.md §5
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from ohmystock.proposal import ProposalDraft, write_proposal
from ohmystock.review.llm_client import ReviewLLM, ReviewLLMParseError, call_llm
from ohmystock.review.models import MetricsOutput


_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "proposer.md"
_TPE = timezone(timedelta(hours=8))
_HIGH_HEADING_RE = re.compile(r"^###\s+高警示\s*$", re.MULTILINE)
_MEDIUM_HEADING_RE = re.compile(r"^###\s+中警示\s*$", re.MULTILINE)
_OBSERVATION_HEADING_RE = re.compile(r"^###\s+觀察項\s*$", re.MULTILINE)
_NUMBERED_ITEM_RE = re.compile(r"^\s*\d+\.\s", re.MULTILINE)


class ProposerOutputParseError(Exception):
    """Raised when an LLM proposal entry cannot be coerced into ProposalDraft."""


@dataclass(frozen=True)
class ProposerResult:
    written_paths: list[Path]
    skipped: list[str]
    proposals_created_md: str


class _LLMProposalItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str
    target_section: str
    priority: str
    description: str
    motivation: str
    diff_draft: str
    expected_impact: str
    risk_assessment: str
    validation_plan: str
    expected_improvement: str


class _LLMProposerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposals: list[_LLMProposalItem]


def run_proposer(
    critique_md: str,
    metrics: MetricsOutput,
    *,
    llm: ReviewLLM,
    db_conn: sqlite3.Connection | None,
    review_id: str,
    proposals_dir: Path,
    created_by: str = "post_trade_review_team",
    now: datetime | None = None,
    dry_run: bool = False,
) -> ProposerResult:
    """Run the proposer LLM, write 0..N proposals, return summary."""

    has_warnings = _has_high_or_medium_warnings(critique_md)
    if not has_warnings:
        return ProposerResult(
            written_paths=[],
            skipped=[],
            proposals_created_md="# 本次復盤產生的提案\n\n本期無提案。\n",
        )

    system_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    user_payload = json.dumps(
        {
            "critique_md": critique_md,
            "metrics": metrics.model_dump(mode="json"),
        },
        ensure_ascii=False,
    )

    try:
        parsed_obj, _usage = call_llm(
            llm,
            system=system_prompt,
            user=user_payload,
            schema=_LLMProposerResponse,
            review_id=review_id,
            db_conn=db_conn,
            dry_run=dry_run,
            max_tokens=8192,
        )
    except ReviewLLMParseError as exc:
        raise ProposerOutputParseError(str(exc)) from exc

    response: _LLMProposerResponse = parsed_obj  # type: ignore[assignment]
    timestamp = now or datetime.now(_TPE)

    written: list[tuple[Path, _LLMProposalItem, bool]] = []
    skipped: list[str] = []

    if dry_run:
        return ProposerResult(
            written_paths=[],
            skipped=[],
            proposals_created_md=_render_proposals_created_md([], dry_run=True),
        )

    for item in response.proposals:
        try:
            draft = ProposalDraft(
                topic=item.topic,
                target_section=item.target_section,
                created_by=created_by,
                created_at=timestamp,
                review_id=review_id,
                priority=item.priority,  # type: ignore[arg-type]
                description=item.description,
                motivation=item.motivation,
                diff_draft=item.diff_draft,
                expected_impact=item.expected_impact,
                risk_assessment=item.risk_assessment,
                validation_plan=item.validation_plan,
                expected_improvement=item.expected_improvement,
            )
        except ValidationError as exc:
            raise ProposerOutputParseError(
                f"LLM proposal {item.topic!r} failed ProposalDraft validation: {exc}"
            ) from exc

        base = proposals_dir / f"{timestamp.date().isoformat()}-{item.topic}.md"
        had_collision = base.exists()
        path = write_proposal(draft, proposals_dir)
        written.append((path, item, had_collision))
        if had_collision:
            skipped.append(path.name)

    proposals_created_md = _render_proposals_created_md(written, dry_run=False)

    return ProposerResult(
        written_paths=[p for p, _i, _c in written],
        skipped=skipped,
        proposals_created_md=proposals_created_md,
    )


def _has_high_or_medium_warnings(critique_md: str) -> bool:
    sections = _split_sections(critique_md)
    high = sections.get("高警示", "")
    medium = sections.get("中警示", "")
    return _has_numbered_item(high) or _has_numbered_item(medium)


def _split_sections(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    matches: list[tuple[str, int]] = []
    for label, pattern in (
        ("高警示", _HIGH_HEADING_RE),
        ("中警示", _MEDIUM_HEADING_RE),
        ("觀察項", _OBSERVATION_HEADING_RE),
    ):
        m = pattern.search(text)
        if m is not None:
            matches.append((label, m.end()))
    matches.sort(key=lambda item: item[1])
    for idx, (label, start) in enumerate(matches):
        end = matches[idx + 1][1] if idx + 1 < len(matches) else len(text)
        out[label] = text[start:end]
    return out


def _has_numbered_item(section: str) -> bool:
    return bool(_NUMBERED_ITEM_RE.search(section))


def _render_proposals_created_md(
    written: list[tuple[Path, _LLMProposalItem, bool]],
    *,
    dry_run: bool,
) -> str:
    if not written:
        if dry_run:
            return "# 本次復盤產生的提案 (dry-run)\n\n本期無提案。\n"
        return "# 本次復盤產生的提案\n\n本期無提案。\n"

    lines = [
        "# 本次復盤產生的提案",
        "",
        "| Proposal | Status | Priority | Target | Note |",
        "|---|---|---|---|---|",
    ]
    for path, item, collision in written:
        rel = f"../../proposals/{path.name}"
        note = "[skipped: file exists]" if collision else ""
        lines.append(
            f"| [{path.stem}]({rel}) | pending | {item.priority} | "
            f"{item.target_section} | {note} |"
        )
    lines.append("")
    return "\n".join(lines)
