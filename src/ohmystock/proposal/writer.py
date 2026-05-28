"""Markdown writer + parser for strategy-change proposals.

Spec: openspec/changes/phase5-review-mvp/specs/proposal-writer/spec.md
SSOT: proposals/README.md §4 template (8 必填段落 + frontmatter)

``write_proposal`` is the only legitimate way LLM/human-authored proposals
land in ``proposals/``. It enforces three invariants:

1. ``status: pending`` — frontmatter is hard-coded, callers cannot override.
2. Filename ``<YYYY-MM-DD>-<topic>.md`` — ``<YYYY-MM-DD>`` is taken from
   ``draft.created_at.date()``, **not** the wall clock, so a re-run is
   stable for a given draft.
3. No overwrite — collisions get ``-2``..``-99`` suffixes; ``-99`` taken
   raises ``RuntimeError`` (fail-loud per design Decision 9).

``parse_proposal`` is the round-trip inverse used by tests and future
review consumers. It does not return ``status`` (writer's invariant 1
makes that always-known).
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from ohmystock.eventbus import Agent, Event, EventType, safe_emit_sync
from ohmystock.proposal.schema import ProposalDraft


_MAX_COLLISION_SUFFIX = 99

_SECTION_HEADERS: list[tuple[str, str]] = [
    ("description", "## 1. 改動描述"),
    ("motivation", "## 2. 動機與佐證"),
    ("diff_draft", "## 3. 改動 diff 草稿"),
    ("expected_impact", "## 4. 預期影響範圍"),
    ("risk_assessment", "## 5. 風險評估"),
    ("validation_plan", "## 6. 驗證計畫"),
    ("expected_improvement", "## 7. 預期改善幅度"),
]
_CHANGELOG_HEADER = "## 8. 變更紀錄"

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_SECTION_BREAK_RE = re.compile(r"^## \d+\. ", re.MULTILINE)


class ProposalParseError(Exception):
    """Raised when a proposal markdown cannot be parsed back into a ProposalDraft.

    ``message`` includes the offending field name or section title.
    """


def write_proposal(draft: ProposalDraft, proposals_dir: Path) -> Path:
    """Write ``draft`` to ``proposals_dir`` as a markdown file and return its path.

    The filename is ``<YYYY-MM-DD>-<topic>.md``. If that file exists, try
    ``-2.md``..``-99.md`` until one is free; if all 99 are taken, raise
    ``RuntimeError``. ``status`` in the rendered frontmatter is always
    ``pending``.
    """
    proposals_dir.mkdir(parents=True, exist_ok=True)

    base = f"{draft.created_at.date().isoformat()}-{draft.topic}"
    target = proposals_dir / f"{base}.md"
    if target.exists():
        target = None  # type: ignore[assignment]
        for suffix in range(2, _MAX_COLLISION_SUFFIX + 1):
            candidate = proposals_dir / f"{base}-{suffix}.md"
            if not candidate.exists():
                target = candidate
                break
        if target is None:
            raise RuntimeError(
                f"too many proposals with same topic on same date: "
                f"{base}.md and -2..-{_MAX_COLLISION_SUFFIX}.md all exist"
            )

    proposal_id = target.stem
    body = render_markdown(draft, proposal_id=proposal_id)
    target.write_text(body, encoding="utf-8", newline="\n")
    safe_emit_sync(
        Event(
            event_type=EventType.PROPOSAL_CREATED,
            agent=Agent.PROPOSER,
            payload={
                "proposal_id": proposal_id,
                "priority": draft.priority,
                "target_section": draft.target_section,
            },
        )
    )
    return target


def render_markdown(draft: ProposalDraft, *, proposal_id: str) -> str:
    """Return the markdown body for ``draft`` with ``proposal_id`` in frontmatter.

    Output ends with a single trailing newline. ``status`` is always
    ``pending``. The 8th section (變更紀錄) carries one ``- <ts> created
    by <author>`` line so the round-trip parser can recover authorship.
    """
    review_id_value = (
        draft.review_id if draft.review_id is not None else "null"
    )
    created_at_iso = draft.created_at.isoformat()

    frontmatter = "\n".join(
        [
            "---",
            f"proposal_id: {proposal_id}",
            f"target_section: {draft.target_section}",
            "status: pending",
            f"created_by: {draft.created_by}",
            f"created_at: {created_at_iso}",
            f"review_id: {review_id_value}",
            f"priority: {draft.priority}",
            "---",
        ]
    )

    section_blocks: list[str] = []
    for field_name, header in _SECTION_HEADERS:
        body_text = getattr(draft, field_name)
        section_blocks.append(f"{header}\n\n{body_text}\n")

    changelog_block = (
        f"{_CHANGELOG_HEADER}\n"
        "<!-- 自動填入,不要手動編輯 -->\n"
        f"- {created_at_iso} created by {draft.created_by}\n"
    )
    section_blocks.append(changelog_block)

    return frontmatter + "\n\n" + "\n".join(section_blocks)


def parse_proposal(path: Path) -> ProposalDraft:
    """Inverse of ``write_proposal`` — read markdown back into a ``ProposalDraft``.

    ``status`` is intentionally not part of ``ProposalDraft`` (writer
    invariant), so it's read but discarded. Missing frontmatter keys or
    body sections raise ``ProposalParseError`` with the offending field
    or section title in the message.
    """
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        raise ProposalParseError(
            f"missing or malformed YAML frontmatter in {path.name}"
        )

    raw_front, body = match.group(1), match.group(2)
    front = _parse_frontmatter(raw_front)

    required_keys = (
        "proposal_id",
        "target_section",
        "status",
        "created_by",
        "created_at",
        "review_id",
        "priority",
    )
    for key in required_keys:
        if key not in front:
            raise ProposalParseError(
                f"frontmatter missing required key: {key}"
            )

    sections = _split_sections(body)
    expected_titles = [header for _, header in _SECTION_HEADERS]
    expected_titles.append(_CHANGELOG_HEADER)
    for header in expected_titles:
        if header not in sections:
            short = header.split(". ", 1)[-1] if ". " in header else header
            raise ProposalParseError(
                f"missing section: {header} (field/title: {short})"
            )

    proposal_id = front["proposal_id"]
    topic = _topic_from_proposal_id(proposal_id)
    review_id_raw = front["review_id"]
    review_id: str | None = None if review_id_raw == "null" else review_id_raw

    try:
        created_at = datetime.fromisoformat(front["created_at"])
    except ValueError as exc:
        raise ProposalParseError(
            f"created_at is not ISO-8601: {front['created_at']!r}"
        ) from exc

    priority = front["priority"]
    if priority not in {"high", "medium", "low"}:
        raise ProposalParseError(
            f"priority must be high|medium|low, got {priority!r}"
        )

    return ProposalDraft(
        topic=topic,
        target_section=front["target_section"],
        created_by=front["created_by"],
        created_at=created_at,
        review_id=review_id,
        priority=priority,  # type: ignore[arg-type]
        description=sections[_SECTION_HEADERS[0][1]],
        motivation=sections[_SECTION_HEADERS[1][1]],
        diff_draft=sections[_SECTION_HEADERS[2][1]],
        expected_impact=sections[_SECTION_HEADERS[3][1]],
        risk_assessment=sections[_SECTION_HEADERS[4][1]],
        validation_plan=sections[_SECTION_HEADERS[5][1]],
        expected_improvement=sections[_SECTION_HEADERS[6][1]],
    )


def _parse_frontmatter(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        key, sep, value = stripped.partition(":")
        if sep != ":":
            continue
        out[key.strip()] = value.strip()
    return out


def _split_sections(body: str) -> dict[str, str]:
    """Split the body on ``## N. `` headers; return ``{header_line: text}``.

    Each value is the text between this header and the next, with leading
    blank lines and a single trailing newline trimmed.
    """
    starts = [m.start() for m in _SECTION_BREAK_RE.finditer(body)]
    out: dict[str, str] = {}
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(body)
        block = body[start:end]
        newline_at = block.find("\n")
        if newline_at == -1:
            header = block.rstrip()
            content = ""
        else:
            header = block[:newline_at].rstrip()
            content = block[newline_at + 1 :]
        out[header] = content.strip("\n")
    return out


def _topic_from_proposal_id(proposal_id: str) -> str:
    parts = proposal_id.split("-")
    if len(parts) < 4:
        raise ProposalParseError(
            f"proposal_id does not match YYYY-MM-DD-<topic>[-<n>] form: "
            f"{proposal_id!r}"
        )
    rest = parts[3:]
    if rest and rest[-1].isdigit():
        rest = rest[:-1]
    if not rest:
        raise ProposalParseError(
            f"proposal_id has no topic component: {proposal_id!r}"
        )
    return "-".join(rest)
