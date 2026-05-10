"""HTTP tests for /api/admin/proposals endpoints (list, detail, transition).

Spec scenarios covered (admin-proposals-endpoints):

* List endpoint shape (200, 5 items sorted by created_at desc, pagination
  fields, status filter, source-of-truth, malformed file silent skip,
  limit clamp <=200, negative offset 400).
* Detail endpoint shape (200 with full body + parsed changelog, extra
  frontmatter for merged/rejected files, 404 for missing slug, 422 for
  malformed body, 400 for path-traversal slugs).
* Transition endpoint (200 for legal edges with file move + frontmatter
  update + changelog line, 409 illegal_transition, 400
  missing_validation_report / unknown_status, 409 destination_exists, 404
  for missing slug, 405 for GET).
* 401 auth_missing / auth_invalid on all 3 endpoints.
* Parametrised test pinning every row of _STATE_ERROR_TO_ENVELOPE.

Spec: openspec/changes/admin-proposals-endpoints-and-pages/specs/admin-proposals-endpoints/spec.md
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from ohmystock.api.app import create_app
from ohmystock.api.routes import proposals as routes_proposals
from ohmystock.proposal import (
    ProposalDraft,
    ProposalStateError,
    transition_proposal,
    write_proposal,
)
from tests.conftest import VALID_ADMIN_TOKEN


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures - proposals_tmp_root + AsyncClient factory
# ---------------------------------------------------------------------------


def _make_draft(
    *,
    topic: str,
    created_at: datetime,
    motivation_pointer: str = "see metrics.json#/sharpe for baseline",
    priority: str = "medium",
    review_id: str | None = None,
) -> ProposalDraft:
    """Build a minimal valid ProposalDraft for fixtures."""
    return ProposalDraft(
        topic=topic,
        target_section="cheatsheet §6.6",
        created_by="mark",
        created_at=created_at,
        review_id=review_id,
        priority=priority,  # type: ignore[arg-type]
        description="改動描述 body text.",
        motivation=f"動機 — {motivation_pointer}",
        diff_draft="```diff\n+ new line\n```",
        expected_impact="影響範圍 body.",
        risk_assessment="風險評估 body.",
        validation_plan="驗證計畫 body.",
        expected_improvement="預期改善 body.",
    )


@pytest.fixture()
def proposals_tmp_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Create tmp_path/proposals + 5 fixture proposals (one per status).

    Slugs:
      2026-04-30-pending-x      -> pending  (root)
      2026-05-01-validating-x   -> validating (root)
      2026-05-02-approved-x     -> approved (PENDING_REVIEW/)
      2026-05-03-merged-x       -> merged (merged/)
      2026-05-04-rejected-x     -> rejected (rejected/)
    """
    root = tmp_path / "proposals"
    root.mkdir()

    monkeypatch.setattr(
        routes_proposals, "_PROPOSALS_ROOT_FACTORY", lambda: root
    )

    tz = timezone.utc

    pending_draft = _make_draft(
        topic="pending-x",
        created_at=datetime(2026, 4, 30, 10, 0, tzinfo=tz),
    )
    write_proposal(pending_draft, root)

    validating_draft = _make_draft(
        topic="validating-x",
        created_at=datetime(2026, 5, 1, 10, 0, tzinfo=tz),
    )
    v_path = write_proposal(validating_draft, root)
    transition_proposal(v_path, "validating", actor="mark")

    approved_draft = _make_draft(
        topic="approved-x",
        created_at=datetime(2026, 5, 2, 10, 0, tzinfo=tz),
    )
    a_path = write_proposal(approved_draft, root)
    a_path = transition_proposal(a_path, "validating", actor="mark")
    transition_proposal(
        a_path,
        "approved",
        actor="mark",
        validation_report_path=Path("reports/approved-x.json"),
    )

    merged_draft = _make_draft(
        topic="merged-x",
        created_at=datetime(2026, 5, 3, 10, 0, tzinfo=tz),
    )
    m_path = write_proposal(merged_draft, root)
    m_path = transition_proposal(m_path, "validating", actor="mark")
    m_path = transition_proposal(
        m_path,
        "approved",
        actor="mark",
        validation_report_path=Path("reports/merged-x.json"),
    )
    transition_proposal(
        m_path, "merged", actor="mark", merged_to_version="v3.1"
    )

    rejected_draft = _make_draft(
        topic="rejected-x",
        created_at=datetime(2026, 5, 4, 10, 0, tzinfo=tz),
    )
    r_path = write_proposal(rejected_draft, root)
    r_path = transition_proposal(r_path, "validating", actor="mark")
    transition_proposal(
        r_path, "rejected", actor="mark", reason="Sharpe drop > 30%"
    )

    return root


