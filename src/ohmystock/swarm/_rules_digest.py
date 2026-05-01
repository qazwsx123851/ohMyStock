"""Cheatsheet rules digest loader.

Reads ``docs/_rules_digest.json`` (curated SSOT for §6.3 must-have and §6.4
bonus items) into a ``RulesDigest`` Pydantic model.

Spec: openspec/changes/phase-2b-swarm-input-assembler/specs/swarm-input-assembler/spec.md
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from ohmystock.swarm._errors import RulesDigestError
from ohmystock.swarm.models import RulesDigest


_DEFAULT_PATH = Path(__file__).resolve().parents[3] / "docs" / "_rules_digest.json"


def load_rules_digest(path: Path | str | None = None) -> RulesDigest:
    """Load and validate the rules digest from disk.

    Raises ``RulesDigestError`` if the file is missing, not valid JSON,
    or violates the (3 must_have, 8 bonus_items) count invariants.
    """
    target = Path(path) if path is not None else _DEFAULT_PATH

    try:
        raw = target.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RulesDigestError(f"rules digest file not found: {target}") from exc
    except OSError as exc:
        raise RulesDigestError(f"cannot read rules digest at {target}: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RulesDigestError(f"rules digest at {target} is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise RulesDigestError(
            f"rules digest at {target} must be a JSON object, got {type(data).__name__}"
        )

    try:
        return RulesDigest.model_validate(data)
    except ValidationError as exc:
        raise RulesDigestError(f"rules digest at {target} failed validation: {exc}") from exc
