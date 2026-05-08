"""Skill registry — filesystem-driven Markdown skill cards.

Spec: openspec/changes/skill-registry-foundation/specs/skill-registry/spec.md
"""

from ohmystock.skills.loader import (
    SkillLoadError,
    load_skill,
    load_skills,
)
from ohmystock.skills.spec import SkillSpec


__all__ = [
    "SkillSpec",
    "load_skills",
    "load_skill",
    "SkillLoadError",
]
