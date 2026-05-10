"""GET/POST /api/admin/proposals — read + transition proposal markdown.

Three endpoints:

* ``GET /api/admin/proposals`` — paginated list, frontmatter-only summaries
  walking ``<root>/`` + ``<root>/PENDING_REVIEW/`` + ``<root>/merged/`` +
  ``<root>/rejected/`` (in that order). Optional ``?status=`` filter applied
  in-memory after parsing (frontmatter is source-of-truth, not directory).
* ``GET /api/admin/proposals/{slug}`` — full body via ``parse_proposal`` +
  parsed ``## 8.`` changelog + raw frontmatter ``extra_frontmatter`` keys
  (``validation_report_path`` / ``merged_to_version`` / ``merged_at`` /
  ``rejected_reason``).
* ``POST /api/admin/proposals/{slug}/transition`` — thin wrapper around
  ``transition_proposal`` with ``ProposalStateError`` → envelope mapping.

Path-safety token tuple is mirrored locally (``_INVALID_NAME_TOKENS``)
and applied BEFORE any disk I/O — same defence-in-depth pattern as
``routes/skills.py``.

The ``_PROPOSALS_ROOT_FACTORY`` indirection is the testing seam: tests
override it via ``monkeypatch.setattr(routes.proposals,
"_PROPOSALS_ROOT_FACTORY", lambda: tmp_path / "proposals")`` so each
request sees the right scope.

Spec: openspec/changes/admin-proposals-endpoints-and-pages/specs/admin-proposals-endpoints/spec.md
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from ohmystock.api.auth import require_admin
from ohmystock.api.routes._envelope import (
    map_exception_to_envelope,
    to_error,
    to_success,
)
from ohmystock.config import Settings
from ohmystock.proposal import (
    ProposalParseError,
    ProposalStateError,
    ProposalStatus,
    parse_proposal,
    transition_proposal,
)


logger = logging.getLogger(__name__)


# Test-override pattern (mirrors ``routes/skills.py``):
#
#     monkeypatch.setattr(
#         ohmystock.api.routes.proposals,
#         "_PROPOSALS_ROOT_FACTORY",
#         lambda: tmp_path / "proposals",
#     )
#
# Production reads ``Settings().proposals_dir`` per request so .env reloads
# (or test scopes) take effect without restarting the app.
_PROPOSALS_ROOT_FACTORY: Callable[[], Path] = lambda: Settings().proposals_dir


_INVALID_NAME_TOKENS: tuple[str, ...] = ("/", "\\", "..", os.sep)
_VALID_STATUSES: tuple[ProposalStatus, ...] = (
    "pending",
    "validating",
    "approved",
    "merged",
    "rejected",
)
_SINK_DIR_NAMES: tuple[str, ...] = ("PENDING_REVIEW", "merged", "rejected")
_OPTIONAL_FRONTMATTER_KEYS: tuple[str, ...] = (
    "validation_report_path",
    "merged_to_version",
    "merged_at",
    "rejected_reason",
)
_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200


# ProposalStateError substring → (HTTP, envelope code) mapping (design D10).
# Order matters: scanned in declared order; first substring hit wins.
_STATE_ERROR_TO_ENVELOPE: list[tuple[str, int, str]] = [
    ("unknown_status", 400, "invalid_input"),
    ("illegal_transition", 409, "illegal_transition"),
    ("missing_actor", 400, "invalid_input"),
    ("missing_validation_report", 400, "invalid_input"),
    ("missing_merged_to_version", 400, "invalid_input"),
    ("missing_rejection_reason", 400, "invalid_input"),
    ("destination_exists", 409, "conflict"),
    ("malformed_changelog", 422, "unprocessable_entity"),
]


# Regex helpers ---------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_SECTION_BREAK_RE = re.compile(r"^## \d+\. ", re.MULTILINE)
_TRANSITION_LINE_RE = re.compile(
    r"^- (?P<ts>\S+) status: (?P<from>\w+) (?:->|→) (?P<to>\w+) by "
    r"(?P<actor>.+?)(?: \((?P<reason>.*)\))?$"
)
_CREATED_LINE_RE = re.compile(r"^- (?P<ts>\S+) created by (?P<actor>.+)$")
_HTML_COMMENT_RE = re.compile(r"^<!--.*-->$")


# Helpers ---------------------------------------------------------------------


def _is_safe_slug(slug: str) -> bool:
    """True iff ``slug`` contains none of the path-traversal tokens."""
    return not any(bad in slug for bad in _INVALID_NAME_TOKENS)


def _read_frontmatter(path: Path) -> dict[str, str] | None:
    """Read the YAML-ish ``key: value`` frontmatter into a dict.

    Returns ``None`` (with a structured warning) on any malformed input
    instead of raising — the list endpoint wants a tolerant pass.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("skipping malformed proposal: %s (%s)", path, exc)
        return None

    match = _FRONTMATTER_RE.match(text)
    if match is None:
        logger.warning("skipping malformed proposal: %s", path)
        return None

    raw_front = match.group(1)
    out: dict[str, str] = {}
    for line in raw_front.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        key, sep, value = stripped.partition(":")
        if sep != ":":
            continue
        out[key.strip()] = value.strip()

    return out


