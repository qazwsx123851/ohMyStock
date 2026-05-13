"""GET /api/admin/reviews — read-only view over reviews/<review_id>/.

Two endpoints:

* ``GET /api/admin/reviews`` — paginated summary list sourced from
  ``<reviews_root>/_index.json``. The filesystem is NOT walked here;
  the pipeline maintains ``_index.json`` atomically (see
  ``openspec/specs/post-trade-review-pipeline/spec.md`` requirement
  "reviews/_index.json 以 atomic rename 維護") so the index is the
  single source of truth.
* ``GET /api/admin/reviews/{review_id}`` — composite payload combining
  the ``_index.json`` row (when present) with on-disk file probes,
  the full ``report.md`` text, parsed ``proposals_created.md`` link
  rows, and the ``metrics.overall`` slice from ``metrics.json``.

Half-finished reviews (pipeline crashed mid-run) are a first-class
case: the detail endpoint returns 200 with ``partial: true`` so the
admin UI can still surface what landed. The 404 path requires BOTH
the directory and the index row to be absent.

Path-safety token tuple is mirrored from ``routes/proposals.py`` and
applied BEFORE any disk I/O. The ``_REVIEWS_ROOT_FACTORY`` indirection
is the testing seam (same pattern as proposals).

Spec: openspec/changes/admin-reviews-endpoints-and-pages/specs/admin-reviews-endpoints/spec.md
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from ohmystock.api.auth import require_admin
from ohmystock.api.routes._envelope import (
    map_exception_to_envelope,
    to_error,
    to_success,
)
from ohmystock.config import Settings


logger = logging.getLogger(__name__)


# Test-override seam (mirrors ``routes/proposals.py``). Production reads
# ``Settings().reviews_dir`` per request; tests monkeypatch this to a tmp_path.
_REVIEWS_ROOT_FACTORY: Callable[[], Path] = lambda: Settings().reviews_dir


# Path-traversal token tuple — kept structurally identical to
# ``routes/proposals._INVALID_NAME_TOKENS`` so the invariant test in
# ``tests/api/routes/test_reviews_endpoint.py`` can assert set-equality.
_INVALID_NAME_TOKENS: tuple[str, ...] = ("/", "\\", "..", os.sep)

_ALLOWED_KINDS: tuple[str, ...] = ("monthly", "quarterly", "forced", "manual")

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200

_INDEX_FILENAME = "_index.json"
_CORRUPTED_INDEX_MESSAGE = "reviews index is corrupted"

# 6 standard files emitted by post-trade-review-pipeline (reviews/README.md §4).
_STANDARD_FILES: tuple[tuple[str, str], ...] = (
    ("data_json", "data.json"),
    ("attribution_json", "attribution.json"),
    ("metrics_json", "metrics.json"),
    ("critique_md", "critique.md"),
    ("report_md", "report.md"),
    ("proposals_created_md", "proposals_created.md"),
)

# Keys lifted from metrics.json's ``overall`` block for the detail endpoint
# (post-trade-review-rubric §3 specifies these as the canonical overall set).
_METRICS_OVERALL_KEYS: tuple[str, ...] = (
    "win_rate",
    "profit_factor",
    "expectancy_pct",
    "max_drawdown_pct",
    "max_consecutive_loss",
    "avg_hold_days",
)

# Empty-proposals sentinel emitted by the proposer node when no critique
# severity warranted a proposal (pipeline spec scenario "0 警示產出 0 提案").
_EMPTY_PROPOSALS_SENTINEL = "本期無提案"

# Markdown link to a proposal: ``[<topic>](../../proposals/<slug>.md)``.
_PROPOSAL_LINK_RE = re.compile(
    r"\[(?P<topic>[^\]]+)\]\(\.\./\.\./proposals/(?P<slug>[^)]+?)\.md\)"
)


class ReviewIndexCorrupted(RuntimeError):
    """``_index.json`` exists but is not valid JSON."""


# ---------------------------------------------------------------------------
# Helpers — all pure (or scoped to a single Path); no FastAPI types here so
# the unit tests can exercise them without a TestClient.
# ---------------------------------------------------------------------------


def _is_safe_review_id(review_id: str) -> bool:
    """True iff ``review_id`` contains none of the path-traversal tokens."""
    return not any(token in review_id for token in _INVALID_NAME_TOKENS)


def _load_index(reviews_root: Path) -> list[dict[str, Any]]:
    """Read ``<root>/_index.json`` and return its ``reviews[]`` array.

    Missing file → empty list. Invalid JSON → ``ReviewIndexCorrupted`` so
    the handler can emit the fixed-message 500 envelope without leaking
    the underlying ``JSONDecodeError`` text. A well-formed file whose
    ``reviews`` key is missing or not a list → empty list (defensive).
    """
    index_path = reviews_root / _INDEX_FILENAME
    try:
        raw = index_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError as exc:
        logger.warning("failed to read %s: %s", index_path, exc)
        raise ReviewIndexCorrupted(_CORRUPTED_INDEX_MESSAGE) from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReviewIndexCorrupted(_CORRUPTED_INDEX_MESSAGE) from exc

    reviews = parsed.get("reviews") if isinstance(parsed, dict) else None
    if not isinstance(reviews, list):
        return []
    return [row for row in reviews if isinstance(row, dict)]


def _sort_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort by ``(completed_at DESC, review_id DESC)``, stable for ties."""
    return sorted(
        rows,
        key=lambda r: (r.get("completed_at") or "", r.get("review_id") or ""),
        reverse=True,
    )


