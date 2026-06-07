"""HTTP tests for ``GET /api/admin/settings``.

Spec scenarios covered:

* 401 on missing / wrong Bearer token.
* 200 default Settings (all secrets unset).
* 200 with anthropic / finmind / shioaji keys set → booleans flip true.
* 200 with shioaji half-set → ``shioaji=false`` (both halves required).
* 200 with whitespace-only key → treated as unset.
* Leak assertion: raw secret strings (and likely substrings) MUST NOT
  appear anywhere in the serialised response.
* 405 on PUT (read-only invariant).
* Whitelist invariant: ``data`` keys are exactly
  ``{api_keys, theme, safety, breakers}`` — no raw ``Settings`` field
  names leak.
* ``safety`` and ``breakers`` map 1:1 from ``Settings`` with no clamp.

Spec: openspec/changes/web-admin-settings-page/specs/admin-settings-endpoint/spec.md
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator

import pytest
from httpx import ASGITransport, AsyncClient

from ohmystock.api.app import create_app
from ohmystock.api.routes._deps import get_db
from ohmystock.journal.schema import init_schema
from tests.conftest import VALID_ADMIN_TOKEN


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_conn() -> Iterator[sqlite3.Connection]:
    """In-memory journal DB so the settings budget block reads a deterministic
    (empty by default) ``llm_costs`` table instead of the real on-disk DB."""

    c = sqlite3.connect(":memory:", check_same_thread=False)
    init_schema(c)
    try:
        yield c
    finally:
        c.close()


@pytest.fixture()
def client_factory(db_conn: sqlite3.Connection):
    """Return a builder that yields an AsyncClient bound to a fresh app.

    Per-test factory so individual tests can override env vars via
    ``monkeypatch.setenv`` *before* ``create_app()`` reads ``Settings()``.
    ``get_db`` is overridden to the in-memory ``db_conn`` so the budget block
    is deterministic and no real DB file is touched.
    """

    def build(*, headers: dict[str, str] | None = None) -> AsyncClient:
        app = create_app()

        def _override_get_db() -> Iterator[sqlite3.Connection]:
            yield db_conn

        app.dependency_overrides[get_db] = _override_get_db
        transport = ASGITransport(app=app)
        return AsyncClient(
            transport=transport,
            base_url="http://test",
            headers=headers
            if headers is not None
            else {"Authorization": f"Bearer {VALID_ADMIN_TOKEN}"},
        )

    return build


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


async def test_no_auth_returns_401(client_factory) -> None:
    async with client_factory(headers={}) as c:
        r = await c.get("/api/admin/settings")
    assert r.status_code == 401
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "auth_missing"


async def test_wrong_token_returns_401(client_factory) -> None:
    async with client_factory(headers={"Authorization": "Bearer wrong"}) as c:
        r = await c.get("/api/admin/settings")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "auth_invalid"


# ---------------------------------------------------------------------------
# Schema & whitelist
# ---------------------------------------------------------------------------


async def test_default_settings_all_four_sections(
    client_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Force "unset" via empty env vars — pydantic-settings precedence is
    # env > .env, so an explicit empty value overrides any local .env.
    for var in (
        "ANTHROPIC_API_KEY",
        "FINMIND_TOKEN",
        "SHIOAJI_API_KEY",
        "SHIOAJI_SECRET_KEY",
    ):
        monkeypatch.setenv(var, "")
    monkeypatch.setenv("OHMYSTOCK_AUTO_EXECUTE", "false")
    monkeypatch.setenv("OHMYSTOCK_BROKER", "shioaji-sim")

    async with client_factory() as c:
        r = await c.get("/api/admin/settings")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    data = body["data"]
    assert set(data.keys()) == {
        "api_keys",
        "theme",
        "safety",
        "breakers",
        "chat",
        "budget",
    }
    assert data["api_keys"] == {
        "anthropic": False,
        "finmind": False,
        "shioaji": False,
    }
    assert data["theme"] == {"mode": "system"}
    assert data["safety"]["auto_execute"] is False
    assert data["safety"]["broker"] == "shioaji-sim"
    assert data["chat"] == {
        "model_default": "claude-sonnet-4-6",
        "title_model": "claude-haiku-4-5-20251001",
    }


async def test_response_does_not_leak_raw_settings_field_names(
    client_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-deadbeefcafe1234")
    monkeypatch.setenv("FINMIND_TOKEN", "ft-livetokendata5678")
    monkeypatch.setenv("SHIOAJI_API_KEY", "sj-key-9012abcd")
    monkeypatch.setenv("SHIOAJI_SECRET_KEY", "sj-secret-3456efgh")

    async with client_factory() as c:
        r = await c.get("/api/admin/settings")

    text = r.text
    forbidden_names = (
        "anthropic_api_key",
        "finmind_token",
        "shioaji_api_key",
        "shioaji_secret_key",
        "ohmystock_admin_token",
        "ohmystock_db_path",
        "ohmystock_log_level",
        "starting_equity_twd",
        "ohmystock_decider_model",
        "ohmystock_confirm_timeout_minutes",
    )
    for name in forbidden_names:
        assert name not in text, f"raw Settings field name {name!r} leaked"


# ---------------------------------------------------------------------------
# Secret detection
# ---------------------------------------------------------------------------


async def test_all_keys_set(
    client_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("FINMIND_TOKEN", "ft-test")
    monkeypatch.setenv("SHIOAJI_API_KEY", "sj-key")
    monkeypatch.setenv("SHIOAJI_SECRET_KEY", "sj-sec")

    async with client_factory() as c:
        r = await c.get("/api/admin/settings")

    assert r.status_code == 200
    assert r.json()["data"]["api_keys"] == {
        "anthropic": True,
        "finmind": True,
        "shioaji": True,
    }


async def test_shioaji_half_set_is_false(
    client_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SHIOAJI_API_KEY", "sj-key")
    monkeypatch.setenv("SHIOAJI_SECRET_KEY", "")

    async with client_factory() as c:
        r = await c.get("/api/admin/settings")

    assert r.json()["data"]["api_keys"]["shioaji"] is False


async def test_whitespace_key_is_unset(
    client_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")

    async with client_factory() as c:
        r = await c.get("/api/admin/settings")

    assert r.json()["data"]["api_keys"]["anthropic"] is False


# ---------------------------------------------------------------------------
# Leak assertion — raw secret strings must not surface
# ---------------------------------------------------------------------------


async def test_raw_secret_does_not_appear_in_response(
    client_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-deadbeefcafe1234")

    async with client_factory() as c:
        r = await c.get("/api/admin/settings")

    text = r.text
    assert "sk-ant-deadbeefcafe1234" not in text
    assert "sk-ant" not in text
    assert "deadbeef" not in text
    assert "cafe" not in text
    assert "1234" not in text


# ---------------------------------------------------------------------------
# safety / breakers mapping
# ---------------------------------------------------------------------------


async def test_breakers_default_values(
    client_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    for var in (
        "OHMYSTOCK_AUTO_EXECUTE_MIN_CONFIDENCE",
        "OHMYSTOCK_AUTO_EXECUTE_DAILY_LIMIT",
        "OHMYSTOCK_AUTO_EXECUTE_MAX_NOTIONAL_PCT",
        "OHMYSTOCK_AUTO_EXECUTE_MAX_SIZING_DEVIATION",
        "OHMYSTOCK_AUTO_EXECUTE_LOSS_LOCKOUT_HOURS",
        "OHMYSTOCK_AUTO_EXECUTE_LOSS_PCT_THRESHOLD",
        "OHMYSTOCK_AUTO_EXECUTE_ACCOUNT_EQUITY_TWD",
    ):
        monkeypatch.delenv(var, raising=False)

    async with client_factory() as c:
        r = await c.get("/api/admin/settings")

    breakers = r.json()["data"]["breakers"]
    assert breakers["min_confidence"] == 0.7
    assert breakers["daily_limit"] == 5
    assert breakers["max_notional_pct"] == 0.25
    assert breakers["max_sizing_deviation"] == 0.30
    assert breakers["loss_lockout_hours"] == 24
    assert breakers["loss_pct_threshold"] == -0.05
    assert breakers["account_equity_twd"] == 1_000_000


async def test_non_default_breaker_values(
    client_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OHMYSTOCK_AUTO_EXECUTE_MIN_CONFIDENCE", "0.85")
    monkeypatch.setenv("OHMYSTOCK_AUTO_EXECUTE_DAILY_LIMIT", "3")

    async with client_factory() as c:
        r = await c.get("/api/admin/settings")

    breakers = r.json()["data"]["breakers"]
    assert breakers["min_confidence"] == 0.85
    assert breakers["daily_limit"] == 3


async def test_auto_execute_true_reflected_in_safety(
    client_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OHMYSTOCK_AUTO_EXECUTE", "true")
    monkeypatch.setenv("OHMYSTOCK_BROKER", "shioaji-sim")

    async with client_factory() as c:
        r = await c.get("/api/admin/settings")

    safety = r.json()["data"]["safety"]
    assert safety["auto_execute"] is True
    assert safety["broker"] == "shioaji-sim"


# ---------------------------------------------------------------------------
# PUT rejected (read-only invariant)
# ---------------------------------------------------------------------------


async def test_put_returns_405(client_factory) -> None:
    async with client_factory() as c:
        r = await c.put(
            "/api/admin/settings",
            content=json.dumps({"safety": {"auto_execute": True}}),
            headers={"Content-Type": "application/json"},
        )
    assert r.status_code == 405


# ---------------------------------------------------------------------------
# budget block (ST-B2)
# ---------------------------------------------------------------------------


async def test_budget_block_empty(
    client_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OHMYSTOCK_MONTHLY_BUDGET_USD", "100")
    async with client_factory() as c:
        r = await c.get("/api/admin/settings")
    budget = r.json()["data"]["budget"]
    assert budget["used_usd"] == 0.0
    assert budget["budget_usd"] == 100.0
    assert budget["remaining_usd"] == 100.0
    assert budget["model_mix"] == {"opus": 0.0, "sonnet": 0.0, "haiku": 0.0}


async def test_budget_block_with_spend(
    client_factory,
    db_conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import datetime as _dt

    ym = _dt.datetime.now(
        _dt.timezone(_dt.timedelta(hours=8))
    ).date().isoformat()[:7]
    db_conn.execute(
        "INSERT INTO llm_costs(model, input_tokens, output_tokens, cost_usd, "
        "created_at) VALUES (?, ?, ?, ?, ?)",
        ("claude-opus-4-7", 1, 1, 60.0, f"{ym}-05T09:00:00+08:00"),
    )
    db_conn.execute(
        "INSERT INTO llm_costs(model, input_tokens, output_tokens, cost_usd, "
        "created_at) VALUES (?, ?, ?, ?, ?)",
        ("claude-sonnet-4-6", 1, 1, 20.0, f"{ym}-05T09:00:00+08:00"),
    )
    db_conn.commit()
    monkeypatch.setenv("OHMYSTOCK_MONTHLY_BUDGET_USD", "100")

    async with client_factory() as c:
        r = await c.get("/api/admin/settings")
    budget = r.json()["data"]["budget"]
    assert budget["used_usd"] == pytest.approx(80.0)
    assert budget["remaining_usd"] == pytest.approx(20.0)
    assert budget["model_mix"]["opus"] == pytest.approx(0.75)
    assert budget["model_mix"]["sonnet"] == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# POST /test-connection (ST-B1)
# ---------------------------------------------------------------------------


async def test_connection_success(
    client_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ohmystock.api.routes.settings as settings_module

    monkeypatch.setitem(settings_module._PROBES, "finmind", lambda: None)
    async with client_factory() as c:
        r = await c.post(
            "/api/admin/settings/test-connection",
            content=json.dumps({"provider": "finmind"}),
            headers={"Content-Type": "application/json"},
        )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["ok"] is True
    assert "latency_ms" in data


async def test_connection_failure_no_key_leak(
    client_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ohmystock.api.routes.settings as settings_module

    def _boom() -> None:
        raise RuntimeError("Shioaji login failed: connection refused")

    monkeypatch.setitem(settings_module._PROBES, "shioaji", _boom)
    async with client_factory() as c:
        r = await c.post(
            "/api/admin/settings/test-connection",
            content=json.dumps({"provider": "shioaji"}),
            headers={"Content-Type": "application/json"},
        )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["ok"] is False
    assert "connection refused" in data["error"]
    # key material never appears
    assert "secret" not in r.text.lower() or "secret_key" not in r.text


async def test_connection_invalid_provider(client_factory) -> None:
    async with client_factory() as c:
        r = await c.post(
            "/api/admin/settings/test-connection",
            content=json.dumps({"provider": "bogus"}),
            headers={"Content-Type": "application/json"},
        )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_input"