def _parse_changelog(section_text: str) -> list[dict[str, Any]]:
    """Parse the ``## 8.`` body section into a list of changelog entries.

    Skips blank lines and HTML comments. Each line maps to one of three
    discriminated-union shapes (``transition`` / ``created`` / ``raw``).
    """
    entries: list[dict[str, Any]] = []
    for raw_line in section_text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if _HTML_COMMENT_RE.match(line.strip()):
            continue

        m = _TRANSITION_LINE_RE.match(line)
        if m is not None:
            entries.append(
                {
                    "kind": "transition",
                    "timestamp": m.group("ts"),
                    "from_status": m.group("from"),
                    "to_status": m.group("to"),
                    "actor": m.group("actor"),
                    "reason": m.group("reason"),
                }
            )
            continue

        m = _CREATED_LINE_RE.match(line)
        if m is not None:
            entries.append(
                {
                    "kind": "created",
                    "timestamp": m.group("ts"),
                    "actor": m.group("actor"),
                }
            )
            continue

        entries.append({"kind": "raw", "text": line})

    return entries


def _resolve_slug_to_path(root: Path, slug: str) -> Path | None:
    """Probe the 4 sub-locations for ``<slug>.md``; return first match or None."""
    filename = f"{slug}.md"
    candidates = [
        root / filename,
        root / "PENDING_REVIEW" / filename,
        root / "merged" / filename,
        root / "rejected" / filename,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _topic_from_proposal_id(proposal_id: str) -> str:
    """Strip the leading ``YYYY-MM-DD-`` prefix to recover the topic.

    Falls back to the full ``proposal_id`` if the prefix isn't present.
    """
    parts = proposal_id.split("-", 3)
    if len(parts) >= 4:
        return parts[3]
    return proposal_id


def _summary_from_frontmatter(slug: str, fm: dict[str, str]) -> dict[str, Any]:
    """Build the ``ProposalSummary`` shape from a parsed frontmatter dict.

    ``review_id == "null"`` is normalised to ``None``. Missing required keys
    yield empty strings — the caller is responsible for upstream filtering.
    """
    proposal_id = fm.get("proposal_id", slug)
    review_raw = fm.get("review_id", "null")
    review_id = None if review_raw == "null" else review_raw

    return {
        "slug": slug,
        "proposal_id": proposal_id,
        "status": fm.get("status", ""),
        "topic": _topic_from_proposal_id(proposal_id),
        "target_section": fm.get("target_section", ""),
        "created_by": fm.get("created_by", ""),
        "created_at": fm.get("created_at", ""),
        "review_id": review_id,
        "priority": fm.get("priority", ""),
    }


def _walk_proposal_files(root: Path) -> list[Path]:
    """Walk the 4 sub-locations and return the deduped ``.md`` file list.

    Files at root whose stem matches one of the 3 sub-dir names are skipped
    so a stray ``proposals/PENDING_REVIEW.md`` cannot collide with the
    sub-directory itself.
    """
    files: list[Path] = []
    if not root.is_dir():
        return files

    sink_set = set(_SINK_DIR_NAMES)
    for entry in sorted(root.iterdir()):
        if entry.is_file() and entry.suffix == ".md":
            if entry.stem in sink_set:
                continue
            files.append(entry)

    for sink in _SINK_DIR_NAMES:
        sink_dir = root / sink
        if not sink_dir.is_dir():
            continue
        for entry in sorted(sink_dir.iterdir()):
            if entry.is_file() and entry.suffix == ".md":
                files.append(entry)

    return files


def _map_state_error(exc: ProposalStateError) -> tuple[int, dict[str, Any]]:
    """Map a ``ProposalStateError`` to ``(http_status, envelope)``.

    Scans ``_STATE_ERROR_TO_ENVELOPE`` in declared order; falls back to
    the generic envelope mapper for messages that don't match any row.
    """
    message = str(exc)
    for substring, status, code in _STATE_ERROR_TO_ENVELOPE:
        if substring in message:
            return status, to_error(code, message)
    return map_exception_to_envelope(exc)


def _split_body_sections(body: str) -> dict[str, str]:
    """Split the markdown body on ``## N. `` headers; return ``{header: text}``."""
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


def _extract_changelog_text(path: Path) -> str:
    """Read the ``## 8. 變更紀錄`` section verbatim from ``path``.

    Returns the empty string if the section header is missing.
    """
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    body = match.group(2) if match is not None else text
    sections = _split_body_sections(body)
    return sections.get("## 8. 變更紀錄", "")


# Pydantic body model ---------------------------------------------------------


class TransitionRequest(BaseModel):
    """JSON body for ``POST /api/admin/proposals/{slug}/transition``."""

    model_config = ConfigDict(extra="forbid")

    new_status: Literal["pending", "validating", "approved", "merged", "rejected"]
    actor: str
    reason: str | None = None
    validation_report_path: str | None = None
    merged_to_version: str | None = None


# Router ----------------------------------------------------------------------


router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/api/admin/proposals")
def list_proposals_endpoint(
    status: str | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_LIMIT),
    offset: int = Query(default=0),
) -> JSONResponse:
    if status is not None and status not in _VALID_STATUSES:
        return JSONResponse(
            status_code=400,
            content=to_error(
                "invalid_input",
                f"status must be one of {list(_VALID_STATUSES)}, got {status!r}",
            ),
        )
    if offset < 0:
        return JSONResponse(
            status_code=400,
            content=to_error("invalid_input", f"offset must be >= 0, got {offset}"),
        )

    clamped_limit = min(max(limit, 0), _MAX_LIMIT)

    try:
        root = _PROPOSALS_ROOT_FACTORY()
        summaries: list[dict[str, Any]] = []
        for path in _walk_proposal_files(root):
            fm = _read_frontmatter(path)
            if fm is None:
                continue
            slug = path.stem
            summary = _summary_from_frontmatter(slug, fm)
            if status is not None and summary["status"] != status:
                continue
            summaries.append(summary)

        summaries.sort(
            key=lambda s: (s.get("created_at") or "", s.get("slug") or ""),
            reverse=True,
        )

        total = len(summaries)
        page = (
            summaries[offset : offset + clamped_limit] if clamped_limit > 0 else []
        )
        has_more = offset + len(page) < total

        return JSONResponse(
            status_code=200,
            content=to_success(
                {
                    "items": page,
                    "total": total,
                    "limit": clamped_limit,
                    "offset": offset,
                    "has_more": has_more,
                }
            ),
        )
    except Exception as exc:  # noqa: BLE001 — generic mapper redacts message
        http_status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=http_status, content=body)


