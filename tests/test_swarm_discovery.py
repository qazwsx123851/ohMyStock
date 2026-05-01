"""Tests for ohmystock.swarm.discover_available_tools / discover_available_skills.

Spec: openspec/changes/phase-2b-swarm-input-assembler/specs/swarm-input-assembler/spec.md
"""

from __future__ import annotations

from pathlib import Path

from ohmystock.swarm import discover_available_skills, discover_available_tools
from ohmystock.swarm._discovery import _read_name_field


def test_discover_tools_handles_missing_registry(monkeypatch) -> None:
    import sys

    sys.modules.pop("ohmystock.tools._registry", None)
    monkeypatch.setitem(sys.modules, "ohmystock.tools._registry", None)
    assert discover_available_tools() == []


def test_discover_tools_returns_sorted_unique(monkeypatch) -> None:
    import sys
    import types

    fake = types.ModuleType("ohmystock.tools._registry")
    fake.list_registered = lambda: [
        "pattern_recognition_tool",
        "market_data_tool",
        "chip_data_tool",
        "market_data_tool",  # duplicate
    ]
    monkeypatch.setitem(sys.modules, "ohmystock.tools._registry", fake)
    assert discover_available_tools() == [
        "chip_data_tool",
        "market_data_tool",
        "pattern_recognition_tool",
    ]


def test_discover_skills_empty_when_dir_missing(tmp_path: Path) -> None:
    assert discover_available_skills(tmp_path / "no_skills") == []


def test_discover_skills_empty_when_dir_has_no_yaml(tmp_path: Path) -> None:
    (tmp_path / "readme.md").write_text("# nope", encoding="utf-8")
    assert discover_available_skills(tmp_path) == []


def test_discover_skills_walks_subdirs_and_sorts(tmp_path: Path) -> None:
    (tmp_path / "technical").mkdir()
    (tmp_path / "chip").mkdir()
    (tmp_path / "technical" / "breakout.yaml").write_text(
        "name: technical/breakout\ndescription: x\n", encoding="utf-8"
    )
    (tmp_path / "chip" / "tmi.yaml").write_text(
        "name: chip/three-major-investors\n", encoding="utf-8"
    )
    assert discover_available_skills(tmp_path) == [
        "chip/three-major-investors",
        "technical/breakout",
    ]


def test_discover_skills_handles_frontmatter(tmp_path: Path) -> None:
    (tmp_path / "x.yaml").write_text(
        "---\nname: technical/vcp-pivot\nversion: 1\n---\nbody",
        encoding="utf-8",
    )
    assert discover_available_skills(tmp_path) == ["technical/vcp-pivot"]


def test_discover_skills_skips_files_without_name(tmp_path: Path) -> None:
    (tmp_path / "noname.yaml").write_text("description: missing name\n", encoding="utf-8")
    (tmp_path / "ok.yaml").write_text("name: chip/broker-branch\n", encoding="utf-8")
    assert discover_available_skills(tmp_path) == ["chip/broker-branch"]


def test_read_name_field_strips_quotes(tmp_path: Path) -> None:
    target = tmp_path / "q.yaml"
    target.write_text('name: "tw_specific/momentum-swing"\n', encoding="utf-8")
    assert _read_name_field(target) == "tw_specific/momentum-swing"


def test_read_name_field_handles_unreadable_file(tmp_path: Path) -> None:
    assert _read_name_field(tmp_path / "missing.yaml") is None
