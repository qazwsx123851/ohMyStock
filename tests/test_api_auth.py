"""Auth coverage for /api/admin/* — Bearer token gate.

Spec: openspec/changes/web-admin-bearer-auth-v0/specs/web-admin-bearer-auth/spec.md
"""

from __future__ import annotations

import json
import secrets as secrets_module
import sqlite3
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from ohmystock.api import auth as auth_module
from ohmystock.api.app import create_app
from ohmystock.api.auth import (
    AuthError,
    _validate_admin_token,
    require_admin,
)
from ohmystock.api.routes._deps import get_db
from ohmystock.api.routes.exit_engine import get_market_data
from ohmystock.config import Settings
from ohmystock.exit_engine.evaluator import MarketDataLookup
from ohmystock.journal.schema import init_schema
from tests.conftest import VALID_ADMIN_TOKEN


WRONG_TOKEN = "wrong-token-32-characters-or-more-zz"  # 36 chars, well-formed but mismatched


# ---------------------------------------------------------------------------
# _validate_admin_token (startup fail-fast) — direct unit tests
# ---------------------------------------------------------------------------


def test_validate_admin_token_rejects_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OHMYSTOCK_ADMIN_TOKEN", raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    settings = Settings()
    assert settings.ohmystock_admin_token is None
    with pytest.raises(RuntimeError) as exc_info:
        _validate_admin_token(settings)
    msg = str(exc_info.value)
    assert "OHMYSTOCK_ADMIN_TOKEN must be set" in msg
    assert "32" in msg


def test_validate_admin_token_rejects_empty_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OHMYSTOCK_ADMIN_TOKEN", "")
    settings = Settings()
    with pytest.raises(RuntimeError) as exc_info:
        _validate_admin_token(settings)
    assert "32" in str(exc_info.value)


def test_validate_admin_token_rejects_short_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OHMYSTOCK_ADMIN_TOKEN", "too-short")  # 9 chars
    settings = Settings()
    with pytest.raises(RuntimeError) as exc_info:
        _validate_admin_token(settings)
    msg = str(exc_info.value)
    assert "OHMYSTOCK_ADMIN_TOKEN must be set" in msg
    assert "32" in msg


def test_validate_admin_token_accepts_32_char_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token32 = "a" * 32
    monkeypatch.setenv("OHMYSTOCK_ADMIN_TOKEN", token32)
    settings = Settings()
    _validate_admin_token(settings)  # should not raise


def test_create_app_refuses_to_start_without_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OHMYSTOCK_ADMIN_TOKEN", raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    with pytest.raises(RuntimeError) as exc_info:
        create_app()
    msg = str(exc_info.value)
    assert "OHMYSTOCK_ADMIN_TOKEN must be set" in msg
    assert "32" in msg


def test_create_app_refuses_to_start_with_short_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OHMYSTOCK_ADMIN_TOKEN", "too-short")
    with pytest.raises(RuntimeError):
        create_app()


# ---------------------------------------------------------------------------
# require_admin dependency — direct exception coverage
# ---------------------------------------------------------------------------


def test_require_admin_missing_header_raises_auth_missing() -> None:
    with pytest.raises(AuthError) as exc_info:
        require_admin(authorization=None)
    assert exc_info.value.code == "auth_missing"


def test_require_admin_basic_scheme_raises_auth_missing() -> None:
    with pytest.raises(AuthError) as exc_info:
        require_admin(authorization="Basic dXNlcjpwYXNz")
    assert exc_info.value.code == "auth_missing"


def test_require_admin_lowercase_bearer_raises_auth_missing() -> None:
    with pytest.raises(AuthError) as exc_info:
        require_admin(authorization=f"bearer {VALID_ADMIN_TOKEN}")
    assert exc_info.value.code == "auth_missing"


def test_require_admin_wrong_token_raises_auth_invalid() -> None:
    with pytest.raises(AuthError) as exc_info:
        require_admin(authorization=f"Bearer {WRONG_TOKEN}")
    assert exc_info.value.code == "auth_invalid"


def test_require_admin_correct_token_passes() -> None:
    # Returns None (no raise) when token matches.
    result = require_admin(authorization=f"Bearer {VALID_ADMIN_TOKEN}")
    assert result is None


def test_require_admin_uses_secrets_compare_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []
    real_compare_digest = secrets_module.compare_digest

    def _spy(a: str, b: str) -> bool:
        calls.append((a, b))
        return real_compare_digest(a, b)

    monkeypatch.setattr(auth_module.secrets, "compare_digest", _spy)
    require_admin(authorization=f"Bearer {VALID_ADMIN_TOKEN}")
    assert len(calls) >= 1


# ---------------------------------------------------------------------------
# HTTP-level coverage — every admin endpoint returns 401 + envelope
# ---------------------------------------------------------------------------


class _NullMarketData:
    def get_close(self, symbol: str, asof) -> float | None:  # type: ignore[override]
        return None


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    init_schema(c)
    try:
        yield c
    finally:
        c.close()


