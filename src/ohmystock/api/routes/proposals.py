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

import ast
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ohmystock.api.auth import require_admin
from ohmystock.api.db import get_connection
from ohmystock.api.routes._envelope import (
    map_exception_to_envelope,
    to_error,
    to_success,
)
from ohmystock.config import Settings
from ohmystock.data.cache import select_bars
from ohmystock.data.sources.base import BarRow
from ohmystock.proposal import (
    ProposalParseError,
    ProposalStateError,
    ProposalStatus,
    parse_proposal,
    transition_proposal,
)
from ohmystock.validation import (
    WfaValidationError,
    run_validation,
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


# Test override seam for the validate endpoint's market data loader.
# Default builds the loader from ``get_connection() + select_bars`` so
# tests can ``monkeypatch.setattr(routes.proposals,
# "_MARKET_DATA_LOADER_FACTORY", lambda: synthetic_loader)`` and avoid
# touching the SQLite cache. Mirrors ``cli._validate_proposal``'s factory.
_MARKET_DATA_LOADER_FACTORY: Callable[
    [], Callable[[str, str, str], list[BarRow]]
] = lambda: (lambda sym, s, e: select_bars(get_connection(), sym, s, e))


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


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class PeriodModel(BaseModel):
    """``{from, to}`` ISO-date window, with ``from <= to`` enforced."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: str = Field(alias="from")
    to: str

    @field_validator("from_", "to")
    @classmethod
    def _iso_date(cls, value: str) -> str:
        if not _ISO_DATE_RE.match(value):
            raise ValueError(f"must match YYYY-MM-DD, got {value!r}")
        return value

    @model_validator(mode="after")
    def _check_order(self) -> "PeriodModel":
        if self.from_ > self.to:
            raise ValueError(
                f"period.from must be <= period.to ({self.from_} > {self.to})"
            )
        return self


class ValidateRequest(BaseModel):
    """JSON body for ``POST /api/admin/proposals/{slug}/validate``."""

    model_config = ConfigDict(extra="forbid")

    strategy: str
    period: PeriodModel
    param_overrides: list[str]
    universe: list[str] = Field(..., min_length=1)
    wfa_windows: int = Field(default=5, ge=2)
    in_sample_ratio: float = Field(default=0.7, gt=0.0, lt=1.0)
    initial_capital: int | None = None
    dry_run: bool = False


def _parse_param_pairs(pairs: list[str]) -> dict[str, Any]:
    """Parse ``["key=value", ...]`` into a dict via ``ast.literal_eval`` on values.

    Mirrors ``cli._validate_proposal._parse_param_pairs`` exactly. Not imported
    from the CLI module because that would couple two unrelated layers.
    """
    out: dict[str, Any] = {}
    for raw in pairs:
        if not raw:
            continue
        key, sep, value = raw.partition("=")
        if sep != "=" or not key.strip():
            raise ValueError(f"unparseable_param: {raw!r} (need key=value)")
        key_stripped = key.strip()
        value_stripped = value.strip()
        try:
            out[key_stripped] = ast.literal_eval(value_stripped)
        except (ValueError, SyntaxError) as exc:
            raise ValueError(
                f"unparseable_param: {key_stripped}={value_stripped} ({exc})"
            ) from exc
    return out


def _post_run_state_paths(
    slug: str,
    dry_run: bool,
) -> tuple[str | None, str | None]:
    """Compute ``(new_path, report_path)`` forward-slash strings post-run.

    Dry-run → ``(None, None)``. Otherwise the endpoint runs with
    ``auto_transition=False`` (manual-verdict mode, spec
    proposal-manual-verdict): the markdown never moves, so ``new_path`` is
    always ``None`` and the report sits at the proposals root as
    ``<slug>.validation.json``.
    """
    if dry_run:
        return None, None
    return None, f"{slug}.validation.json"


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


@router.get("/api/admin/proposals/{slug:path}/validate")
def reject_get_on_validate(slug: str) -> JSONResponse:
    """Return 405 explicitly for GET on the validate path.

    Same rationale as ``reject_get_on_transition``: the catch-all detail
    route would otherwise swallow the slug.
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


# Registered AFTER ``transition`` so the catch-all ``{slug:path}`` detail
# route never swallows ``<slug>/validate`` requests.
@router.post("/api/admin/proposals/{slug:path}/validate")
def validate_proposal_endpoint(
    slug: str, body: ValidateRequest = Body(...)
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

        try:
            param_overrides_dict = _parse_param_pairs(body.param_overrides)
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content=to_error("invalid_input", str(exc)),
            )

        initial_capital = (
            body.initial_capital
            if body.initial_capital is not None
            else Settings().starting_equity_twd
        )

        market_data_loader = _MARKET_DATA_LOADER_FACTORY()

        try:
            report = run_validation(
                path,
                strategy_name=body.strategy,
                period={"from": body.period.from_, "to": body.period.to},
                param_overrides=param_overrides_dict,
                universe=body.universe,
                wfa_windows=body.wfa_windows,
                in_sample_ratio=body.in_sample_ratio,
                initial_capital=initial_capital,
                market_data_loader=market_data_loader,
                dry_run=body.dry_run,
                auto_transition=False,
            )
        except WfaValidationError as exc:
            msg = str(exc)
            if msg.startswith("status_not_validating"):
                return JSONResponse(
                    status_code=409,
                    content=to_error("illegal_transition", msg),
                )
            return JSONResponse(
                status_code=422,
                content=to_error("wfa_validation_failed", msg),
            )
        except ProposalStateError as state_exc:
            http_status, envelope = _map_state_error(state_exc)
            return JSONResponse(status_code=http_status, content=envelope)

        new_path_str, report_path_str = _post_run_state_paths(slug, body.dry_run)

        # Manual-verdict mode: the proposal always stays in ``validating``;
        # the operator approves/rejects via the transition endpoint after
        # reviewing the report.
        new_status: Literal["validating"] = "validating"

        return JSONResponse(
            status_code=200,
            content=to_success(
                {
                    "verdict": report.verdict,
                    "slug": slug,
                    "new_status": new_status,
                    "new_path": new_path_str,
                    "report_path": report_path_str,
                    "deltas": report.deltas,
                    "failures": list(report.failures),
                }
            ),
        )
    except Exception as exc:  # noqa: BLE001 — generic mapper redacts message
        http_status, envelope = map_exception_to_envelope(exc)
        return JSONResponse(status_code=http_status, content=envelope)