@router.get("/api/admin/proposals/{slug:path}/transition")
def reject_get_on_transition(slug: str) -> JSONResponse:
    """Return 405 explicitly for GET on the transition path.

    Without this handler the catch-all detail route (``{slug:path}``) would
    swallow the request and reject it as ``invalid_input`` (slug contains
    ``/``). The spec requires a clean 405 instead.
    """
    return JSONResponse(
        status_code=405,
        content={"detail": "Method Not Allowed"},
        headers={"Allow": "POST"},
    )


@router.get("/api/admin/proposals/{slug:path}")
def get_proposal_endpoint(slug: str) -> JSONResponse:
    if not _is_safe_slug(slug):
        return JSONResponse(
            status_code=400,
            content=to_error("invalid_input", "invalid proposal slug"),
        )

    try:
        root = _PROPOSALS_ROOT_FACTORY()
        path = _resolve_slug_to_path(root, slug)
        if path is None:
            return JSONResponse(
                status_code=404,
                content=to_error("not_found", f"proposal not found: {slug}"),
            )

        fm = _read_frontmatter(path)
        if fm is None:
            return JSONResponse(
                status_code=422,
                content=to_error(
                    "malformed_proposal",
                    f"proposal markdown is malformed: {slug}.md frontmatter",
                ),
            )

        try:
            draft = parse_proposal(path)
        except ProposalParseError as parse_exc:
            return JSONResponse(
                status_code=422,
                content=to_error(
                    "malformed_proposal",
                    f"proposal markdown is malformed: {parse_exc}",
                ),
            )

        changelog_text = _extract_changelog_text(path)
        changelog = _parse_changelog(changelog_text)

        extra_frontmatter = {
            key: fm[key] for key in _OPTIONAL_FRONTMATTER_KEYS if key in fm
        }

        summary = _summary_from_frontmatter(slug, fm)
        data = {
            **summary,
            "body": {
                "description": draft.description,
                "motivation": draft.motivation,
                "diff_draft": draft.diff_draft,
                "expected_impact": draft.expected_impact,
                "risk_assessment": draft.risk_assessment,
                "validation_plan": draft.validation_plan,
                "expected_improvement": draft.expected_improvement,
            },
            "changelog": changelog,
            "extra_frontmatter": extra_frontmatter,
        }

        return JSONResponse(status_code=200, content=to_success(data))
    except Exception as exc:  # noqa: BLE001
        http_status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=http_status, content=body)