def _build_client(
    conn: sqlite3.Connection,
    *,
    headers: dict[str, str] | None = None,
    market: MarketDataLookup | None = None,
) -> AsyncClient:
    app = create_app()

    def _override_get_db():
        yield conn

    app.dependency_overrides[get_db] = _override_get_db
    if market is not None:
        app.dependency_overrides[get_market_data] = lambda: market
    transport = ASGITransport(app=app)
    return AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=headers if headers is not None else {},
    )


def _admin_endpoints() -> list[tuple[str, str, dict[str, Any] | None]]:
    """Return ``(method, path, json_body)`` for each /api/admin/* endpoint."""

    return [
        ("GET", "/api/admin/events", None),
        ("POST", "/api/admin/screener/run", {"universe": "TWSE+OTC"}),
        ("GET", "/api/admin/confirm-gate/pending", None),
        (
            "POST",
            "/api/admin/confirm-gate/confirm",
            {"decision_id": "x", "user": "mark"},
        ),
        (
            "POST",
            "/api/admin/confirm-gate/reject",
            {"decision_id": "x", "user": "mark", "reason": "weak"},
        ),
        ("POST", "/api/admin/confirm-gate/sweep-expired", {}),
        (
            "POST",
            "/api/admin/exit-engine/run",
            {"asof_date": "2026-05-07"},
        ),
    ]


@pytest.mark.parametrize("method,path,body", _admin_endpoints())
async def test_admin_endpoint_without_token_returns_401(
    conn: sqlite3.Connection, method: str, path: str, body: dict[str, Any] | None
) -> None:
    async with _build_client(conn, market=_NullMarketData()) as client:
        if method == "GET":
            r = await client.get(path)
        else:
            r = await client.post(path, json=body or {})
    assert r.status_code == 401, (path, r.text)
    payload = r.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "auth_missing"
    assert isinstance(payload["error"]["message"], str)
    assert payload["error"]["message"]


@pytest.mark.parametrize("method,path,body", _admin_endpoints())
async def test_admin_endpoint_with_wrong_token_returns_401_auth_invalid(
    conn: sqlite3.Connection, method: str, path: str, body: dict[str, Any] | None
) -> None:
    headers = {"Authorization": f"Bearer {WRONG_TOKEN}"}
    async with _build_client(conn, headers=headers, market=_NullMarketData()) as client:
        if method == "GET":
            r = await client.get(path)
        else:
            r = await client.post(path, json=body or {})
    assert r.status_code == 401, (path, r.text)
    assert r.json()["error"]["code"] == "auth_invalid"


async def test_admin_endpoint_with_basic_scheme_returns_401_auth_missing(
    conn: sqlite3.Connection,
) -> None:
    headers = {"Authorization": "Basic dXNlcjpwYXNz"}
    async with _build_client(conn, headers=headers) as client:
        r = await client.post(
            "/api/admin/screener/run", json={"universe": "TWSE+OTC"}
        )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "auth_missing"


async def test_admin_endpoint_with_lowercase_bearer_returns_401_auth_missing(
    conn: sqlite3.Connection,
) -> None:
    headers = {"Authorization": f"bearer {VALID_ADMIN_TOKEN}"}
    async with _build_client(conn, headers=headers) as client:
        r = await client.post(
            "/api/admin/screener/run", json={"universe": "TWSE+OTC"}
        )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "auth_missing"


async def test_healthz_works_without_token(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as client:
        r = await client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


# ---------------------------------------------------------------------------
# 401 body redaction — token, stack trace, paths must NOT leak
# ---------------------------------------------------------------------------


_FORBIDDEN_SUBSTRINGS = (
    VALID_ADMIN_TOKEN,
    WRONG_TOKEN,
    "/Users/",
    "/home/",
    "Traceback",
    'File "',
    ".py\", line ",
)


async def test_401_body_does_not_leak_token_or_stack_trace(
    conn: sqlite3.Connection,
) -> None:
    headers = {"Authorization": f"Bearer {WRONG_TOKEN}"}
    async with _build_client(conn, headers=headers) as client:
        r = await client.post(
            "/api/admin/screener/run", json={"universe": "TWSE+OTC"}
        )
    assert r.status_code == 401
    body_text = json.dumps(r.json())
    for needle in _FORBIDDEN_SUBSTRINGS:
        assert needle not in body_text, f"leaked: {needle!r} in {body_text!r}"


async def test_401_body_missing_header_does_not_leak_token(
    conn: sqlite3.Connection,
) -> None:
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/confirm-gate/pending")
    assert r.status_code == 401
    body_text = json.dumps(r.json())
    for needle in _FORBIDDEN_SUBSTRINGS:
        assert needle not in body_text, f"leaked: {needle!r} in {body_text!r}"


# ---------------------------------------------------------------------------
# Happy path — one probe per route is enough; full behavior covered elsewhere
# ---------------------------------------------------------------------------


async def test_screener_with_valid_token_does_not_return_401(
    conn: sqlite3.Connection,
) -> None:
    headers = {"Authorization": f"Bearer {VALID_ADMIN_TOKEN}"}
    async with _build_client(conn, headers=headers) as client:
        r = await client.post(
            "/api/admin/screener/run",
            json={"universe": "TWSE+OTC", "asof_date": "2026-04-30"},
        )
    # screener may legitimately return 503 data_unavailable on empty cache,
    # but never 401/403 with a valid token.
    assert r.status_code != 401
    assert r.status_code != 403