def _find_index_row(
    rows: list[dict[str, Any]], review_id: str
) -> dict[str, Any] | None:
    """Return the first row whose ``review_id`` matches, else ``None``."""
    for row in rows:
        if row.get("review_id") == review_id:
            return row
    return None


def _probe_files(review_dir: Path, review_id: str) -> dict[str, dict[str, Any]]:
    """Probe the 6 standard files; return ``{key: {exists, path}}``.

    ``path`` strings use forward slashes regardless of host OS to keep
    the wire format stable for the React client.
    """
    out: dict[str, dict[str, Any]] = {}
    for key, filename in _STANDARD_FILES:
        candidate = review_dir / filename
        if candidate.is_file():
            out[key] = {"exists": True, "path": f"{review_id}/{filename}"}
        else:
            out[key] = {"exists": False, "path": None}
    return out


def _read_report(review_dir: Path) -> str | None:
    """Return the full text of ``report.md`` or ``None`` if absent / unreadable."""
    candidate = review_dir / "report.md"
    try:
        return candidate.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.warning("failed to read %s: %s", candidate, exc)
        return None


def _extract_metrics_overall(review_dir: Path) -> dict[str, Any] | None:
    """Lift the ``overall`` block from ``metrics.json`` (6 fixed keys).

    Missing file → ``None``. Malformed JSON or missing ``overall`` key →
    zero-filled dict so the UI can still render KPI cards. Per-key
    fallback to 0 keeps the response shape stable for the React types.
    """
    candidate = review_dir / "metrics.json"
    try:
        raw = candidate.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.warning("failed to read %s: %s", candidate, exc)
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("metrics.json is not valid JSON: %s", candidate)
        return {key: 0 for key in _METRICS_OVERALL_KEYS}

    overall = parsed.get("overall") if isinstance(parsed, dict) else None
    if not isinstance(overall, dict):
        return {key: 0 for key in _METRICS_OVERALL_KEYS}

    return {key: overall.get(key, 0) for key in _METRICS_OVERALL_KEYS}


