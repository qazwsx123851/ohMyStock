"""HTTP tests for /api/admin/reviews endpoints (list, detail).

Spec scenarios covered (admin-reviews-endpoints):

* List endpoint (200 mixed-kind shape, sort by completed_at desc, missing
  _index.json → empty, empty reviews array → empty, corrupted _index → 500
  internal_error with fixed message; ?kind= narrow / invalid 400 / zero
  matches; limit clamp ≤200, offset<0 → 400, limit<1 → 400, has_more).
* Detail endpoint (200 complete, 200 partial with critique crash,
  proposals_created parsed, empty proposals_created sentinel, malformed
  proposals_created → warning + empty list, path-traversal slugs → 400,
  404 only when both dir and index row absent, dir-only → partial,
  index-only → partial).
* Bearer auth on both endpoints (401 auth_missing / auth_invalid).
* Reviews root indirection (_REVIEWS_ROOT_FACTORY default + monkeypatch).
* Path-traversal invariant (_INVALID_NAME_TOKENS == proposals'.).

Spec: openspec/changes/admin-reviews-endpoints-and-pages/specs/admin-reviews-endpoints/spec.md
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from ohmystock.api.app import create_app
from ohmystock.api.routes import proposals as routes_proposals
from ohmystock.api.routes import reviews as routes_reviews
from tests.conftest import VALID_ADMIN_TOKEN


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_index(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "v3.0",
        "last_updated": "2026-05-12T10:00:00+08:00",
        "reviews": rows,
    }


def _make_summary(
    review_id: str,
    *,
    kind: str = "manual",
    period_from: str = "2026-04-01",
    period_to: str = "2026-04-30",
    trade_count: int = 23,
    win_rate: float = 0.565,
    pf: float = 1.84,
    proposals_created: int = 3,
    completed_at: str = "2026-04-30T19:42:18+08:00",
) -> dict[str, Any]:
    return {
        "review_id": review_id,
        "kind": kind,
        "period": {"from": period_from, "to": period_to},
        "trade_count": trade_count,
        "win_rate": win_rate,
        "pf": pf,
        "proposals_created": proposals_created,
        "completed_at": completed_at,
    }


def _write_review_dir(
    root: Path,
    review_id: str,
    *,
    files: dict[str, str],
) -> Path:
    """Create ``<root>/<review_id>/`` populated with the given filename→content map."""
    review_dir = root / review_id
    review_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        (review_dir / filename).write_text(content, encoding="utf-8")
    return review_dir


_FULL_METRICS_JSON = json.dumps(
    {
        "overall": {
            "win_rate": 0.565,
            "profit_factor": 1.84,
            "expectancy_pct": 0.023,
            "max_drawdown_pct": -0.075,
            "max_consecutive_loss": 3,
            "avg_hold_days": 8.4,
        },
        "by_skill": {},
    }
)

_FULL_REPORT_MD = "# 2026-04 月度復盤\n\n期間概覽:23 筆交易,勝率 56.5%。\n"

_FULL_PROPOSALS_CREATED_MD = """# 2026-04 月度復盤產生的提案

| Proposal | Status | Priority | Target |
|---|---|---|---|
| [2026-04-30-vcp-volume-threshold](../../proposals/2026-04-30-vcp-volume-threshold.md) | pending | high | cheatsheet §6.4 |
| [2026-04-30-time-stop-extend-vcp](../../proposals/2026-04-30-time-stop-extend-vcp.md) | pending | medium | cheatsheet §7.B |
"""


def _full_review_files() -> dict[str, str]:
    """6 standard files for a fully-complete review fixture."""
    return {
        "data.json": "{}",
        "attribution.json": "{}",
        "metrics.json": _FULL_METRICS_JSON,
        "critique.md": "### 高警示\n本期 VCP 命中率偏低。\n",
        "report.md": _FULL_REPORT_MD,
        "proposals_created.md": _FULL_PROPOSALS_CREATED_MD,
    }


@pytest.fixture()
def reviews_tmp_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Create tmp_path/reviews + 4 fixture reviews (one per kind) + 1 partial.

    Layout:
      manual-2026-04-01-to-2026-04-30/  full 6 files,  in _index
      2026-04/                          full 6 files,  in _index
      2026-Q1/                          full 6 files,  in _index
      forced-2026-04/                   full 6 files,  in _index
      partial-2026-05/                  only 3 files,  NOT in _index
    """
    root = tmp_path / "reviews"
    root.mkdir()

    monkeypatch.setattr(
        routes_reviews, "_REVIEWS_ROOT_FACTORY", lambda: root
    )

    _write_review_dir(
        root, "manual-2026-04-01-to-2026-04-30", files=_full_review_files()
    )
    _write_review_dir(root, "2026-04", files=_full_review_files())
    _write_review_dir(root, "2026-Q1", files=_full_review_files())
    _write_review_dir(root, "forced-2026-04", files=_full_review_files())

    # Partial — only first 3 files landed (critic crash).
    partial_files = _full_review_files()
    for missing in ("critique.md", "report.md", "proposals_created.md"):
        del partial_files[missing]
    _write_review_dir(root, "partial-2026-05", files=partial_files)

    index = _make_index(
        [
            _make_summary(
                "manual-2026-04-01-to-2026-04-30",
                kind="manual",
                completed_at="2026-05-12T10:00:00+08:00",
            ),
            _make_summary(
                "2026-04",
                kind="monthly",
                completed_at="2026-04-30T19:42:18+08:00",
            ),
            _make_summary(
                "2026-Q1",
                kind="quarterly",
                period_from="2026-01-01",
                period_to="2026-03-31",
                trade_count=71,
                win_rate=0.62,
                pf=2.10,
                proposals_created=6,
                completed_at="2026-03-31T20:14:00+08:00",
            ),
            _make_summary(
                "forced-2026-04",
                kind="forced",
                completed_at="2026-04-20T15:00:00+08:00",
            ),
        ]
    )
    (root / "_index.json").write_text(
        json.dumps(index, ensure_ascii=False), encoding="utf-8"
    )

    return root


