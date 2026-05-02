"""FastAPI dependencies shared by every admin action endpoint.

* ``get_db`` — yield a fresh ``sqlite3.Connection`` per request and close
  it in the generator's ``finally`` block (works for both success and
  raise paths). Spec requires this lifecycle: see scenarios under
  "每個請求自開自關 sqlite3 connection".

* ``get_settings_dep`` — return a fresh ``Settings`` per call. Per-call
  construction avoids stale env-var caches when tests use
  ``monkeypatch.setenv`` between requests.

Spec: openspec/changes/server-action-endpoints-v0/specs/server-action-endpoints/spec.md
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from ohmystock.api.db import get_connection
from ohmystock.config import Settings


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: yield a fresh connection, always close after."""

    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def get_settings_dep() -> Settings:
    """FastAPI dependency: return a fresh ``Settings`` instance per request."""

    return Settings()
