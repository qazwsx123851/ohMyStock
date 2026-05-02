"""CLI smoke tests — exercises typer.Typer app and pydantic-settings loader.

Spec: openspec/specs/cli-and-config/spec.md
- root help lists all 8 subcommands (5 stubs + api + smoke-test + score)
- each stub exits 1 with "not implemented" in stdout (api / smoke-test /
  score excluded — they are non-stub and would actually launch external work)
- Settings() constructible without any env present
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from ohmystock.cli import app
from ohmystock.config import Settings

runner = CliRunner()

STUB_SUBCOMMANDS = ["run", "backtest", "review", "propose", "screen"]
ALL_SUBCOMMANDS = [*STUB_SUBCOMMANDS, "api", "smoke-test", "score"]


def test_root_help_lists_all_subcommands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ALL_SUBCOMMANDS:
        assert cmd in result.output, f"subcommand {cmd!r} missing from --help output"


@pytest.mark.parametrize("subcommand", STUB_SUBCOMMANDS)
def test_subcommand_stub_returns_not_implemented(subcommand: str) -> None:
    result = runner.invoke(app, [subcommand])
    assert result.exit_code == 1
    assert "not implemented" in result.output


def test_settings_constructible_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    env_keys = [
        "ANTHROPIC_API_KEY",
        "SHIOAJI_API_KEY",
        "SHIOAJI_SECRET_KEY",
        "SHIOAJI_CA_PATH",
        "SHIOAJI_CA_PASSWD",
        "SHIOAJI_PERSON_ID",
        "FINMIND_TOKEN",
        "OHMYSTOCK_AUTO_EXECUTE",
        "OHMYSTOCK_LLM_DEGRADE",
        "OHMYSTOCK_DB_PATH",
        "OHMYSTOCK_LOG_LEVEL",
    ]
    for key in env_keys:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("OHMYSTOCK_DECIDER_MODEL", raising=False)
    monkeypatch.delenv("OHMYSTOCK_ALLOW_FAKE_DECIDER", raising=False)
    monkeypatch.delenv("OHMYSTOCK_CONFIRM_TIMEOUT_MINUTES", raising=False)
    monkeypatch.delenv("OHMYSTOCK_DEFAULT_CAPITAL_TWD", raising=False)
    s = Settings(_env_file=None)
    assert s.anthropic_api_key is None
    assert s.ohmystock_log_level == "INFO"
    assert s.ohmystock_db_path == "~/.ohmystock/journal.db"
    assert s.ohmystock_decider_model == "claude-opus-4-7"
    assert s.ohmystock_allow_fake_decider is False
    assert s.ohmystock_confirm_timeout_minutes == 30
    assert s.ohmystock_default_capital_twd == 1_000_000


def test_settings_decider_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OHMYSTOCK_DECIDER_MODEL", "claude-sonnet-4-6")
    monkeypatch.delenv("OHMYSTOCK_ALLOW_FAKE_DECIDER", raising=False)
    s = Settings(_env_file=None)
    assert s.ohmystock_decider_model == "claude-sonnet-4-6"
    assert s.ohmystock_allow_fake_decider is False


def test_settings_allow_fake_decider_truthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OHMYSTOCK_ALLOW_FAKE_DECIDER", "true")
    s = Settings(_env_file=None)
    assert s.ohmystock_allow_fake_decider is True


def test_settings_confirm_timeout_minutes_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OHMYSTOCK_CONFIRM_TIMEOUT_MINUTES", "60")
    s = Settings(_env_file=None)
    assert s.ohmystock_confirm_timeout_minutes == 60


def test_settings_default_capital_twd_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OHMYSTOCK_DEFAULT_CAPITAL_TWD", "2500000")
    s = Settings(_env_file=None)
    assert s.ohmystock_default_capital_twd == 2_500_000


def test_settings_confirm_timeout_zero_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import ValidationError

    monkeypatch.setenv("OHMYSTOCK_CONFIRM_TIMEOUT_MINUTES", "0")
    with pytest.raises(ValidationError, match="ohmystock_confirm_timeout_minutes"):
        Settings(_env_file=None)


def test_settings_confirm_timeout_negative_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import ValidationError

    monkeypatch.setenv("OHMYSTOCK_CONFIRM_TIMEOUT_MINUTES", "-5")
    with pytest.raises(ValidationError, match="ohmystock_confirm_timeout_minutes"):
        Settings(_env_file=None)


def test_settings_default_capital_negative_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import ValidationError

    monkeypatch.setenv("OHMYSTOCK_DEFAULT_CAPITAL_TWD", "-1")
    with pytest.raises(ValidationError, match="ohmystock_default_capital_twd"):
        Settings(_env_file=None)
