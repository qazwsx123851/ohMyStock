"""CLI smoke tests — exercises typer.Typer app and pydantic-settings loader.

Spec: openspec/specs/cli-and-config/spec.md
- root help lists all 5 subcommands
- each stub exits 1 with "not implemented" in stdout
- Settings() constructible without any env present
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from ohmystock.cli import app
from ohmystock.config import Settings

runner = CliRunner()

SUBCOMMANDS = ["run", "backtest", "review", "propose", "screen"]


def test_root_help_lists_all_subcommands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in SUBCOMMANDS:
        assert cmd in result.output, f"subcommand {cmd!r} missing from --help output"


@pytest.mark.parametrize("subcommand", SUBCOMMANDS)
def test_subcommand_stub_returns_not_implemented(subcommand: str) -> None:
    result = runner.invoke(app, [subcommand])
    assert result.exit_code == 1
    assert "not implemented" in result.output


def test_settings_constructible_without_env() -> None:
    s = Settings()
    assert s.anthropic_api_key is None
    assert s.ohmystock_log_level == "INFO"
    assert s.ohmystock_db_path == "~/.ohmystock/journal.db"