@pytest.fixture()
def empty_reviews_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """A tmp reviews/ that has no _index.json and no review dirs."""
    root = tmp_path / "reviews"
    root.mkdir()
    monkeypatch.setattr(
        routes_reviews, "_REVIEWS_ROOT_FACTORY", lambda: root
    )
    return root


@pytest.fixture()
def client_factory():
    """AsyncClient bound to a fresh app with a valid Bearer token by default."""

    def build(*, headers: dict[str, str] | None = None) -> AsyncClient:
        app = create_app()
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
# List endpoint — shape + source
# ---------------------------------------------------------------------------


async def test_list_200_with_mixed_kind_index(
    client_factory, reviews_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/reviews")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    data = body["data"]
    # 4 indexed reviews; the partial review without an _index row is NOT listed.
    assert data["total"] == 4
    assert data["limit"] == 50
    assert data["offset"] == 0
    assert data["has_more"] is False
    items = data["items"]
    assert len(items) == 4
    expected_keys = {
        "review_id",
        "kind",
        "period",
        "trade_count",
        "win_rate",
        "pf",
        "proposals_created",
        "completed_at",
    }
    for item in items:
        assert set(item.keys()) == expected_keys


async def test_list_items_sorted_by_completed_at_desc(
    client_factory, reviews_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/reviews")
    items = r.json()["data"]["items"]
    completed = [i["completed_at"] for i in items]
    assert completed == sorted(completed, reverse=True)
    assert completed[0].startswith("2026-05-12")


async def test_list_missing_index_returns_empty_not_404(
    client_factory, empty_reviews_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/reviews")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["items"] == []
    assert data["total"] == 0
    assert data["has_more"] is False


async def test_list_empty_reviews_array_returns_empty(
    client_factory, empty_reviews_root: Path
) -> None:
    (empty_reviews_root / "_index.json").write_text(
        json.dumps({"schema_version": "v3.0", "reviews": []}),
        encoding="utf-8",
    )
    async with client_factory() as c:
        r = await c.get("/api/admin/reviews")
    assert r.status_code == 200
    assert r.json()["data"]["items"] == []
    assert r.json()["data"]["total"] == 0


async def test_list_corrupted_index_returns_500(
    client_factory, empty_reviews_root: Path
) -> None:
    (empty_reviews_root / "_index.json").write_text(
        "not valid json {{", encoding="utf-8"
    )
    async with client_factory() as c:
        r = await c.get("/api/admin/reviews")
    assert r.status_code == 500
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "internal_error"
    assert body["error"]["message"] == "reviews index is corrupted"
    assert "Traceback" not in r.text


# ---------------------------------------------------------------------------
# List endpoint — kind filter
# ---------------------------------------------------------------------------


async def test_list_kind_filter_narrows_to_one(
    client_factory, reviews_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/reviews?kind=monthly")
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["kind"] == "monthly"
    assert r.json()["data"]["total"] == 1


async def test_list_invalid_kind_returns_400(
    client_factory, reviews_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/reviews?kind=weekly")
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "invalid_input"
    assert "kind" in err["message"]


async def test_list_kind_filter_zero_matches_returns_empty(
    client_factory, empty_reviews_root: Path
) -> None:
    # Index with only monthly rows; query forced → empty list.
    index = _make_index([_make_summary("2026-04", kind="monthly")])
    (empty_reviews_root / "_index.json").write_text(
        json.dumps(index), encoding="utf-8"
    )
    async with client_factory() as c:
        r = await c.get("/api/admin/reviews?kind=forced")
    assert r.status_code == 200
    assert r.json()["data"]["items"] == []
    assert r.json()["data"]["total"] == 0


# ---------------------------------------------------------------------------
# List endpoint — pagination
# ---------------------------------------------------------------------------


async def test_list_limit_clamps_to_max(
    client_factory, reviews_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/reviews?limit=10000")
    assert r.status_code == 200
    assert r.json()["data"]["limit"] == 200


async def test_list_negative_offset_returns_400(
    client_factory, reviews_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/reviews?offset=-1")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_input"


async def test_list_limit_zero_returns_400(
    client_factory, reviews_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/reviews?limit=0")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_input"


async def test_list_has_more_reflects_remaining(
    client_factory, empty_reviews_root: Path
) -> None:
    rows = [
        _make_summary(
            f"manual-{i:03d}",
            kind="manual",
            completed_at=f"2026-04-{(i % 28) + 1:02d}T10:00:00+08:00",
        )
        for i in range(75)
    ]
    (empty_reviews_root / "_index.json").write_text(
        json.dumps(_make_index(rows)), encoding="utf-8"
    )
    async with client_factory() as c:
        r1 = await c.get("/api/admin/reviews?limit=50&offset=0")
        r2 = await c.get("/api/admin/reviews?limit=50&offset=50")
    d1 = r1.json()["data"]
    d2 = r2.json()["data"]
    assert d1["total"] == 75
    assert len(d1["items"]) == 50
    assert d1["has_more"] is True
    assert len(d2["items"]) == 25
    assert d2["has_more"] is False


# ---------------------------------------------------------------------------
# Detail endpoint — shape + happy path
# ---------------------------------------------------------------------------


async def test_detail_200_complete_review(
    client_factory, reviews_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/reviews/manual-2026-04-01-to-2026-04-30")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["review_id"] == "manual-2026-04-01-to-2026-04-30"
    assert data["partial"] is False
    assert data["summary"] is not None
    assert data["summary"]["kind"] == "manual"
    for key, _ in routes_reviews._STANDARD_FILES:
        assert data["files"][key]["exists"] is True
        assert data["files"][key]["path"] is not None
        # forward-slash relative path, regardless of host OS
        assert "\\" not in data["files"][key]["path"]
    assert data["report"] == _FULL_REPORT_MD
    assert set(data["metrics_overall"].keys()) == {
        "win_rate",
        "profit_factor",
        "expectancy_pct",
        "max_drawdown_pct",
        "max_consecutive_loss",
        "avg_hold_days",
    }
    assert data["metrics_overall"]["win_rate"] == 0.565
    assert len(data["proposals_created"]) == 2


async def test_detail_partial_review_when_critique_missing(
    client_factory, reviews_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/reviews/partial-2026-05")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["partial"] is True
    assert data["summary"] is None
    assert data["files"]["data_json"]["exists"] is True
    assert data["files"]["critique_md"]["exists"] is False
    assert data["files"]["report_md"]["exists"] is False
    assert data["report"] is None
    assert data["metrics_overall"] is not None  # metrics.json still exists


async def test_detail_proposals_created_parsed_rows(
    client_factory, reviews_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/reviews/manual-2026-04-01-to-2026-04-30")
    rows = r.json()["data"]["proposals_created"]
    assert len(rows) == 2
    assert rows[0]["slug"] == "2026-04-30-vcp-volume-threshold"
    assert rows[0]["status"] == "pending"
    assert rows[0]["priority"] == "high"
    assert rows[1]["slug"] == "2026-04-30-time-stop-extend-vcp"
    assert rows[1]["priority"] == "medium"


async def test_detail_empty_proposals_sentinel_returns_empty_list(
    client_factory, reviews_tmp_root: Path
) -> None:
    review_dir = reviews_tmp_root / "manual-2026-04-01-to-2026-04-30"
    (review_dir / "proposals_created.md").write_text(
        "本期無提案\n", encoding="utf-8"
    )
    async with client_factory() as c:
        r = await c.get("/api/admin/reviews/manual-2026-04-01-to-2026-04-30")
    assert r.json()["data"]["proposals_created"] == []


async def test_detail_malformed_proposals_created_warns_and_empties(
    client_factory,
    reviews_tmp_root: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    review_dir = reviews_tmp_root / "manual-2026-04-01-to-2026-04-30"
    # Pipe-prefixed garbage so the parser enters table mode but yields 0 rows.
    (review_dir / "proposals_created.md").write_text(
        "| garbage line without a link |\n", encoding="utf-8"
    )
    with caplog.at_level(logging.WARNING, logger="ohmystock.api.routes.reviews"):
        async with client_factory() as c:
            r = await c.get(
                "/api/admin/reviews/manual-2026-04-01-to-2026-04-30"
            )
    assert r.status_code == 200
    assert r.json()["data"]["proposals_created"] == []
    assert any(
        "could not parse proposals_created.md" in rec.message
        for rec in caplog.records
    )


# ---------------------------------------------------------------------------
# Detail endpoint — path-traversal & 404 boundaries
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "slug",
    [
        # NOTE: a bare ".." gets normalised away by httpx before reaching
        # FastAPI; we cover that path-traversal flavour via the invariant
        # test against the proposals module + the explicit ``deep..traversal``
        # case below (which embeds ".." mid-token, surviving normalisation).
        "ok\\bad",
        "deep..traversal",
    ],
)
async def test_detail_path_traversal_returns_400(
    client_factory, reviews_tmp_root: Path, slug: str
) -> None:
    async with client_factory() as c:
        r = await c.get(f"/api/admin/reviews/{slug}")
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "invalid_input"


async def test_detail_forward_slash_does_not_reach_handler(
    client_factory, reviews_tmp_root: Path
) -> None:
    """A literal forward slash in the slug makes FastAPI parse it as a
    multi-segment path, so the route never matches our 1-segment handler.
    The response is 404 from the router (NOT a 200 leaking files).
    """
    async with client_factory() as c:
        r = await c.get("/api/admin/reviews/foo/bar")
    assert r.status_code in (400, 404)


async def test_detail_404_when_neither_dir_nor_index_row(
    client_factory, reviews_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.get(
            "/api/admin/reviews/manual-2099-12-31-to-2099-12-31"
        )
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "not_found"
    assert "manual-2099-12-31-to-2099-12-31" in err["message"]


async def test_detail_dir_only_returns_200_partial(
    client_factory, reviews_tmp_root: Path
) -> None:
    # partial-2026-05 fixture has a dir but no index row
    async with client_factory() as c:
        r = await c.get("/api/admin/reviews/partial-2026-05")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["partial"] is True
    assert data["summary"] is None


async def test_detail_index_only_returns_200_partial(
    client_factory, empty_reviews_root: Path
) -> None:
    # Build an index whose review_id has NO matching directory.
    index = _make_index([_make_summary("orphan-2026-01", kind="manual")])
    (empty_reviews_root / "_index.json").write_text(
        json.dumps(index), encoding="utf-8"
    )
    async with client_factory() as c:
        r = await c.get("/api/admin/reviews/orphan-2026-01")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["partial"] is True
    assert data["summary"] is not None
    for key, _ in routes_reviews._STANDARD_FILES:
        assert data["files"][key]["exists"] is False
        assert data["files"][key]["path"] is None


# ---------------------------------------------------------------------------
# Bearer auth
# ---------------------------------------------------------------------------


async def test_list_401_when_authorization_missing(
    client_factory, reviews_tmp_root: Path
) -> None:
    async with client_factory(headers={}) as c:
        r = await c.get("/api/admin/reviews")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "auth_missing"


async def test_detail_401_when_token_invalid(
    client_factory, reviews_tmp_root: Path
) -> None:
    async with client_factory(headers={"Authorization": "Bearer wrong"}) as c:
        r = await c.get("/api/admin/reviews/manual-2026-04-01-to-2026-04-30")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "auth_invalid"


# ---------------------------------------------------------------------------
# Invariants — module-level factories and token sets
# ---------------------------------------------------------------------------


# These two are synchronous invariants — opt them out of the module-level
# ``pytestmark = pytest.mark.asyncio`` so pytest-asyncio doesn't warn.
@pytest.mark.asyncio(loop_scope=None)
async def test_reviews_root_factory_default_returns_settings_path() -> None:
    # No monkeypatch — invoke the production lambda directly.
    path = routes_reviews._REVIEWS_ROOT_FACTORY()
    assert path.name == "reviews"


@pytest.mark.asyncio(loop_scope=None)
async def test_invalid_name_tokens_match_proposals_module() -> None:
    """Path-safety policy must stay in sync between the two route modules."""
    assert set(routes_reviews._INVALID_NAME_TOKENS) == set(
        routes_proposals._INVALID_NAME_TOKENS
    )
