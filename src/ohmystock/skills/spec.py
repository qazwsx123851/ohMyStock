"""Frozen ``SkillSpec`` model + canonical category enum.

Spec: openspec/changes/skill-registry-foundation/specs/skill-registry/spec.md
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


SKILL_CATEGORIES: tuple[str, ...] = (
    "data",
    "indicator",
    "signal",
    "decider",
    "gate",
    "tool",
    "report",
)


SkillCategory = Literal[
    "data",
    "indicator",
    "signal",
    "decider",
    "gate",
    "tool",
    "report",
]


class SkillSpec(BaseModel):
    """Read-only representation of a single skill on disk.

    Loaded from ``<skills_dir>/<name>.md`` whose first segment is YAML
    frontmatter. ``body`` is the raw Markdown text after the closing
    ``---`` (loader does not render it).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    description: str
    category: SkillCategory
    body: str
    cited_specs: list[str]
