"""Tests for the ``ohmystock smoke-test`` subcommand.

Spec: openspec/changes/external-connectors-and-cost/specs/external-connectors/spec.md
"""

from __future__ import annotations

from typer.testing import CliRunner

from ohmystock.cli import app

runner = CliRunner()


def test_smoke_test_help_lists_three_checks() -> None:
    result = runner.invoke(app, ["smoke-test", "--help"])
    assert result.exit_code == 0
    output_lower = result.output.lower()
    assert "finmind" in output_lower
    assert "shioaji" in output_lower
    assert "anthropic" in output_lower
    assert "not implemented" not in result.output
