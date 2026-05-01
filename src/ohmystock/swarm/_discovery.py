"""Tool / skill discovery helpers.

The swarm input assembler advertises ``available_tools`` and
``available_skills`` to the LLM nodes. Both come from sources that exist
elsewhere in the codebase (or will). These helpers read whatever is
currently registered and return sorted name lists; absence is not an
error — an empty list is a valid result.

Spec: openspec/changes/phase-2b-swarm-input-assembler/specs/swarm-input-assembler/spec.md
"""

from __future__ import annotations

import re
from pathlib import Path


_DEFAULT_SKILLS_ROOT = Path(__file__).resolve().parents[1] / "skills"
_NAME_LINE = re.compile(r"^\s*name\s*:\s*(?P<value>\S.*?)\s*$")


def discover_available_tools() -> list[str]:
    """Return sorted names of registered tools.

    Reads ``ohmystock.tools._registry.list_registered()`` if present.
    Falls back to an empty list when the registry module hasn't been
    written yet — the swarm input assembler treats missing tools as
    "no tools advertised", not an error.
    """
    try:
        from ohmystock.tools import _registry  # noqa: WPS433
    except ImportError:
        return []

    list_fn = getattr(_registry, "list_registered", None)
    if list_fn is None:
        return []

    names = list_fn()
    return sorted({str(n) for n in names})


def discover_available_skills(root: Path | str | None = None) -> list[str]:
    """Return sorted skill identifiers found under ``src/ohmystock/skills/``.

    Each ``*.yaml`` file is parsed for a ``name: <id>`` line (YAML
    frontmatter or top-level scalar). Files without a ``name`` field are
    skipped silently. Returns an empty list when no skills exist yet.
    """
    skill_root = Path(root) if root is not None else _DEFAULT_SKILLS_ROOT
    if not skill_root.exists() or not skill_root.is_dir():
        return []

    names: set[str] = set()
    for yaml_path in skill_root.rglob("*.yaml"):
        if not yaml_path.is_file():
            continue
        name = _read_name_field(yaml_path)
        if name:
            names.add(name)

    return sorted(names)


def _read_name_field(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    in_frontmatter = False
    for line_idx, raw in enumerate(text.splitlines()):
        stripped = raw.strip()
        if line_idx == 0 and stripped == "---":
            in_frontmatter = True
            continue
        if in_frontmatter and stripped == "---":
            break
        match = _NAME_LINE.match(raw)
        if match:
            value = match.group("value")
            return value.strip().strip("\"'")
    return None
