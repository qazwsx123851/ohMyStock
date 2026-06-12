"""HTTP tests for ``POST /api/admin/proposals/{slug}/validate``.

Covers auth gate, body validation (extra/missing/inverted/empty), path traversal,
unknown slug, unparseable params, happy-pass / happy-fail (manual-verdict mode:
report written, status stays validating), dry-run (status stays validating),
state-machine guard (status != validating → 409 illegal_transition), unknown
strategy / missing bars / period_too_short → 422 wfa_validation_failed, GET 405.

Synthetic monotonic-price bars + the ``_MARKET_DATA_LOADER_FACTORY`` test seam
keep the entire flow off SQLite — no cache fixture is needed.

Spec: openspec/changes/admin-proposal-validate-action/specs/admin-proposals-endpoints/spec.md
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import pytest
from httpx import ASGITransport, AsyncClient

from ohmystock.api.app import create_app
from ohmystock.api.routes import proposals as proposals_route
from ohmystock.data.sources.base import BarRow
from ohmystock.proposal import (
    ProposalDraft,
    transition_proposal,
    write_proposal,
)
from ohmystock.validation import wfa as wfa_module
from tests.conftest import VALID_ADMIN_TOKEN


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Synthetic bars + proposal fixtures
# ---------------------------------------------------------------------------


_TPE = timezone(timedelta(hours=8))


def _synthetic_bars(n_days: int, base_price: float = 100.0) -> list[BarRow]:
    """Monotonic up-trend BarRows starting 2025-01-02, Mon-Fri only."""
    rows: list[BarRow] = []
    current = date(2025, 1, 2)
    i = 0
    while len(rows) < n_days:
        if current.weekday() < 5:
            price = base_price + i * 0.5
            rows.append(
                BarRow(
                    ts=current.isoformat(),
                    o=price,
                    h=price,
                    l=price,
                    c=price,
                    v=1_000_000,
                    amount=int(price * 1_000_000),
                )
            )
            i += 1
        current = current + timedelta(days=1)
    return rows


def _make_draft(topic: str = "validate-x") -> ProposalDraft:
    return ProposalDraft(
        topic=topic,
        target_section="cheatsheet §6.6",
        created_by="mark",
        created_at=datetime(2026, 5, 1, 10, 0, tzinfo=_TPE),
        review_id=None,
        priority="medium",
        description="改動描述.",
        motivation="動機 — metrics.json#/sharpe baseline.",
        diff_draft="```diff\n+ x\n```",
        expected_impact="影響.",
        risk_assessment="風險.",
        validation_plan="WFA 5+1.",
        expected_improvement="0.55 → 0.60.",
    )


def _make_validating_proposal(root: Path, *, topic: str = "validate-x") -> Path:
    path = write_proposal(_make_draft(topic), root)
    return transition_proposal(path, "validating", actor="setup")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def proposals_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    root = tmp_path / "proposals"
    root.mkdir()
    monkeypatch.setattr(
        proposals_route, "_PROPOSALS_ROOT_FACTORY", lambda: root
    )
    return root


@pytest.fixture()
def loader_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[dict[str, list[BarRow]]], None]:
    """Install a synthetic ``_MARKET_DATA_LOADER_FACTORY`` per test."""

    def install(bars_by_symbol: dict[str, list[BarRow]]) -> None:
        def loader(sym: str, _s: str, _e: str) -> list[BarRow]:
            return bars_by_symbol.get(sym, [])

        monkeypatch.setattr(
            proposals_route, "_MARKET_DATA_LOADER_FACTORY", lambda: loader
        )

    return install


@pytest.fixture()
def client_factory() -> Callable[..., AsyncClient]:
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


def _valid_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "strategy": "sma_cross",
        "period": {"from": "2025-01-02", "to": "2025-12-30"},
        "param_overrides": ["fast=10"],
        "universe": ["2330"],
        "wfa_windows": 5,
        "in_sample_ratio": 0.7,
        "initial_capital": 1_000_000,
        "dry_run": False,
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# 7.4 — auth
# ---------------------------------------------------------------------------


async def test_validate_unauthenticated_returns_401(
    client_factory: Callable[..., AsyncClient], proposals_root: Path
) -> None:
    async with client_factory(headers={}) as c:
        r = await c.post(
            "/api/admin/proposals/anything/validate",
            json=_valid_body(),
        )
    assert r.status_code == 401
    assert r.json()["error"]["code"] in {"auth_missing", "auth_invalid"}


# ---------------------------------------------------------------------------
# 7.5 — path traversal slug
# ---------------------------------------------------------------------------


async def test_validate_path_traversal_slug_returns_400(
    client_factory: Callable[..., AsyncClient], proposals_root: Path
) -> None:
    async with client_factory() as c:
        # ``..%2Fetc`` decoded by Starlette → ``../etc`` → contains "..".
        r = await c.post(
            "/api/admin/proposals/..%2Fetc/validate",
            json=_valid_body(),
        )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "invalid_input"


# ---------------------------------------------------------------------------
# 7.6 — unknown slug
# ---------------------------------------------------------------------------


async def test_validate_unknown_slug_returns_404(
    client_factory: Callable[..., AsyncClient], proposals_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.post(
            "/api/admin/proposals/does-not-exist/validate",
            json=_valid_body(),
        )
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "not_found"


# ---------------------------------------------------------------------------
# 7.7–7.10 — body validation (pydantic ValidationError → 422)
# ---------------------------------------------------------------------------


async def test_validate_malformed_body_missing_strategy_returns_422(
    client_factory: Callable[..., AsyncClient], proposals_root: Path
) -> None:
    slug = _make_validating_proposal(proposals_root).stem
    body = _valid_body()
    body.pop("strategy")
    async with client_factory() as c:
        r = await c.post(f"/api/admin/proposals/{slug}/validate", json=body)
    assert r.status_code == 422, r.text


async def test_validate_body_extra_field_returns_422(
    client_factory: Callable[..., AsyncClient], proposals_root: Path
) -> None:
    slug = _make_validating_proposal(proposals_root).stem
    body = _valid_body()
    body["async"] = True
    async with client_factory() as c:
        r = await c.post(f"/api/admin/proposals/{slug}/validate", json=body)
    assert r.status_code == 422, r.text


async def test_validate_inverted_period_returns_422(
    client_factory: Callable[..., AsyncClient], proposals_root: Path
) -> None:
    slug = _make_validating_proposal(proposals_root).stem
    body = _valid_body(period={"from": "2025-12-30", "to": "2025-01-02"})
    async with client_factory() as c:
        r = await c.post(f"/api/admin/proposals/{slug}/validate", json=body)
    assert r.status_code == 422, r.text


async def test_validate_empty_universe_returns_422(
    client_factory: Callable[..., AsyncClient], proposals_root: Path
) -> None:
    slug = _make_validating_proposal(proposals_root).stem
    body = _valid_body(universe=[])
    async with client_factory() as c:
        r = await c.post(f"/api/admin/proposals/{slug}/validate", json=body)
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# 7.11 — unparseable param
# ---------------------------------------------------------------------------


async def test_validate_unparseable_param_returns_400(
    client_factory: Callable[..., AsyncClient],
    proposals_root: Path,
    loader_factory: Callable[[dict[str, list[BarRow]]], None],
) -> None:
    slug = _make_validating_proposal(proposals_root).stem
    loader_factory({"2330": _synthetic_bars(253)})
    body = _valid_body(param_overrides=["foo=bar%bad"])
    async with client_factory() as c:
        r = await c.post(f"/api/admin/proposals/{slug}/validate", json=body)
    assert r.status_code == 400, r.text
    payload = r.json()
    assert payload["error"]["code"] == "invalid_input"
    assert "unparseable_param" in payload["error"]["message"]


# ---------------------------------------------------------------------------
# 7.12 — happy pass
# ---------------------------------------------------------------------------


async def test_validate_pass_returns_200_with_envelope(
    client_factory: Callable[..., AsyncClient],
    proposals_root: Path,
    loader_factory: Callable[[dict[str, list[BarRow]]], None],
) -> None:
    slug = _make_validating_proposal(proposals_root).stem
    loader_factory({"2330": _synthetic_bars(253)})
    async with client_factory() as c:
        r = await c.post(
            f"/api/admin/proposals/{slug}/validate",
            json=_valid_body(),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["verdict"] == "pass"
    # Manual-verdict mode (proposal-manual-verdict): the proposal stays in
    # validating; the operator approves via the transition endpoint.
    assert data["new_status"] == "validating"
    assert data["new_path"] is None
    assert data["report_path"] == f"{slug}.validation.json"
    assert data["failures"] == []
    assert set(data["deltas"].keys()) == {"sharpe", "max_drawdown", "win_rate"}

    staying_md = proposals_root / f"{slug}.md"
    report = proposals_root / f"{slug}.validation.json"
    assert staying_md.is_file()
    assert "status: validating" in staying_md.read_text(encoding="utf-8")
    assert report.is_file()
    assert not (proposals_root / "PENDING_REVIEW" / f"{slug}.md").exists()


# ---------------------------------------------------------------------------
# 7.13 — happy fail
# ---------------------------------------------------------------------------


async def test_validate_fail_returns_200_with_failures(
    client_factory: Callable[..., AsyncClient],
    proposals_root: Path,
    loader_factory: Callable[[dict[str, list[BarRow]]], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slug = _make_validating_proposal(proposals_root).stem
    loader_factory({"2330": _synthetic_bars(253)})

    # Craft per-window metrics so candidate IS/OOS Sharpe gap = 0.75 (> 0.30).
    call_state = {"i": 0}

    def fake_run_one(
        _strategy: Any, _bars: Any, _period: Any, _capital: Any
    ) -> dict[str, float]:
        idx = call_state["i"] % 4
        call_state["i"] += 1
        if idx == 0:
            return {"sharpe": 1.0, "max_drawdown": -0.05, "win_rate": 0.5}
        if idx == 1:
            return {"sharpe": 1.0, "max_drawdown": -0.05, "win_rate": 0.5}
        if idx == 2:
            return {"sharpe": 2.0, "max_drawdown": -0.05, "win_rate": 0.5}
        return {"sharpe": 0.5, "max_drawdown": -0.05, "win_rate": 0.5}

    monkeypatch.setattr(wfa_module, "_run_one", fake_run_one)

    async with client_factory() as c:
        r = await c.post(
            f"/api/admin/proposals/{slug}/validate",
            json=_valid_body(),
        )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["verdict"] == "fail"
    # Manual-verdict mode: fail no longer auto-rejects — the operator
    # reviews the report and rejects via the transition endpoint.
    assert data["new_status"] == "validating"
    assert data["new_path"] is None
    assert data["report_path"] == f"{slug}.validation.json"
    assert len(data["failures"]) >= 1
    assert any("sharpe_gap" in f for f in data["failures"])
    assert (proposals_root / f"{slug}.md").is_file()
    assert not (proposals_root / "rejected" / f"{slug}.md").exists()


# ---------------------------------------------------------------------------
# 7.14 — dry-run keeps state at validating
# ---------------------------------------------------------------------------


async def test_validate_dry_run_keeps_validating_and_paths_null(
    client_factory: Callable[..., AsyncClient],
    proposals_root: Path,
    loader_factory: Callable[[dict[str, list[BarRow]]], None],
) -> None:
    proposal_path = _make_validating_proposal(proposals_root)
    slug = proposal_path.stem
    loader_factory({"2330": _synthetic_bars(253)})

    async with client_factory() as c:
        r = await c.post(
            f"/api/admin/proposals/{slug}/validate",
            json=_valid_body(dry_run=True),
        )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["new_status"] == "validating"
    assert data["new_path"] is None
    assert data["report_path"] is None

    # On-disk state untouched.
    assert proposal_path.is_file()
    text = proposal_path.read_text(encoding="utf-8")
    assert "status: validating" in text
    assert not (proposals_root / f"{slug}.validation.json").exists()
    assert not (
        proposals_root / "PENDING_REVIEW" / f"{slug}.validation.json"
    ).exists()


# ---------------------------------------------------------------------------
# 7.15 — pending status → 409 illegal_transition
# ---------------------------------------------------------------------------


async def test_validate_pending_status_returns_409_illegal_transition(
    client_factory: Callable[..., AsyncClient],
    proposals_root: Path,
    loader_factory: Callable[[dict[str, list[BarRow]]], None],
) -> None:
    pending_path = write_proposal(_make_draft(), proposals_root)
    slug = pending_path.stem
    loader_factory({"2330": _synthetic_bars(253)})

    async with client_factory() as c:
        r = await c.post(
            f"/api/admin/proposals/{slug}/validate",
            json=_valid_body(),
        )
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["code"] == "illegal_transition"
    assert "status_not_validating" in err["message"]

    # Proposal stays put — no transition fired.
    assert pending_path.is_file()


# ---------------------------------------------------------------------------
# 7.16 — unknown strategy → 422 wfa_validation_failed
# ---------------------------------------------------------------------------


async def test_validate_unknown_strategy_returns_422_wfa_validation_failed(
    client_factory: Callable[..., AsyncClient],
    proposals_root: Path,
    loader_factory: Callable[[dict[str, list[BarRow]]], None],
) -> None:
    slug = _make_validating_proposal(proposals_root).stem
    loader_factory({"2330": _synthetic_bars(253)})

    async with client_factory() as c:
        r = await c.post(
            f"/api/admin/proposals/{slug}/validate",
            json=_valid_body(strategy="made_up"),
        )
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "wfa_validation_failed"
    assert "unknown_strategy" in err["message"]


# ---------------------------------------------------------------------------
# 7.17 — missing bars → 422 wfa_validation_failed
# ---------------------------------------------------------------------------


async def test_validate_missing_bars_returns_422_wfa_validation_failed(
    client_factory: Callable[..., AsyncClient],
    proposals_root: Path,
    loader_factory: Callable[[dict[str, list[BarRow]]], None],
) -> None:
    slug = _make_validating_proposal(proposals_root).stem
    loader_factory({})  # any symbol → empty list

    async with client_factory() as c:
        r = await c.post(
            f"/api/admin/proposals/{slug}/validate",
            json=_valid_body(),
        )
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "wfa_validation_failed"
    assert err["message"].startswith("missing_bars")


# ---------------------------------------------------------------------------
# 7.18 — period_too_short → 422 wfa_validation_failed
# ---------------------------------------------------------------------------


async def test_validate_period_too_short_returns_422(
    client_factory: Callable[..., AsyncClient],
    proposals_root: Path,
    loader_factory: Callable[[dict[str, list[BarRow]]], None],
) -> None:
    slug = _make_validating_proposal(proposals_root).stem
    loader_factory({"2330": _synthetic_bars(30)})
    body = _valid_body(period={"from": "2025-01-02", "to": "2025-01-15"})

    async with client_factory() as c:
        r = await c.post(f"/api/admin/proposals/{slug}/validate", json=body)
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "wfa_validation_failed"
    assert "period_too_short" in err["message"]


# ---------------------------------------------------------------------------
# 7.19 — GET on validate path → 405
# ---------------------------------------------------------------------------


async def test_validate_get_on_validate_returns_405(
    client_factory: Callable[..., AsyncClient], proposals_root: Path
) -> None:
    slug = _make_validating_proposal(proposals_root).stem
    async with client_factory() as c:
        r = await c.get(f"/api/admin/proposals/{slug}/validate")
    assert r.status_code == 405
    assert r.headers.get("Allow", "").upper().find("POST") != -1
