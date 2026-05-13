"""HTTP tests for ``/api/admin/swarm/*``.

Spec: openspec/changes/admin-swarm-endpoints-and-pages/specs/swarm-runs/spec.md
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from ohmystock.api.app import create_app
from ohmystock.api.routes._deps import get_db
from ohmystock.review.pipeline import ReviewResult
from ohmystock.swarm_runs import runner as runner_mod
from ohmystock.swarm_runs import storage as swarm_storage
from tests.conftest import VALID_ADMIN_TOKEN


pytestmark = pytest.mark.asyncio


@pytest.fixture()
def conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(":memory:", check_same_thread=False)
    swarm_storage.init_schema(c)
    try:
        yield c
    finally:
        c.close()


def _build_client(
    conn: sqlite3.Connection, *, headers: dict[str, str] | None = None
) -> AsyncClient:
    app = create_app()

    def _override_get_db() -> Iterator[sqlite3.Connection]:
        yield conn

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    return AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=headers
        if headers is not None
        else {"Authorization": f"Bearer {VALID_ADMIN_TOKEN}"},
    )


def _good_review_result() -> ReviewResult:
    return ReviewResult(
        review_id="manual-2026-04-01-to-2026-04-30",
        period_from=date(2026, 4, 1),
        period_to=date(2026, 4, 30),
        trade_count=0,
        proposals_created=0,
        proposals_files=[],
        total_input_tokens=0,
        total_output_tokens=0,
        total_cost_usd=0.0,
        out_dir="/tmp/r",
        proposals_dir="/tmp/p",
        dry_run=True,
    )


def _seed_row(conn: sqlite3.Connection, **overrides: Any) -> str:
    row = swarm_storage.SwarmRunRowDict(
        id=overrides.get("id", "swr_seedfeed1234"),
        preset=overrides.get("preset", "phase5-review"),
        status=overrides.get("status", "completed"),
        params_json=overrides.get("params_json", '{"period_from":"2026-04-01"}'),
        result_json=overrides.get("result_json", '{"node_outputs":{}}'),
        elapsed_ms=overrides.get("elapsed_ms", 100),
        created_at=overrides.get("created_at", "2026-05-13T12:00:00+08:00"),
    )
    swarm_storage.insert_run(conn, row)
    return row["id"]


# ---------------------------------------------------------------------------
# GET /presets
# ---------------------------------------------------------------------------


async def test_get_presets_lists_phase5_review(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/swarm/presets")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    items = body["data"]["items"]
    assert any(p["name"] == "phase5-review" for p in items)


async def test_get_presets_requires_auth(conn: sqlite3.Connection) -> None:
    async with _build_client(conn, headers={}) as client:
        r = await client.get("/api/admin/swarm/presets")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "auth_missing"


# ---------------------------------------------------------------------------
# POST /runs
# ---------------------------------------------------------------------------


async def test_post_runs_happy_path(
    conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-1234567890abcdef")
    monkeypatch.setattr(runner_mod, "run_review", lambda **kw: _good_review_result())

    body = {
        "preset": "phase5-review",
        "params": {
            "period_from": "2026-04-01",
            "period_to": "2026-04-30",
            "limit_trades": None,
            "dry_run": True,
            "force": False,
        },
    }
    async with _build_client(conn) as client:
        r = await client.post("/api/admin/swarm/runs", json=body)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "completed"
    assert data["preset"] == "phase5-review"
    assert data["id"].startswith("swr_")
    assert "node_outputs" in data["result"]


async def test_post_runs_failure_still_returns_200_with_failed_status(
    conn: sqlite3.Connection,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-1234567890abcdef")
    monkeypatch.setenv("REVIEWS_DIR", str(tmp_path / "reviews"))
    monkeypatch.setenv("PROPOSALS_DIR", str(tmp_path / "proposals"))
    review_dir = tmp_path / "reviews" / "manual-2026-04-01-to-2026-04-30"
    review_dir.mkdir(parents=True)
    (review_dir / "data.json").write_text("{}", encoding="utf-8")
    (review_dir / "attribution.json").write_text("{}", encoding="utf-8")

    def _boom(**kw):  # type: ignore[no-untyped-def]
        raise RuntimeError("aggregator boom")

    monkeypatch.setattr(runner_mod, "run_review", _boom)

    body = {
        "preset": "phase5-review",
        "params": {
            "period_from": "2026-04-01",
            "period_to": "2026-04-30",
            "limit_trades": None,
            "dry_run": False,
            "force": False,
        },
    }
    async with _build_client(conn) as client:
        r = await client.post("/api/admin/swarm/runs", json=body)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "failed"
    assert data["result"]["failed_node"] == "aggregator"


async def test_post_runs_unknown_preset_400(
    conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-1234567890abcdef")
    async with _build_client(conn) as client:
        r = await client.post(
            "/api/admin/swarm/runs",
            json={"preset": "nonexistent", "params": {}},
        )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_input"


async def test_post_runs_missing_api_key_422(
    conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    body = {
        "preset": "phase5-review",
        "params": {
            "period_from": "2026-04-01",
            "period_to": "2026-04-30",
            "limit_trades": None,
            "dry_run": True,
            "force": False,
        },
    }
    async with _build_client(conn) as client:
        r = await client.post("/api/admin/swarm/runs", json=body)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "missing_api_key"


async def test_post_runs_extra_field_rejected(
    conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-1234567890abcdef")
    async with _build_client(conn) as client:
        r = await client.post(
            "/api/admin/swarm/runs",
            json={
                "preset": "phase5-review",
                "params": {},
                "extra": "boom",
            },
        )
    assert r.status_code == 422


async def test_post_runs_requires_auth(conn: sqlite3.Connection) -> None:
    async with _build_client(conn, headers={}) as client:
        r = await client.post(
            "/api/admin/swarm/runs",
            json={"preset": "phase5-review", "params": {}},
        )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# GET /runs (list)
# ---------------------------------------------------------------------------


async def test_get_runs_list_returns_summary_only(
    conn: sqlite3.Connection,
) -> None:
    _seed_row(conn, id="swr_aaa", created_at="2026-05-12T00:00:00+08:00")
    _seed_row(conn, id="swr_bbb", created_at="2026-05-13T00:00:00+08:00")
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/swarm/runs")
    assert r.status_code == 200
    data = r.json()["data"]
    assert [item["id"] for item in data["items"]] == ["swr_bbb", "swr_aaa"]
    for item in data["items"]:
        assert set(item.keys()) == {"id", "preset", "status", "elapsed_ms", "created_at"}


async def test_get_runs_list_clamps_limit_to_100(
    conn: sqlite3.Connection,
) -> None:
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/swarm/runs?limit=999")
    assert r.status_code == 200
    assert r.json()["data"]["limit"] == 100


async def test_get_runs_list_limit_zero_400(
    conn: sqlite3.Connection,
) -> None:
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/swarm/runs?limit=0")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_input"


# ---------------------------------------------------------------------------
# GET /runs/{id}
# ---------------------------------------------------------------------------


async def test_get_run_by_id_returns_full_row_with_parsed_dicts(
    conn: sqlite3.Connection,
) -> None:
    _seed_row(conn, id="swr_abc123def456")
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/swarm/runs/swr_abc123def456")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["id"] == "swr_abc123def456"
    assert isinstance(data["params"], dict)
    assert isinstance(data["result"], dict)


async def test_get_run_by_id_404(conn: sqlite3.Connection) -> None:
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/swarm/runs/swr_doesnotexist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    assert "swr_doesnotexist" in r.json()["error"]["message"]


async def test_get_run_by_id_path_traversal_400(
    conn: sqlite3.Connection,
) -> None:
    async with _build_client(conn) as client:
        r = await client.get("/api/admin/swarm/runs/..%2Fsecrets")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_input"
