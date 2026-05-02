"""Tests for the Phase 3.5 auto-execute settings fields and validator.

Spec: openspec/changes/auto-execute-toggle-and-breakers/specs/auto-execute/spec.md
"""

from __future__ import annotations

import pytest

from ohmystock.config import Settings


_AUTO_EXECUTE_ENV_VARS = (
    "OHMYSTOCK_BROKER",
    "OHMYSTOCK_AUTO_EXECUTE",
    "OHMYSTOCK_AUTO_EXECUTE_DAILY_LIMIT",
    "OHMYSTOCK_AUTO_EXECUTE_MIN_CONFIDENCE",
    "OHMYSTOCK_AUTO_EXECUTE_MAX_NOTIONAL_PCT",
    "OHMYSTOCK_AUTO_EXECUTE_MAX_SIZING_DEVIATION",
    "OHMYSTOCK_AUTO_EXECUTE_LOSS_LOCKOUT_HOURS",
    "OHMYSTOCK_AUTO_EXECUTE_LOSS_PCT_THRESHOLD",
    "OHMYSTOCK_AUTO_EXECUTE_ACCOUNT_EQUITY_TWD",
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent leakage from any developer .env / shell env into these tests."""
    for var in _AUTO_EXECUTE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_defaults_match_cheatsheet_section_6_7() -> None:
    s = Settings()
    assert s.ohmystock_broker == "shioaji-sim"
    assert s.ohmystock_auto_execute is False
    assert s.ohmystock_auto_execute_daily_limit == 5
    assert s.ohmystock_auto_execute_min_confidence == 0.7
    assert s.ohmystock_auto_execute_max_notional_pct == 0.25
    assert s.ohmystock_auto_execute_max_sizing_deviation == 0.30
    assert s.ohmystock_auto_execute_loss_lockout_hours == 24
    assert s.ohmystock_auto_execute_loss_pct_threshold == -0.05
    assert s.ohmystock_auto_execute_account_equity_twd == 1_000_000


def test_sim_mode_with_auto_execute_true_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OHMYSTOCK_BROKER", "shioaji-sim")
    monkeypatch.setenv("OHMYSTOCK_AUTO_EXECUTE", "true")
    s = Settings()
    assert s.ohmystock_broker == "shioaji-sim"
    assert s.ohmystock_auto_execute is True


def test_mock_mode_with_auto_execute_true_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OHMYSTOCK_BROKER", "mock")
    monkeypatch.setenv("OHMYSTOCK_AUTO_EXECUTE", "true")
    s = Settings()
    assert s.ohmystock_auto_execute is True


def test_live_mode_with_auto_execute_true_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OHMYSTOCK_BROKER", "shioaji-live")
    monkeypatch.setenv("OHMYSTOCK_AUTO_EXECUTE", "true")
    with pytest.raises(RuntimeError) as exc_info:
        Settings()
    msg = str(exc_info.value)
    assert "shioaji-live" in msg
    assert "OHMYSTOCK_AUTO_EXECUTE" in msg


def test_live_mode_with_auto_execute_false_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OHMYSTOCK_BROKER", "shioaji-live")
    monkeypatch.setenv("OHMYSTOCK_AUTO_EXECUTE", "false")
    s = Settings()
    assert s.ohmystock_broker == "shioaji-live"
    assert s.ohmystock_auto_execute is False


def test_env_override_round_trips_for_all_numeric_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OHMYSTOCK_AUTO_EXECUTE", "true")
    monkeypatch.setenv("OHMYSTOCK_AUTO_EXECUTE_DAILY_LIMIT", "3")
    monkeypatch.setenv("OHMYSTOCK_AUTO_EXECUTE_MIN_CONFIDENCE", "0.85")
    monkeypatch.setenv("OHMYSTOCK_AUTO_EXECUTE_MAX_NOTIONAL_PCT", "0.10")
    monkeypatch.setenv("OHMYSTOCK_AUTO_EXECUTE_MAX_SIZING_DEVIATION", "0.20")
    monkeypatch.setenv("OHMYSTOCK_AUTO_EXECUTE_LOSS_LOCKOUT_HOURS", "12")
    monkeypatch.setenv("OHMYSTOCK_AUTO_EXECUTE_LOSS_PCT_THRESHOLD", "-0.03")
    monkeypatch.setenv("OHMYSTOCK_AUTO_EXECUTE_ACCOUNT_EQUITY_TWD", "500000")
    s = Settings()
    assert s.ohmystock_auto_execute is True
    assert s.ohmystock_auto_execute_daily_limit == 3
    assert s.ohmystock_auto_execute_min_confidence == 0.85
    assert s.ohmystock_auto_execute_max_notional_pct == 0.10
    assert s.ohmystock_auto_execute_max_sizing_deviation == 0.20
    assert s.ohmystock_auto_execute_loss_lockout_hours == 12
    assert s.ohmystock_auto_execute_loss_pct_threshold == -0.03
    assert s.ohmystock_auto_execute_account_equity_twd == 500_000


def test_invalid_broker_value_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OHMYSTOCK_BROKER", "ig-mt5")
    with pytest.raises(Exception):
        Settings()


@pytest.mark.parametrize(
    "field_env,bad_value",
    [
        ("OHMYSTOCK_AUTO_EXECUTE_DAILY_LIMIT", "0"),
        ("OHMYSTOCK_AUTO_EXECUTE_DAILY_LIMIT", "-1"),
        ("OHMYSTOCK_AUTO_EXECUTE_LOSS_LOCKOUT_HOURS", "0"),
        ("OHMYSTOCK_AUTO_EXECUTE_ACCOUNT_EQUITY_TWD", "0"),
    ],
)
def test_non_positive_int_fields_rejected(
    monkeypatch: pytest.MonkeyPatch, field_env: str, bad_value: str
) -> None:
    monkeypatch.setenv(field_env, bad_value)
    with pytest.raises(Exception):
        Settings()
