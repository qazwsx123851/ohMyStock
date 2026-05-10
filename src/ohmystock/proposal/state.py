"""Proposal state machine — transition_proposal API.

Spec: openspec/changes/proposal-state-machine/specs/proposal-state-machine/spec.md
SSOT: proposals/README.md §2 (5-state workflow) + cheatsheet §16

State graph (5 legal edges only)::

    pending ──▶ validating ──▶ approved ──▶ merged
                    │              │
                    └──▶ rejected ◀┘

Required keyword args by ``new_status``:

* ``approved`` — ``validation_report_path: Path``
* ``merged``   — ``merged_to_version: str``
* ``rejected`` — ``reason: str`` (non-empty)
* ``validating`` — none beyond ``actor``

Filesystem side-effects: ``approved`` moves the file into ``PENDING_REVIEW/``,
``merged`` into ``merged/``, ``rejected`` into ``rejected/``. ``pending`` /
``validating`` stay in the proposals root. The proposals root is reverse-
inferred from the input path's parent: if the parent is ``PENDING_REVIEW`` /
``merged`` / ``rejected`` the root is ``parent.parent``, otherwise it is
``parent``.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal, get_args


ProposalStatus = Literal["pending", "validating", "approved", "merged", "rejected"]


_LEGAL_TRANSITIONS: frozenset[tuple[ProposalStatus, ProposalStatus]] = frozenset(
    {
        ("pending", "validating"),
        ("validating", "approved"),
        ("validating", "rejected"),
        ("approved", "merged"),
        ("approved", "rejected"),
    }
)


_SINK_DIR: dict[ProposalStatus, str | None] = {
    "pending": None,
    "validating": None,
    "approved": "PENDING_REVIEW",
    "merged": "merged",
    "rejected": "rejected",
}

_SINK_DIR_NAMES = frozenset({"PENDING_REVIEW", "merged", "rejected"})

_CHANGELOG_HEADER = "## 8. 變更紀錄"


class ProposalStateError(RuntimeError):
    """Raised when ``transition_proposal`` cannot perform the requested change.

    First-line message uses a short token (``unknown_status`` /
    ``illegal_transition`` / ``missing_actor`` / ``missing_validation_report`` /
    ``missing_merged_to_version`` / ``missing_rejection_reason`` /
    ``destination_exists`` / ``malformed_frontmatter`` / ``malformed_changelog``)
    so callers and tests can match on the token without depending on the
    free-text suffix.
    """


def transition_proposal(
    path: Path,
    new_status: str,
    *,
    actor: str,
    reason: str | None = None,
    validation_report_path: Path | None = None,
    merged_to_version: str | None = None,
) -> Path:
    """Transition a proposal markdown to ``new_status``, returning the new path.

    Reads the current ``status`` from the frontmatter (never inferred from the
    directory). Validates the transition against the 5 legal edges, checks
    required kwargs for the target status, then atomically writes the updated
    file (moving it into the appropriate sink subdirectory) and unlinks the old
    location if it differs.
    """
    _validate_actor(actor)
    _validate_new_status(new_status)
    new_status_lit: ProposalStatus = new_status  # type: ignore[assignment]

    frontmatter, body = _read_proposal(path)

    current_status_raw = frontmatter.get("status")
    if current_status_raw not in get_args(ProposalStatus):
        raise ProposalStateError(
            f"unknown_status: frontmatter status {current_status_raw!r} is not "
            f"one of {get_args(ProposalStatus)}"
        )
    current_status: ProposalStatus = current_status_raw  # type: ignore[assignment]

    _validate_transition(current_status, new_status_lit)
    _validate_required_args(
        new_status_lit,
        reason=reason,
        validation_report_path=validation_report_path,
        merged_to_version=merged_to_version,
    )

    proposals_root = _resolve_proposals_root(path)
    new_path = _resolve_new_path(proposals_root, path.name, new_status_lit)

    if new_path != path and new_path.exists():
        raise ProposalStateError(
            f"destination_exists: target path {new_path} already exists; "
            "manual cleanup required before re-running transition"
        )

    now_iso = datetime.now().astimezone().isoformat(timespec="seconds")

    new_frontmatter = _mutate_frontmatter(
        frontmatter,
        new_status_lit,
        reason=reason,
        validation_report_path=validation_report_path,
        merged_to_version=merged_to_version,
        now_iso=now_iso,
    )
    new_body = _append_changelog(
        body,
        old_status=current_status,
        new_status=new_status_lit,
        actor=actor,
        reason=reason,
        now_iso=now_iso,
    )
    content = _serialize(new_frontmatter, new_body)

    _atomic_write(content, new_path)
    if path != new_path:
        path.unlink()
    return new_path


def _validate_actor(actor: str) -> None:
    if not actor:
        raise ProposalStateError("missing_actor: actor must be a non-empty string")


def _validate_new_status(new_status: str) -> None:
    if new_status not in get_args(ProposalStatus):
        raise ProposalStateError(
            f"unknown_status: {new_status!r} is not one of {get_args(ProposalStatus)}"
        )


def _validate_transition(
    current: ProposalStatus, new: ProposalStatus
) -> None:
    if (current, new) not in _LEGAL_TRANSITIONS:
        raise ProposalStateError(
            f"illegal_transition: {current} -> {new} is not one of "
            f"{sorted(_LEGAL_TRANSITIONS)}"
        )


def _validate_required_args(
    new_status: ProposalStatus,
    *,
    reason: str | None,
    validation_report_path: Path | None,
    merged_to_version: str | None,
) -> None:
    if new_status == "approved" and validation_report_path is None:
        raise ProposalStateError(
            "missing_validation_report: validation_report_path is required "
            "when transitioning to approved"
        )
    if new_status == "merged" and not merged_to_version:
        raise ProposalStateError(
            "missing_merged_to_version: merged_to_version is required when "
            "transitioning to merged"
        )
    if new_status == "rejected" and not reason:
        raise ProposalStateError(
            "missing_rejection_reason: non-empty reason is required when "
            "transitioning to rejected"
        )


def _read_proposal(path: Path) -> tuple[dict[str, str], str]:
    """Parse ``path`` into ``(frontmatter_dict, body_str)``.

    Uses the same line-based ``key: value`` format the writer emits — keys
    preserve insertion order via ``dict``. Missing or malformed ``---``
    fences raise ``ProposalStateError("malformed_frontmatter")``.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise ProposalStateError(
            f"malformed_frontmatter: {path.name} does not start with '---'"
        )

    end_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        raise ProposalStateError(
            f"malformed_frontmatter: {path.name} missing closing '---' fence"
        )

    fm: dict[str, str] = {}
    for line in lines[1:end_idx]:
        stripped = line.strip()
        if not stripped:
            continue
        key, sep, value = stripped.partition(":")
        if sep != ":":
            continue
        fm[key.strip()] = value.strip()

    body = "\n".join(lines[end_idx + 1 :])
    if body.startswith("\n"):
        body = body[1:]
    return fm, body


