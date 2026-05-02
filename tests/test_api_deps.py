"""Unit tests for ``ohmystock.api.routes._deps`` lifecycle.

Verifies that ``get_db`` yields a fresh ``sqlite3.Connection`` per call
and closes it after both success and raise paths. Spec scenarios under
"每個請求自開自關 sqlite3 connection".
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ohmystock.api.db import _get_settings
from ohmystock.api.routes._deps import get_db, get_settings_dep
from ohmystock.config import Settings


@pytest.fixture()
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "deps.db"
    monkeypatch.setenv("OHMYSTOCK_DB_PATH", str(db_path))
    _get_settings.cache_clear()
    yield db_path
    _get_settings.cache_clear()


def _drain(gen) -> sqlite3.Connection:
    return next(gen)


def _close_gen(gen) -> None:
    with pytest.raises(StopIteration):
        next(gen)


def test_get_db_yields_fresh_connection_each_call(isolated_db: Path) -> None:
    gen1 = get_db()
    conn1 = _drain(gen1)
    gen2 = get_db()
    conn2 = _drain(gen2)
    try:
        assert isinstance(conn1, sqlite3.Connection)
        assert isinstance(conn2, sqlite3.Connection)
        assert conn1 is not conn2
    finally:
        _close_gen(gen1)
        _close_gen(gen2)


def test_get_db_closes_connection_on_success_path(isolated_db: Path) -> None:
    gen = get_db()
    conn = _drain(gen)
    _close_gen(gen)
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_get_db_closes_connection_when_handler_raises(
    isolated_db: Path,
) -> None:
    gen = get_db()
    conn = _drain(gen)

    with pytest.raises(RuntimeError):
        gen.throw(RuntimeError("handler failure"))

    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_get_settings_dep_returns_fresh_settings_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OHMYSTOCK_CONFIRM_TIMEOUT_MINUTES", "42")
    s1 = get_settings_dep()
    s2 = get_settings_dep()
    assert isinstance(s1, Settings)
    assert isinstance(s2, Settings)
    assert s1 is not s2
    assert s1.ohmystock_confirm_timeout_minutes == 42
    assert s2.ohmystock_confirm_timeout_minutes == 42
