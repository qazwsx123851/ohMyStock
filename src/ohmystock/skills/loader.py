"""Filesystem loader for skill markdown files.

Skill files are ``<skills_dir>/<name>.md`` with a YAML frontmatter block
fenced by ``---`` on its own line, followed by an arbitrary Markdown
body. The loader is fail-loud: any malformed file raises
:class:`SkillLoadError`. See
``openspec/changes/skill-registry-foundation/specs/skill-registry/spec.md``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ohmystock.skills.spec import SKILL_CATEGORIES, SkillSpec


class SkillLoadError(Exception):
    """Raised when a skill file cannot be parsed into a ``SkillSpec``."""

    def __init__(self, path: Path | str, reason: str) -> None:
        super().__init__(f"{path}: {reason}")
        self.path = Path(path) if not isinstance(path, Path) else path
        self.reason = reason


_REQUIRED_FRONTMATTER_KEYS: frozenset[str] = frozenset(
    {"name", "description", "category", "cited_specs"}
)


def _parse_frontmatter(text: str, path: Path) -> tuple[dict[str, Any], str]:
    """Split ``text`` into (frontmatter dict, body string)."""

    lines = text.splitlines(keepends=False)
    if not lines or lines[0].strip() != "---":
        raise SkillLoadError(path, "missing frontmatter delimiter on line 1")

    closing_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            closing_idx = i
            break
    if closing_idx is None:
        raise SkillLoadError(path, "missing closing frontmatter delimiter")

    frontmatter_yaml = "\n".join(lines[1:closing_idx])
    body_lines = lines[closing_idx + 1 :]
    # Strip a single leading blank line so a `---\n# Title` body and a
    # `---\n\n# Title` body produce the same body text.
    if body_lines and body_lines[0] == "":
        body_lines = body_lines[1:]
    body = "\n".join(body_lines)

    try:
        loaded = yaml.safe_load(frontmatter_yaml) or {}
    except yaml.YAMLError as exc:
        raise SkillLoadError(path, f"YAML parse error: {exc}") from exc
    if not isinstance(loaded, dict):
        raise SkillLoadError(
            path, f"frontmatter must be a YAML mapping, got {type(loaded).__name__}"
        )

    return loaded, body


def _to_skill_spec(
    frontmatter: dict[str, Any], body: str, path: Path
) -> SkillSpec:
    """Turn a parsed frontmatter dict + body into a ``SkillSpec``."""

    keys = set(frontmatter.keys())
    missing = _REQUIRED_FRONTMATTER_KEYS - keys
    if missing:
        raise SkillLoadError(
            path, f"missing required frontmatter keys: {sorted(missing)}"
        )
    extra = keys - _REQUIRED_FRONTMATTER_KEYS
    if extra:
        raise SkillLoadError(
            path, f"unknown frontmatter keys: {sorted(extra)}"
        )

    name = frontmatter.get("name")
    if name != path.stem:
        raise SkillLoadError(
            path,
            f"frontmatter name {name!r} does not match filename stem "
            f"{path.stem!r}",
        )

    category = frontmatter.get("category")
    if category not in SKILL_CATEGORIES:
        raise SkillLoadError(
            path,
            f"category {category!r} not in allowed values "
            f"{list(SKILL_CATEGORIES)} (note: 'indicator' singular, "
            f"not 'indicators')",
        )

    try:
        return SkillSpec(
            name=name,
            description=frontmatter["description"],
            category=category,
            body=body,
            cited_specs=frontmatter["cited_specs"],
        )
    except ValidationError as exc:
        raise SkillLoadError(path, f"schema error: {exc}") from exc


_INVALID_NAME_TOKENS: tuple[str, ...] = ("/", "\\", "..", os.sep)


def _validate_name(name: str, path_hint: Path) -> None:
    for bad in _INVALID_NAME_TOKENS:
        if bad in name:
            raise SkillLoadError(path_hint, "invalid skill name")


def load_skill(skills_dir: Path, name: str) -> SkillSpec | None:
    """Load a single skill by ``name``; return ``None`` if absent.

    ``name`` MUST be a kebab-case identifier without path separators.
    Names containing ``/``, ``\\``, ``..``, or ``os.sep`` raise
    :class:`SkillLoadError` BEFORE any filesystem access.
    """

    _validate_name(name, skills_dir / f"{name}.md")
    path = skills_dir / f"{name}.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    frontmatter, body = _parse_frontmatter(text, path)
    return _to_skill_spec(frontmatter, body, path)


def load_skills(skills_dir: Path) -> list[SkillSpec]:
    """Load every ``*.md`` skill file under ``skills_dir`` (non-recursive).

    Skips directories, non-``.md`` suffixes, and filenames starting with
    ``_``. Fails fast on the first parse error encountered.
    """

    if not skills_dir.exists() or not skills_dir.is_dir():
        return []

    collected: list[SkillSpec] = []
    for entry in sorted(skills_dir.iterdir(), key=lambda p: p.name):
        if entry.is_dir():
            continue
        if entry.suffix != ".md":
            continue
        if entry.name.startswith("_"):
            continue

        text = entry.read_text(encoding="utf-8")
        frontmatter, body = _parse_frontmatter(text, entry)
        collected.append(_to_skill_spec(frontmatter, body, entry))

    collected.sort(key=lambda s: s.name)
    return collected
