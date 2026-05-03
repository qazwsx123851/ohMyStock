"""Project-wide pytest fixtures.

Capability: web-admin-bearer-auth (auth gate must be satisfied for any
``/api/admin/*`` test client). The autouse fixture sets a synthetic
``OHMYSTOCK_ADMIN_TOKEN`` for the entire test session so existing route
tests that build their own ``TestClient`` / ``AsyncClient`` keep working;
new auth-coverage tests opt out via per-test ``monkeypatch.delenv``.

Spec: openspec/changes/web-admin-bearer-auth-v0/specs/web-admin-bearer-auth/spec.md
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest


VALID_ADMIN_TOKEN = "test-admin-token-xxxxxxxxxxxxxxxxxxxxxxxx"  # 41 chars


@pytest.fixture(autouse=True, scope="session")
def _set_admin_token_env() -> Iterator[None]:
    """Inject a synthetic admin token for the whole test session.

    Any test that needs to assert "no token" or "wrong token" behavior
    overrides this with ``monkeypatch.delenv("OHMYSTOCK_ADMIN_TOKEN")``
    or ``monkeypatch.setenv("OHMYSTOCK_ADMIN_TOKEN", "...")`` — those
    function-scoped patches override the session-level os.environ.
    """

    previous = os.environ.get("OHMYSTOCK_ADMIN_TOKEN")
    os.environ["OHMYSTOCK_ADMIN_TOKEN"] = VALID_ADMIN_TOKEN
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("OHMYSTOCK_ADMIN_TOKEN", None)
        else:
            os.environ["OHMYSTOCK_ADMIN_TOKEN"] = previous


@pytest.fixture()
def valid_admin_token() -> str:
    """Return the synthetic admin token used across the test session."""

    return VALID_ADMIN_TOKEN


@pytest.fixture()
def auth_headers(valid_admin_token: str) -> dict[str, str]:
    """Default Authorization header dict for admin route tests."""

    return {"Authorization": f"Bearer {valid_admin_token}"}
