"""Tests for ``ohmystock.skills.loader``.

Spec: openspec/changes/skill-registry-foundation/specs/skill-registry/spec.md
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ohmystock.skills import (
    SkillLoadError,
    SkillSpec,
    load_skill,
    load_skills,
)


_VALID = """\
---
name: market-data
description: 取得 daily bars
category: data
cited_specs:
  - market-data-cache
---
# Purpose
demo body
"""


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_module_exports_are_exactly_four() -> None:
    import ohmystock.skills as s

    assert set(s.__all__) == {
        "SkillSpec",
        "load_skills",
        "load_skill",
        "SkillLoadError",
    }
    assert s.SkillSpec is SkillSpec
    assert s.SkillLoadError is SkillLoadError


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_load_skill_happy_path(tmp_path: Path) -> None:
    _write(tmp_path / "market-data.md", _VALID)

    spec = load_skill(tmp_path, "market-data")

    assert isinstance(spec, SkillSpec)
    assert spec.name == "market-data"
    assert spec.category == "data"
    assert spec.cited_specs == ["market-data-cache"]
    assert spec.body.startswith("# Purpose")
    assert "demo body" in spec.body


def test_load_skill_returns_none_when_missing(tmp_path: Path) -> None:
    assert load_skill(tmp_path, "does-not-exist") is None


def test_body_can_be_empty(tmp_path: Path) -> None:
    _write(
        tmp_path / "ok.md",
        "---\nname: ok\ndescription: x\ncategory: data\ncited_specs: []\n---\n",
    )
    spec = load_skill(tmp_path, "ok")
    assert spec is not None
    assert spec.body == ""


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


def test_missing_frontmatter_delimiter(tmp_path: Path) -> None:
    _write(tmp_path / "bad.md", "no leading dashes here\n")
    with pytest.raises(SkillLoadError, match="missing frontmatter"):
        load_skill(tmp_path, "bad")


def test_missing_closing_delimiter(tmp_path: Path) -> None:
    _write(tmp_path / "bad.md", "---\nname: bad\ndescription: x\n")
    with pytest.raises(SkillLoadError, match="missing closing frontmatter"):
        load_skill(tmp_path, "bad")


def test_malformed_yaml(tmp_path: Path) -> None:
    _write(tmp_path / "bad.md", "---\nname: [unterminated\n---\n")
    with pytest.raises(SkillLoadError, match="YAML parse error"):
        load_skill(tmp_path, "bad")


def test_name_mismatch(tmp_path: Path) -> None:
    _write(
        tmp_path / "market-data.md",
        "---\nname: foo-bar\ndescription: x\ncategory: data\ncited_specs: []\n---\n",
    )
    with pytest.raises(SkillLoadError) as exc:
        load_skill(tmp_path, "market-data")
    msg = str(exc.value)
    assert "market-data" in msg
    assert "foo-bar" in msg


def test_bad_category(tmp_path: Path) -> None:
    _write(
        tmp_path / "market-data.md",
        "---\nname: market-data\ndescription: x\ncategory: indicators\ncited_specs: []\n---\n",
    )
    with pytest.raises(SkillLoadError) as exc:
        load_skill(tmp_path, "market-data")
    msg = str(exc.value)
    assert "indicators" in msg
    assert "indicator" in msg


def test_unknown_frontmatter_key(tmp_path: Path) -> None:
    _write(
        tmp_path / "market-data.md",
        "---\nname: market-data\ndescription: x\ncategory: data\ncited_specs: []\nextra: boom\n---\n",
    )
    with pytest.raises(SkillLoadError, match="unknown frontmatter keys"):
        load_skill(tmp_path, "market-data")


def test_missing_required_key(tmp_path: Path) -> None:
    _write(
        tmp_path / "market-data.md",
        "---\nname: market-data\ndescription: x\ncategory: data\n---\n",
    )
    with pytest.raises(SkillLoadError, match="missing required frontmatter keys"):
        load_skill(tmp_path, "market-data")


# ---------------------------------------------------------------------------
# Path traversal defence
# ---------------------------------------------------------------------------


def test_path_traversal_rejected(tmp_path: Path) -> None:
    with pytest.raises(SkillLoadError, match="invalid skill name"):
        load_skill(tmp_path, "../../../etc/passwd")


def test_forward_slash_rejected(tmp_path: Path) -> None:
    with pytest.raises(SkillLoadError, match="invalid skill name"):
        load_skill(tmp_path, "foo/bar")


def test_backslash_rejected(tmp_path: Path) -> None:
    with pytest.raises(SkillLoadError, match="invalid skill name"):
        load_skill(tmp_path, "foo\\bar")


# ---------------------------------------------------------------------------
# load_skills (directory walk)
# ---------------------------------------------------------------------------


def test_empty_dir_returns_empty_list(tmp_path: Path) -> None:
    assert load_skills(tmp_path) == []


def test_nonexistent_dir_returns_empty_list(tmp_path: Path) -> None:
    assert load_skills(tmp_path / "does-not-exist") == []


def test_skips_underscore_files(tmp_path: Path) -> None:
    _write(tmp_path / "market-data.md", _VALID)
    _write(
        tmp_path / "_template.md",
        "---\nname: _template\ndescription: x\ncategory: data\ncited_specs: []\n---\n",
    )
    out = load_skills(tmp_path)
    assert [s.name for s in out] == ["market-data"]


def test_skips_subdirs_and_non_md(tmp_path: Path) -> None:
    (tmp_path / "subdir").mkdir()
    _write(tmp_path / "ignored.txt", "---\nname: ignored\n---\n")
    _write(tmp_path / "market-data.md", _VALID)
    out = load_skills(tmp_path)
    assert [s.name for s in out] == ["market-data"]


def test_sort_stable_alphabetical(tmp_path: Path) -> None:
    for n in ("zebra", "apple", "mango"):
        _write(
            tmp_path / f"{n}.md",
            f"---\nname: {n}\ndescription: x\ncategory: data\ncited_specs: []\n---\n",
        )
    out = load_skills(tmp_path)
    assert [s.name for s in out] == ["apple", "mango", "zebra"]


def test_load_skills_fails_fast_on_bad_file(tmp_path: Path) -> None:
    _write(
        tmp_path / "good.md",
        "---\nname: good\ndescription: x\ncategory: data\ncited_specs: []\n---\n",
    )
    _write(tmp_path / "bad.md", "no frontmatter here")

    with pytest.raises(SkillLoadError) as exc:
        load_skills(tmp_path)
    assert "bad.md" in str(exc.value)


# ---------------------------------------------------------------------------
# SkillSpec immutability
# ---------------------------------------------------------------------------


def test_skill_spec_is_frozen() -> None:
    s = SkillSpec(
        name="x",
        description="y",
        category="data",
        body="",
        cited_specs=[],
    )
    with pytest.raises(ValidationError):
        s.name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Real corpus smoke test
# ---------------------------------------------------------------------------


def test_real_registry_loads_at_least_ten_skills() -> None:
    here = Path(__file__).resolve().parent.parent
    registry = here / "src" / "ohmystock" / "skills" / "registry"

    out = load_skills(registry)

    assert len(out) >= 10
    names = [s.name for s in out]
    assert len(names) == len(set(names)), f"duplicate names: {names}"
    for spec in out:
        assert spec.cited_specs, f"{spec.name} has empty cited_specs"
