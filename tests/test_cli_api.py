"""CLI smoke test for `ohmystock api --help`.

Verifies the api command exposes --host, --port, --reload/--no-reload
flags and is NOT in stub state (must not echo "not implemented").
--help short-circuits before uvicorn.run, so no socket bind happens.

Spec: openspec/changes/fastapi-bootstrap/specs/cli-and-config/spec.md
"""

from __future__ import annotations

from typer.testing import CliRunner

from ohmystock.cli import app

runner = CliRunner()


def test_api_help_lists_flags() -> None:
    result = runner.invoke(app, ["api", "--help"])
    assert result.exit_code == 0
    assert "--host" in result.output
    assert "--port" in result.output
    assert "--reload" in result.output or "--no-reload" in result.output
    assert "not implemented" not in result.output
