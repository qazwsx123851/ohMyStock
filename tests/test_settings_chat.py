"""Tests for the chat model Settings fields and validator.

Spec: openspec/changes/admin-chat-sessions-endpoints-and-pages/specs/cli-and-config/spec.md
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ohmystock.config import Settings


_CHAT_ENV_VARS = (
    "OHMYSTOCK_CHAT_MODEL_DEFAULT",
    "OHMYSTOCK_CHAT_TITLE_MODEL",
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent leakage from any developer .env / shell env into these tests."""
    for var in _CHAT_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_chat_defaults_match_spec() -> None:
    s = Settings()
    assert s.ohmystock_chat_model_default == "claude-sonnet-4-6"
    assert s.ohmystock_chat_title_model == "claude-haiku-4-5-20251001"


def test_env_override_chat_model_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OHMYSTOCK_CHAT_MODEL_DEFAULT", "claude-opus-4-7")
    s = Settings()
    assert s.ohmystock_chat_model_default == "claude-opus-4-7"


def test_env_override_chat_title_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OHMYSTOCK_CHAT_TITLE_MODEL", "claude-haiku-4-5")
    s = Settings()
    assert s.ohmystock_chat_title_model == "claude-haiku-4-5"


def test_empty_string_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OHMYSTOCK_CHAT_MODEL_DEFAULT", "")
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "ohmystock_chat_model_default" in str(exc_info.value)


def test_whitespace_only_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OHMYSTOCK_CHAT_TITLE_MODEL", "   ")
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "ohmystock_chat_title_model" in str(exc_info.value)