def _resolve_proposals_root(path: Path) -> Path:
    parent = path.parent
    if parent.name in _SINK_DIR_NAMES:
        return parent.parent
    return parent


def _resolve_new_path(
    root: Path, filename: str, new_status: ProposalStatus
) -> Path:
    sink = _SINK_DIR[new_status]
    if sink is None:
        return root / filename
    return root / sink / filename


def _mutate_frontmatter(
    fm: dict[str, str],
    new_status: ProposalStatus,
    *,
    reason: str | None,
    validation_report_path: Path | None,
    merged_to_version: str | None,
    now_iso: str,
) -> dict[str, str]:
    """Return a new dict: original keys (in order, with status updated)
    followed by any newly-introduced metadata keys appended at the end.
    """
    out: dict[str, str] = {}
    for key, value in fm.items():
        if key == "status":
            out[key] = new_status
        else:
            out[key] = value

    if new_status == "approved" and validation_report_path is not None:
        out["validation_report_path"] = str(validation_report_path)
    if new_status == "merged":
        if merged_to_version is not None:
            out["merged_to_version"] = merged_to_version
        out["merged_at"] = now_iso
    if new_status == "rejected" and reason:
        out["rejected_reason"] = reason

    return out


def _append_changelog(
    body: str,
    *,
    old_status: ProposalStatus,
    new_status: ProposalStatus,
    actor: str,
    reason: str | None,
    now_iso: str,
) -> str:
    if _CHANGELOG_HEADER not in body:
        raise ProposalStateError(
            f"malformed_changelog: body is missing '{_CHANGELOG_HEADER}' heading"
        )

    line = f"- {now_iso} status: {old_status} → {new_status} by {actor}"
    if reason:
        line += f" ({reason})"

    return body.rstrip("\n") + "\n" + line + "\n"


def _serialize(fm: dict[str, str], body: str) -> str:
    """Re-emit the markdown with line-based ``key: value`` frontmatter,
    matching the writer's byte format so diffs stay minimal.
    """
    lines = ["---"]
    for key, value in fm.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    front = "\n".join(lines)
    return front + "\n\n" + body


def _atomic_write(content: str, new_path: Path) -> None:
    """Write ``content`` to ``new_path`` atomically.

    Strategy: ``NamedTemporaryFile`` in the destination directory, fsync,
    close, then ``os.replace``. On any error, unlink the tmp file and
    re-raise the original exception.
    """
    new_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=new_path.parent,
            delete=False,
            suffix=".md.tmp",
            mode="w",
            encoding="utf-8",
            newline="\n",
        ) as tmp:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, new_path)
        tmp_path = None
    finally:
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