@pytest.fixture()
def client_factory():
    """Build an AsyncClient bound to a fresh app + valid Bearer token by default."""

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
# §6.2 - list 200 shape
# ---------------------------------------------------------------------------


async def test_list_200_shape_5_items_sorted_desc(
    client_factory, proposals_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/proposals")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["total"] == 5
    assert data["limit"] == 50
    assert data["offset"] == 0
    assert data["has_more"] is False
    items = data["items"]
    assert len(items) == 5
    iso_dates = [i["created_at"] for i in items]
    assert iso_dates == sorted(iso_dates, reverse=True)
    expected_keys = {
        "slug",
        "proposal_id",
        "status",
        "topic",
        "target_section",
        "created_by",
        "created_at",
        "review_id",
        "priority",
    }
    for item in items:
        assert set(item.keys()) == expected_keys


# ---------------------------------------------------------------------------
# §6.3 - list ?status=approved filter
# ---------------------------------------------------------------------------


async def test_list_status_filter_returns_one_item(
    client_factory, proposals_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/proposals?status=approved")
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["status"] == "approved"


# ---------------------------------------------------------------------------
# §6.4 - list ?status=approve typo -> 400
# ---------------------------------------------------------------------------


async def test_list_invalid_status_typo_returns_400(
    client_factory, proposals_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/proposals?status=approve")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_input"


# ---------------------------------------------------------------------------
# §6.5 - malformed file silently skipped + warning logged
# ---------------------------------------------------------------------------


async def test_list_malformed_file_skipped_and_logged(
    client_factory,
    proposals_tmp_root: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    (proposals_tmp_root / "broken.md").write_text(
        "no frontmatter at all\n", encoding="utf-8"
    )
    caplog.set_level("WARNING", logger="ohmystock.api.routes.proposals")
    async with client_factory() as c:
        r = await c.get("/api/admin/proposals")
    assert r.status_code == 200
    assert r.json()["data"]["total"] == 5  # malformed not counted
    assert any(
        "skipping malformed proposal" in rec.getMessage()
        for rec in caplog.records
    )


# ---------------------------------------------------------------------------
# §6.6 - status is source-of-truth, not directory
# ---------------------------------------------------------------------------


async def test_list_status_filter_source_of_truth(
    client_factory, proposals_tmp_root: Path
) -> None:
    """A pending-frontmatter file under merged/ shows under ?status=pending."""
    misplaced = proposals_tmp_root / "merged" / "2026-05-05-misplaced.md"
    misplaced.write_text(
        "---\n"
        "proposal_id: 2026-05-05-misplaced\n"
        "target_section: x\n"
        "status: pending\n"
        "created_by: mark\n"
        "created_at: 2026-05-05T10:00:00+08:00\n"
        "review_id: null\n"
        "priority: low\n"
        "---\n\n"
        "## 1. 改動描述\n\nbody\n\n"
        "## 2. 動機與佐證\n\nsee metrics.json# baseline\n\n"
        "## 3. 改動 diff 草稿\n\n```diff\n+x\n```\n\n"
        "## 4. 預期影響範圍\n\nbody\n\n"
        "## 5. 風險評估\n\nbody\n\n"
        "## 6. 驗證計畫\n\nbody\n\n"
        "## 7. 預期改善幅度\n\nbody\n\n"
        "## 8. 變更紀錄\n- 2026-05-05T10:00:00+08:00 created by mark\n",
        encoding="utf-8",
    )

    async with client_factory() as c:
        r_pending = await c.get("/api/admin/proposals?status=pending")
        r_merged = await c.get("/api/admin/proposals?status=merged")

    pending_slugs = {i["slug"] for i in r_pending.json()["data"]["items"]}
    merged_slugs = {i["slug"] for i in r_merged.json()["data"]["items"]}
    assert "2026-05-05-misplaced" in pending_slugs
    assert "2026-05-05-misplaced" not in merged_slugs


# ---------------------------------------------------------------------------
# §6.7 - pagination clamps
# ---------------------------------------------------------------------------


async def test_list_limit_clamps_to_200(
    client_factory, proposals_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/proposals?limit=10000")
    assert r.status_code == 200
    assert r.json()["data"]["limit"] == 200


async def test_list_negative_offset_returns_400(
    client_factory, proposals_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/proposals?offset=-1")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_input"


# ---------------------------------------------------------------------------
# §6.8 - detail 200 full payload (pending fixture)
# ---------------------------------------------------------------------------


async def test_detail_200_full_payload(
    client_factory, proposals_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/proposals/2026-04-30-pending-x")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["slug"] == "2026-04-30-pending-x"
    assert data["proposal_id"] == "2026-04-30-pending-x"
    assert data["status"] == "pending"
    assert data["topic"] == "pending-x"
    assert data["body"]["description"] == "改動描述 body text."
    assert "metrics.json#" in data["body"]["motivation"]
    assert isinstance(data["changelog"], list)
    assert len(data["changelog"]) >= 1
    assert data["changelog"][0]["kind"] == "created"
    assert data["extra_frontmatter"] == {}


# ---------------------------------------------------------------------------
# §6.9 - detail of a transitioned (validating) file shows transition entry
# ---------------------------------------------------------------------------


async def test_detail_transitioned_file_changelog_has_transition(
    client_factory, proposals_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/proposals/2026-05-01-validating-x")
    assert r.status_code == 200
    data = r.json()["data"]
    transitions = [e for e in data["changelog"] if e["kind"] == "transition"]
    assert len(transitions) >= 1
    t = transitions[0]
    assert t["from_status"] == "pending"
    assert t["to_status"] == "validating"
    assert t["actor"] == "mark"


# ---------------------------------------------------------------------------
# §6.10 - detail of rejected file: reason populated + extra_frontmatter
# ---------------------------------------------------------------------------


async def test_detail_rejected_file_carries_reason(
    client_factory, proposals_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/proposals/2026-05-04-rejected-x")
    assert r.status_code == 200
    data = r.json()["data"]
    last_transition = [
        e for e in data["changelog"] if e["kind"] == "transition"
    ][-1]
    assert last_transition["reason"] == "Sharpe drop > 30%"
    assert "rejected_reason" in data["extra_frontmatter"]
    assert data["extra_frontmatter"]["rejected_reason"] == "Sharpe drop > 30%"


# ---------------------------------------------------------------------------
# §6.11 - detail of merged file: extra_frontmatter
# ---------------------------------------------------------------------------


async def test_detail_merged_file_has_merged_metadata(
    client_factory, proposals_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/proposals/2026-05-03-merged-x")
    assert r.status_code == 200
    extra = r.json()["data"]["extra_frontmatter"]
    assert "merged_to_version" in extra
    assert extra["merged_to_version"] == "v3.1"
    assert "merged_at" in extra
    assert "rejected_reason" not in extra


# ---------------------------------------------------------------------------
# §6.12 - detail 404 for well-formed but missing slug
# ---------------------------------------------------------------------------


async def test_detail_404_for_missing_slug(
    client_factory, proposals_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/proposals/2099-12-31-does-not-exist")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert "2099-12-31-does-not-exist" in body["error"]["message"]


# ---------------------------------------------------------------------------
# §6.13 - detail 422 for malformed body section
# ---------------------------------------------------------------------------


async def test_detail_422_for_missing_body_section(
    client_factory, proposals_tmp_root: Path
) -> None:
    """Strip the ## 5. section to force a ProposalParseError."""
    target = proposals_tmp_root / "2026-04-30-pending-x.md"
    text = target.read_text(encoding="utf-8")
    new_text: list[str] = []
    skip = False
    for line in text.split("\n"):
        if line.startswith("## 5. "):
            skip = True
            continue
        if skip and line.startswith("## ") and not line.startswith("## 5. "):
            skip = False
        if not skip:
            new_text.append(line)
    target.write_text("\n".join(new_text), encoding="utf-8")

    async with client_factory() as c:
        r = await c.get("/api/admin/proposals/2026-04-30-pending-x")
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["error"]["code"] == "malformed_proposal"
    assert "Traceback" not in r.text


# ---------------------------------------------------------------------------
# §6.14 - detail 400 invalid_input for path-traversal slugs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw_slug",
    [
        "foo%2Fbar",  # decodes to foo/bar
        "..%2Fsecrets",  # decodes to ../secrets
        "foo%5Cbar",  # decodes to foo\bar
        "foo..bar",  # contains ..
    ],
)
async def test_detail_rejects_path_traversal_400(
    client_factory, proposals_tmp_root: Path, raw_slug: str
) -> None:
    async with client_factory() as c:
        r = await c.get(f"/api/admin/proposals/{raw_slug}")
    assert r.status_code == 400, (raw_slug, r.text)
    assert r.json()["error"]["code"] == "invalid_input"


async def test_path_traversal_does_not_open_file(
    client_factory,
    proposals_tmp_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    real_read = Path.read_text
    real_is_file = Path.is_file

    def trap_read(self: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(f"read_text:{self}")
        return real_read(self, *args, **kwargs)

    def trap_is_file(self: Path) -> bool:
        calls.append(f"is_file:{self}")
        return real_is_file(self)

    monkeypatch.setattr(Path, "read_text", trap_read)
    monkeypatch.setattr(Path, "is_file", trap_is_file)

    async with client_factory() as c:
        r = await c.get("/api/admin/proposals/foo%2Fbar")

    assert r.status_code == 400
    assert not any(
        str(proposals_tmp_root) in call for call in calls
    ), calls


# ---------------------------------------------------------------------------
# §6.15 - transition 200 pending -> validating
# ---------------------------------------------------------------------------


async def test_transition_pending_to_validating_200(
    client_factory, proposals_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.post(
            "/api/admin/proposals/2026-04-30-pending-x/transition",
            content=json.dumps({"new_status": "validating", "actor": "mark"}),
            headers={
                "Authorization": f"Bearer {VALID_ADMIN_TOKEN}",
                "Content-Type": "application/json",
            },
        )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["new_status"] == "validating"
    assert data["new_path"] == "2026-04-30-pending-x.md"
    assert "\\" not in data["new_path"]
    on_disk = (proposals_tmp_root / "2026-04-30-pending-x.md").read_text(
        encoding="utf-8"
    )
    assert "status: validating" in on_disk
    assert "status: pending → validating by mark" in on_disk


# ---------------------------------------------------------------------------
# §6.16 - transition 200 validating -> approved (file moves)
# ---------------------------------------------------------------------------


async def test_transition_validating_to_approved_moves_file(
    client_factory, proposals_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.post(
            "/api/admin/proposals/2026-05-01-validating-x/transition",
            content=json.dumps(
                {
                    "new_status": "approved",
                    "actor": "mark",
                    "validation_report_path": "reports/v.json",
                }
            ),
            headers={
                "Authorization": f"Bearer {VALID_ADMIN_TOKEN}",
                "Content-Type": "application/json",
            },
        )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["new_path"] == "PENDING_REVIEW/2026-05-01-validating-x.md"
    assert not (proposals_tmp_root / "2026-05-01-validating-x.md").exists()
    moved = proposals_tmp_root / "PENDING_REVIEW" / "2026-05-01-validating-x.md"
    assert moved.exists()
    text = moved.read_text(encoding="utf-8")
    assert "status: approved" in text
    assert "validation_report_path: reports" in text


# ---------------------------------------------------------------------------
# §6.17 - transition 409 illegal_transition (pending -> approved)
# ---------------------------------------------------------------------------


async def test_transition_pending_to_approved_409(
    client_factory, proposals_tmp_root: Path
) -> None:
    target = proposals_tmp_root / "2026-04-30-pending-x.md"
    before = target.read_text(encoding="utf-8")
    async with client_factory() as c:
        r = await c.post(
            "/api/admin/proposals/2026-04-30-pending-x/transition",
            content=json.dumps(
                {
                    "new_status": "approved",
                    "actor": "mark",
                    "validation_report_path": "x.json",
                }
            ),
            headers={
                "Authorization": f"Bearer {VALID_ADMIN_TOKEN}",
                "Content-Type": "application/json",
            },
        )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "illegal_transition"
    assert target.read_text(encoding="utf-8") == before


# ---------------------------------------------------------------------------
# §6.18 - transition 400 missing_validation_report
# ---------------------------------------------------------------------------


async def test_transition_validating_to_approved_missing_report_400(
    client_factory, proposals_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.post(
            "/api/admin/proposals/2026-05-01-validating-x/transition",
            content=json.dumps({"new_status": "approved", "actor": "mark"}),
            headers={
                "Authorization": f"Bearer {VALID_ADMIN_TOKEN}",
                "Content-Type": "application/json",
            },
        )
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["error"]["code"] == "invalid_input"
    assert "missing_validation_report" in body["error"]["message"]


# ---------------------------------------------------------------------------
# §6.19 - transition 409 destination_exists (conflict)
# ---------------------------------------------------------------------------


async def test_transition_destination_exists_409(
    client_factory, proposals_tmp_root: Path
) -> None:
    sink = proposals_tmp_root / "PENDING_REVIEW"
    sink.mkdir(exist_ok=True)
    stale = sink / "2026-05-01-validating-x.md"
    stale.write_text("stale content\n", encoding="utf-8")

    src = proposals_tmp_root / "2026-05-01-validating-x.md"
    src_before = src.read_text(encoding="utf-8")

    async with client_factory() as c:
        r = await c.post(
            "/api/admin/proposals/2026-05-01-validating-x/transition",
            content=json.dumps(
                {
                    "new_status": "approved",
                    "actor": "mark",
                    "validation_report_path": "x.json",
                }
            ),
            headers={
                "Authorization": f"Bearer {VALID_ADMIN_TOKEN}",
                "Content-Type": "application/json",
            },
        )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "conflict"
    assert src.read_text(encoding="utf-8") == src_before
    assert stale.read_text(encoding="utf-8") == "stale content\n"


# ---------------------------------------------------------------------------
# §6.20 - transition 400/422 for unknown_status (typo)
# ---------------------------------------------------------------------------


async def test_transition_unknown_status_rejected(
    client_factory, proposals_tmp_root: Path
) -> None:
    """pydantic Literal mismatch returns 422 from FastAPI's default
    validation envelope. We accept either 400 invalid_input (route-level)
    or 422 (FastAPI default) - both are non-200 and the file on disk is
    untouched, which is the externally-promised contract.
    """
    target = proposals_tmp_root / "2026-04-30-pending-x.md"
    before = target.read_text(encoding="utf-8")
    async with client_factory() as c:
        r = await c.post(
            "/api/admin/proposals/2026-04-30-pending-x/transition",
            content=json.dumps({"new_status": "approve", "actor": "mark"}),
            headers={
                "Authorization": f"Bearer {VALID_ADMIN_TOKEN}",
                "Content-Type": "application/json",
            },
        )
    assert r.status_code in (400, 422), r.text
    assert target.read_text(encoding="utf-8") == before


# ---------------------------------------------------------------------------
# §6.21 - transition 404 missing slug + 405 GET on transition path
# ---------------------------------------------------------------------------


async def test_transition_missing_slug_404(
    client_factory, proposals_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.post(
            "/api/admin/proposals/2099-99-99-missing/transition",
            content=json.dumps({"new_status": "validating", "actor": "mark"}),
            headers={
                "Authorization": f"Bearer {VALID_ADMIN_TOKEN}",
                "Content-Type": "application/json",
            },
        )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


async def test_get_on_transition_path_returns_405(
    client_factory, proposals_tmp_root: Path
) -> None:
    async with client_factory() as c:
        r = await c.get(
            "/api/admin/proposals/2026-04-30-pending-x/transition"
        )
    assert r.status_code == 405


# ---------------------------------------------------------------------------
# §6.22 - 401 auth_missing / auth_invalid on all 3 endpoints
# ---------------------------------------------------------------------------


async def test_list_no_auth_returns_401(client_factory) -> None:
    async with client_factory(headers={}) as c:
        r = await c.get("/api/admin/proposals")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "auth_missing"


async def test_list_wrong_token_returns_401(client_factory) -> None:
    async with client_factory(headers={"Authorization": "Bearer wrong"}) as c:
        r = await c.get("/api/admin/proposals")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "auth_invalid"


async def test_detail_no_auth_returns_401(
    client_factory, proposals_tmp_root: Path
) -> None:
    async with client_factory(headers={}) as c:
        r = await c.get("/api/admin/proposals/2026-04-30-pending-x")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "auth_missing"


async def test_transition_no_auth_returns_401(
    client_factory, proposals_tmp_root: Path
) -> None:
    async with client_factory(headers={}) as c:
        r = await c.post(
            "/api/admin/proposals/2026-04-30-pending-x/transition",
            content=json.dumps({"new_status": "validating", "actor": "mark"}),
            headers={"Content-Type": "application/json"},
        )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "auth_missing"


async def test_transition_wrong_token_returns_401(
    client_factory, proposals_tmp_root: Path
) -> None:
    async with client_factory(headers={"Authorization": "Bearer wrong"}) as c:
        r = await c.post(
            "/api/admin/proposals/2026-04-30-pending-x/transition",
            content=json.dumps({"new_status": "validating", "actor": "mark"}),
            headers={"Content-Type": "application/json"},
        )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "auth_invalid"
    on_disk = (proposals_tmp_root / "2026-04-30-pending-x.md").read_text(
        encoding="utf-8"
    )
    assert "status: pending" in on_disk


# ---------------------------------------------------------------------------
# §6.23 - parametrised: every row of _STATE_ERROR_TO_ENVELOPE
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "substring,expected_status,expected_code",
    [
        ("unknown_status: bogus", 400, "invalid_input"),
        ("illegal_transition: pending -> approved", 409, "illegal_transition"),
        ("missing_actor: empty", 400, "invalid_input"),
        ("missing_validation_report: required", 400, "invalid_input"),
        ("missing_merged_to_version: required", 400, "invalid_input"),
        ("missing_rejection_reason: empty", 400, "invalid_input"),
        ("destination_exists: target exists", 409, "conflict"),
        ("malformed_changelog: missing heading", 422, "unprocessable_entity"),
    ],
)
async def test_state_error_envelope_mapping_each_row(
    client_factory,
    proposals_tmp_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    substring: str,
    expected_status: int,
    expected_code: str,
) -> None:
    """Pin _STATE_ERROR_TO_ENVELOPE: each substring -> expected envelope row."""

    def fake_transition(*args: Any, **kwargs: Any) -> Path:
        raise ProposalStateError(substring)

    monkeypatch.setattr(routes_proposals, "transition_proposal", fake_transition)

    async with client_factory() as c:
        r = await c.post(
            "/api/admin/proposals/2026-04-30-pending-x/transition",
            content=json.dumps({"new_status": "validating", "actor": "mark"}),
            headers={
                "Authorization": f"Bearer {VALID_ADMIN_TOKEN}",
                "Content-Type": "application/json",
            },
        )
    assert r.status_code == expected_status, (substring, r.text)
    assert r.json()["error"]["code"] == expected_code
