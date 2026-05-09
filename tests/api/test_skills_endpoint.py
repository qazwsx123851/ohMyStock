"""HTTP tests for ``GET /api/admin/skills`` and ``GET /api/admin/skills/{name}``.

Spec scenarios covered (admin-skills-endpoints):

* List endpoint shape (200, alphabetical, key whitelist, body_truncated flag).
* Detail endpoint shape (200, full body, order-preserved cited_specs).
* 400 ``invalid_input`` for path-traversal names — validated BEFORE disk I/O.
* 404 ``not_found`` for well-formed but missing skill.
* 401 ``auth_missing`` / ``auth_invalid`` on both endpoints.
* 405 on POST/PUT.
* Token-tuple equality invariant against ``loader._INVALID_NAME_TOKENS``.
* Production registry sanity (10 seed skills + ``market-data`` description).
* Loader error → 500 envelope without traceback leakage.

Spec: openspec/changes/web-admin-skills-pages/specs/admin-skills-endpoints/spec.md
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from ohmystock.api.app import create_app
from ohmystock.api.routes import skills as routes_skills
from ohmystock.skills import loader as skills_loader
from tests.conftest import VALID_ADMIN_TOKEN


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_SHORT_BODY = "# Short\nA single-line body well under 200 chars.\n"
_LONG_BODY = "# Long\n" + ("台股 daily bars 與技術指標 " * 50)  # >> 200 chars
_NO_CITED_BODY = "# No cited specs\nBody without referenced specs.\n"


def _write_skill(
    dirpath: Path,
    *,
    name: str,
    description: str,
    category: str,
    cited_specs: list[str],
    body: str,
) -> None:
    """Write a valid skill ``.md`` file (frontmatter + body) into ``dirpath``."""
    if cited_specs:
        cited_yaml = "\n".join(f"  - {c}" for c in cited_specs)
        cited_block = "cited_specs:\n" + cited_yaml
    else:
        # Flow-style empty list so pyyaml returns [] not None
        cited_block = "cited_specs: []"
    text = (
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        f"category: {category}\n"
        f"{cited_block}\n"
        "---\n"
        f"{body}"
    )
    (dirpath / f"{name}.md").write_text(text, encoding="utf-8")


@pytest.fixture()
def fake_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Three valid skills covering the truncation + empty-cited-specs paths."""
    _write_skill(
        tmp_path,
        name="alpha",
        description="alpha desc",
        category="data",
        cited_specs=["spec-one", "spec-two"],
        body=_SHORT_BODY,
    )
    _write_skill(
        tmp_path,
        name="beta",
        description="beta long-body desc",
        category="indicator",
        cited_specs=["spec-three"],
        body=_LONG_BODY,
    )
    _write_skill(
        tmp_path,
        name="gamma",
        description="gamma no cited",
        category="tool",
        cited_specs=[],
        body=_NO_CITED_BODY,
    )
    monkeypatch.setattr(routes_skills, "_REGISTRY_DIR", tmp_path)
    return tmp_path


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
# Auth
# ---------------------------------------------------------------------------


async def test_list_no_auth_returns_401(client_factory) -> None:
    async with client_factory(headers={}) as c:
        r = await c.get("/api/admin/skills")
    assert r.status_code == 401
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "auth_missing"


async def test_list_wrong_token_returns_401(client_factory) -> None:
    async with client_factory(headers={"Authorization": "Bearer wrong"}) as c:
        r = await c.get("/api/admin/skills")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "auth_invalid"


async def test_detail_no_auth_returns_401(client_factory, fake_registry) -> None:
    async with client_factory(headers={}) as c:
        r = await c.get("/api/admin/skills/alpha")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "auth_missing"


async def test_detail_wrong_token_returns_401(
    client_factory, fake_registry
) -> None:
    async with client_factory(headers={"Authorization": "Bearer wrong"}) as c:
        r = await c.get("/api/admin/skills/alpha")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "auth_invalid"


# ---------------------------------------------------------------------------
# List shape (200)
# ---------------------------------------------------------------------------