@router.post("/api/admin/proposals/{slug:path}/transition")
def transition_proposal_endpoint(
    slug: str, body: TransitionRequest = Body(...)
) -> JSONResponse:
    if not _is_safe_slug(slug):
        return JSONResponse(
            status_code=400,
            content=to_error("invalid_input", "invalid proposal slug"),
        )

    try:
        root = _PROPOSALS_ROOT_FACTORY()
        path = _resolve_slug_to_path(root, slug)
        if path is None:
            return JSONResponse(
                status_code=404,
                content=to_error("not_found", f"proposal not found: {slug}"),
            )

        validation_path = (
            Path(body.validation_report_path)
            if body.validation_report_path
            else None
        )

        try:
            new_path = transition_proposal(
                path,
                body.new_status,
                actor=body.actor,
                reason=body.reason,
                validation_report_path=validation_path,
                merged_to_version=body.merged_to_version,
            )
        except ProposalStateError as state_exc:
            http_status, envelope = _map_state_error(state_exc)
            return JSONResponse(status_code=http_status, content=envelope)
        except ProposalParseError as parse_exc:
            return JSONResponse(
                status_code=422,
                content=to_error(
                    "malformed_proposal",
                    f"proposal markdown is malformed: {parse_exc}",
                ),
            )

        new_path_relative = new_path.relative_to(root).as_posix()
        return JSONResponse(
            status_code=200,
            content=to_success(
                {
                    "slug": slug,
                    "new_status": body.new_status,
                    "new_path": new_path_relative,
                }
            ),
        )
    except Exception as exc:  # noqa: BLE001
        http_status, envelope = map_exception_to_envelope(exc)
        return JSONResponse(status_code=http_status, content=envelope)