def _parse_proposals_created(review_dir: Path) -> list[dict[str, str]]:
    """Parse ``proposals_created.md`` into ``[{slug, status, priority, target}]``.

    Tolerant by design: any parse anomaly (missing file, missing table,
    malformed row) returns ``[]`` with a structured warning. The sentinel
    "本期無提案" short-circuits to ``[]`` without warning.
    """
    candidate = review_dir / "proposals_created.md"
    try:
        text = candidate.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError as exc:
        logger.warning("failed to read %s: %s", candidate, exc)
        return []

    if _EMPTY_PROPOSALS_SENTINEL in text:
        return []

    rows: list[dict[str, str]] = []
    has_any_pipe_row = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        has_any_pipe_row = True
        if stripped.startswith("|---") or "Proposal" in stripped:
            continue

        link_match = _PROPOSAL_LINK_RE.search(stripped)
        if link_match is None:
            continue

        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 4:
            continue

        rows.append(
            {
                "slug": link_match.group("slug"),
                "status": cells[1],
                "priority": cells[2],
                "target": cells[3],
            }
        )

    if has_any_pipe_row and not rows:
        logger.warning("could not parse proposals_created.md: %s", candidate)

    return rows


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/api/admin/reviews")
def list_reviews_endpoint(
    kind: str | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_LIMIT),
    offset: int = Query(default=0),
) -> JSONResponse:
    """Paginated list of reviews, sourced from ``<root>/_index.json``."""
    if offset < 0:
        return JSONResponse(
            status_code=400,
            content=to_error("invalid_input", f"offset must be >= 0, got {offset}"),
        )
    if limit < 1:
        return JSONResponse(
            status_code=400,
            content=to_error("invalid_input", f"limit must be >= 1, got {limit}"),
        )
    if kind is not None and kind not in _ALLOWED_KINDS:
        return JSONResponse(
            status_code=400,
            content=to_error(
                "invalid_input",
                f"kind must be one of {list(_ALLOWED_KINDS)}, got {kind!r}",
            ),
        )

    clamped_limit = min(limit, _MAX_LIMIT)

    try:
        rows = _load_index(_REVIEWS_ROOT_FACTORY())
    except ReviewIndexCorrupted:
        return JSONResponse(
            status_code=500,
            content=to_error("internal_error", _CORRUPTED_INDEX_MESSAGE),
        )
    except Exception as exc:  # noqa: BLE001 — generic mapper redacts message
        http_status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=http_status, content=body)

    if kind is not None:
        rows = [r for r in rows if r.get("kind") == kind]

    rows = _sort_summaries(rows)

    total = len(rows)
    page = rows[offset : offset + clamped_limit]
    has_more = (offset + len(page)) < total

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


@router.get("/api/admin/reviews/{review_id}")
def get_review_endpoint(review_id: str) -> JSONResponse:
    """Composite payload: index row + file probes + report + metrics + proposals."""
    if not _is_safe_review_id(review_id):
        return JSONResponse(
            status_code=400,
            content=to_error("invalid_input", "review_id contains forbidden token"),
        )

    try:
        root = _REVIEWS_ROOT_FACTORY()
        try:
            index_rows = _load_index(root)
        except ReviewIndexCorrupted:
            return JSONResponse(
                status_code=500,
                content=to_error("internal_error", _CORRUPTED_INDEX_MESSAGE),
            )

        summary = _find_index_row(index_rows, review_id)
        review_dir = root / review_id
        dir_exists = review_dir.is_dir()

        if summary is None and not dir_exists:
            return JSONResponse(
                status_code=404,
                content=to_error("not_found", f"review not found: {review_id}"),
            )

        if dir_exists:
            files = _probe_files(review_dir, review_id)
            report = (
                _read_report(review_dir) if files["report_md"]["exists"] else None
            )
            metrics_overall = (
                _extract_metrics_overall(review_dir)
                if files["metrics_json"]["exists"]
                else None
            )
            proposals_created = (
                _parse_proposals_created(review_dir)
                if files["proposals_created_md"]["exists"]
                else []
            )
        else:
            # Index row exists but directory has been removed by hand — a
            # degenerate ``partial`` case; all files absent.
            files = {key: {"exists": False, "path": None} for key, _ in _STANDARD_FILES}
            report = None
            metrics_overall = None
            proposals_created = []

        partial = summary is None or any(
            not entry["exists"] for entry in files.values()
        )

        data = {
            "review_id": review_id,
            "partial": partial,
            "summary": summary,
            "files": files,
            "report": report,
            "metrics_overall": metrics_overall,
            "proposals_created": proposals_created,
        }
        return JSONResponse(status_code=200, content=to_success(data))
    except Exception as exc:  # noqa: BLE001
        http_status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=http_status, content=body)