async def test_list_returns_200_with_alphabetical_items(
    client_factory, fake_registry
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/skills")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    items = body["data"]["items"]
    assert [i["name"] for i in items] == ["alpha", "beta", "gamma"]


async def test_list_item_keys_exact_whitelist(
    client_factory, fake_registry
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/skills")
    items = r.json()["data"]["items"]
    expected = {
        "name",
        "description",
        "category",
        "body_preview",
        "body_truncated",
        "cited_specs",
    }
    for item in items:
        assert set(item.keys()) == expected


async def test_list_truncates_body_over_200_chars(
    client_factory, fake_registry
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/skills")
    items = {i["name"]: i for i in r.json()["data"]["items"]}

    long_item = items["beta"]
    assert len(long_item["body_preview"]) == 200
    assert long_item["body_truncated"] is True

    short_item = items["alpha"]
    # Loader strips the trailing \n from the body; preview matches the
    # rstripped form.
    assert short_item["body_preview"] == _SHORT_BODY.rstrip("\n")
    assert short_item["body_truncated"] is False


async def test_list_empty_registry_returns_empty_items(
    client_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes_skills, "_REGISTRY_DIR", tmp_path)
    async with client_factory() as c:
        r = await c.get("/api/admin/skills")
    assert r.status_code == 200
    assert r.json()["data"]["items"] == []


async def test_list_preserves_cited_specs_order(
    client_factory, fake_registry
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/skills")
    items = {i["name"]: i for i in r.json()["data"]["items"]}
    assert items["alpha"]["cited_specs"] == ["spec-one", "spec-two"]
    assert items["gamma"]["cited_specs"] == []


# ---------------------------------------------------------------------------
# Detail shape (200) and 404
# ---------------------------------------------------------------------------


async def test_detail_returns_full_body(client_factory, fake_registry) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/skills/beta")
    assert r.status_code == 200
    data = r.json()["data"]
    assert set(data.keys()) == {
        "name",
        "description",
        "category",
        "body",
        "cited_specs",
    }
    assert data["name"] == "beta"
    # Loader strips a single trailing newline; long body has none anyway,
    # but compare against the rstripped form for symmetry with the alpha case.
    assert data["body"] == _LONG_BODY.rstrip("\n")
    assert len(data["body"]) > 200


async def test_detail_empty_cited_specs_renders_as_empty_list(
    client_factory, fake_registry
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/skills/gamma")
    assert r.status_code == 200
    assert r.json()["data"]["cited_specs"] == []


async def test_detail_404_for_missing_skill(
    client_factory, fake_registry
) -> None:
    async with client_factory() as c:
        r = await c.get("/api/admin/skills/does-not-exist")
    assert r.status_code == 404
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "not_found"
    assert "does-not-exist" in body["error"]["message"]


# ---------------------------------------------------------------------------
# 400 invalid_input — path traversal rejected before disk I/O
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw_name",
    [
        "foo%2Fbar",  # decodes to foo/bar → catches /
        "..%2Fsecrets",  # decodes to ../secrets → catches both .. and /
        "foo..bar",  # embedded .. survives HTTP path normalization
        "foo%5Cbar",  # decodes to foo\bar → catches \
    ],
)
async def test_detail_rejects_path_traversal_with_400(
    client_factory, fake_registry, raw_name: str
) -> None:
    async with client_factory() as c:
        r = await c.get(f"/api/admin/skills/{raw_name}")
    assert r.status_code == 400, (raw_name, r.text)
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "invalid_input"


async def test_path_traversal_does_not_touch_filesystem(
    client_factory,
    fake_registry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 400 must fire before any ``Path.read_text`` / ``Path.exists`` call."""
    calls: list[str] = []
    real_read = Path.read_text
    real_exists = Path.exists

    def trap_read(self: Path, *args, **kwargs):
        calls.append(f"read_text:{self}")
        return real_read(self, *args, **kwargs)

    def trap_exists(self: Path) -> bool:
        calls.append(f"exists:{self}")
        return real_exists(self)

    monkeypatch.setattr(Path, "read_text", trap_read)
    monkeypatch.setattr(Path, "exists", trap_exists)

    async with client_factory() as c:
        r = await c.get("/api/admin/skills/foo%2Fbar")

    assert r.status_code == 400
    assert not any(str(fake_registry) in call for call in calls), calls


# ---------------------------------------------------------------------------
# 405 on write methods
# ---------------------------------------------------------------------------


async def test_post_list_returns_405(client_factory) -> None:
    async with client_factory() as c:
        r = await c.post("/api/admin/skills", content=json.dumps({}))
    assert r.status_code == 405


async def test_put_detail_returns_405(client_factory, fake_registry) -> None:
    async with client_factory() as c:
        r = await c.put(
            "/api/admin/skills/alpha", content=json.dumps({"body": "x"})
        )
    assert r.status_code == 405


# ---------------------------------------------------------------------------
# Invariant: route's local token tuple stays equal to loader's
# ---------------------------------------------------------------------------


async def test_invalid_name_tokens_match_loader() -> None:
    assert (
        routes_skills._INVALID_NAME_TOKENS_LOCAL
        == skills_loader._INVALID_NAME_TOKENS
    ), (
        "routes/skills.py and skills/loader.py disagree on which tokens "
        "constitute path traversal — update both or add a wrapper."
    )


# ---------------------------------------------------------------------------
# Production registry sanity (no monkeypatch — real disk)
# ---------------------------------------------------------------------------


async def test_production_registry_lists_all_seed_skills(
    client_factory,
) -> None:
    expected_count = len(list(routes_skills._REGISTRY_DIR.glob("*.md")))
    assert expected_count >= 10, "production registry should have ≥10 seeds"

    async with client_factory() as c:
        r = await c.get("/api/admin/skills")
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert len(items) == expected_count
    names = {i["name"] for i in items}
    assert "market-data" in names

    market_data = next(i for i in items if i["name"] == "market-data")
    assert market_data["category"] == "data"
    assert market_data["description"]


# ---------------------------------------------------------------------------
# 500 path — malformed frontmatter must not leak traceback
# ---------------------------------------------------------------------------


async def test_malformed_frontmatter_returns_500_without_traceback(
    client_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Missing closing --- fence → SkillLoadError at parse time.
    (tmp_path / "broken.md").write_text(
        "---\nname: broken\nno-closing-fence-here\n# body\n", encoding="utf-8"
    )
    monkeypatch.setattr(routes_skills, "_REGISTRY_DIR", tmp_path)

    async with client_factory() as c:
        r = await c.get("/api/admin/skills")

    assert r.status_code == 500
    body = r.json()
    assert body["ok"] is False
    text = r.text
    assert "Traceback" not in text
    assert "SkillLoadError" not in text
