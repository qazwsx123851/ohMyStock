"""GET /api/admin/skills + GET /api/admin/skills/{name} — read-only registry view.

Surfaces the production skill registry (``src/ohmystock/skills/registry/``) so
the admin UI can browse and inspect skills without shell access.

* List endpoint returns every skill loaded by ``load_skills`` with ``body``
  truncated to 200 codepoints + a ``body_truncated`` flag.
* Detail endpoint returns one skill with the full ``body``. Validates ``name``
  against the same path-traversal token tuple the loader uses (defence in
  depth — the loader already validates, but we want ``invalid_input`` to fire
  before any disk I/O).

Path-safety token tuple is mirrored inline (see ``_INVALID_NAME_TOKENS_LOCAL``).
A test pins it equal to ``loader._INVALID_NAME_TOKENS`` so a future loader
change to add a token fails CI immediately.

Spec: openspec/changes/web-admin-skills-pages/specs/admin-skills-endpoints/spec.md
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

import ohmystock.skills as _skills_pkg
from ohmystock.api.auth import require_admin
from ohmystock.api.routes._envelope import (
    map_exception_to_envelope,
    to_error,
    to_success,
)
from ohmystock.skills import SkillSpec, load_skill, load_skills


# Resolved once at import time — production registry path. Tests override via
# ``monkeypatch.setattr(routes.skills, "_REGISTRY_DIR", tmp_path)``. Production
# code never reads the path from anywhere else (no Settings field, no env var).
_REGISTRY_DIR: Path = Path(_skills_pkg.__file__).resolve().parent / "registry"

# Mirrors ``ohmystock.skills.loader._INVALID_NAME_TOKENS``. A test in
# tests/api/test_skills_endpoint.py asserts equality so the two stay in sync.
_INVALID_NAME_TOKENS_LOCAL: tuple[str, ...] = ("/", "\\", "..", os.sep)

_BODY_PREVIEW_LIMIT = 200


router = APIRouter(dependencies=[Depends(require_admin)])


def _is_safe_name(name: str) -> bool:
    """True iff ``name`` contains none of the path-traversal tokens."""
    return not any(bad in name for bad in _INVALID_NAME_TOKENS_LOCAL)


def _to_list_item(spec: SkillSpec) -> dict[str, Any]:
    """Map a ``SkillSpec`` to the list-endpoint shape (preview body, plus flag)."""
    body = spec.body
    return {
        "name": spec.name,
        "description": spec.description,
        "category": spec.category,
        "body_preview": body[:_BODY_PREVIEW_LIMIT],
        "body_truncated": len(body) > _BODY_PREVIEW_LIMIT,
        "cited_specs": list(spec.cited_specs),
    }


def _to_detail(spec: SkillSpec) -> dict[str, Any]:
    """Map a ``SkillSpec`` to the detail-endpoint shape (full body)."""
    return {
        "name": spec.name,
        "description": spec.description,
        "category": spec.category,
        "body": spec.body,
        "cited_specs": list(spec.cited_specs),
    }


@router.get("/api/admin/skills")
def list_skills_endpoint() -> JSONResponse:
    try:
        specs = load_skills(_REGISTRY_DIR)
        items = [_to_list_item(s) for s in specs]
    except Exception as exc:  # noqa: BLE001 — never leak SkillLoadError text
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)

    return JSONResponse(status_code=200, content=to_success({"items": items}))


@router.get("/api/admin/skills/{name:path}")
def get_skill_endpoint(name: str) -> JSONResponse:
    if not _is_safe_name(name):
        return JSONResponse(
            status_code=400,
            content=to_error("invalid_input", "invalid skill name"),
        )

    try:
        spec = load_skill(_REGISTRY_DIR, name)
    except Exception as exc:  # noqa: BLE001
        status, body = map_exception_to_envelope(exc)
        return JSONResponse(status_code=status, content=body)

    if spec is None:
        return JSONResponse(
            status_code=404,
            content=to_error("not_found", f"skill not found: {name}"),
        )

    return JSONResponse(status_code=200, content=to_success(_to_detail(spec)))
