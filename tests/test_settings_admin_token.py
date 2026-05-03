"""Tests for the web-admin-bearer-auth Settings field.

Spec: openspec/changes/web-admin-bearer-auth-v0/specs/web-admin-bearer-auth/spec.md
"""

from __future__ import annotations

import pytest

from ohmystock.config import Settings


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OHMYSTOCK_ADMIN_TOKEN", raising=False)


def test_admin_token_defaults_to_none_when_unset() -> None:
    s = Settings()
    assert s.ohmystock_admin_token is None


def test_admin_token_reads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "OHMYSTOCK_ADMIN_TOKEN", "abcdefghijklmnopqrstuvwxyz0123456"
    )
    s = Settings()
    assert s.ohmystock_admin_token == "abcdefghijklmnopqrstuvwxyz0123456"
    assert len(s.ohmystock_admin_token) == 33
