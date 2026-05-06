"""End-to-end smoke for rs-percentile wiring — covers task 5.1.

Spec: openspec/changes/rs-percentile-finmind-wiring/specs/rs-percentile/spec.md

Pins the FastAPI lifespan + loader contract:

* Before app startup, no loader is installed.
* Entering ``TestClient(create_app())`` triggers the lifespan, which wires
  the production loader.
* While inside the lifespan context, a manually-injected stub loader can
  be swapped in so ``compute_rs_rating`` returns an ``int`` against
  deterministic data.
* On exit, the lifespan teardown calls ``reset_providers()`` and the
  loader is unwired again.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest
from starlette.testclient import TestClient

from ohmystock.api.app import create_app
from ohmystock.sepa import rs as rs_module
from ohmystock.sepa.rs import (
    compute_rs_rating,
    init_schema as init_rs_schema,
    reset_providers,
    set_universe_closes_loader,
)


@pytest.fixture(autouse=True)
def _reset_loader():
    yield
    reset_providers()


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    try:
        init_rs_schema(c)
        yield c
    finally:
        c.close()


def _stub_loader(num_symbols: int = 150):
    """Loader that returns ``num_symbols`` valid 260-close ramps per asof."""

    def loader(asof: date) -> dict[str, list[float]]:
        # Always include "2330" so the spec scenario keys off a real ticker.
        out = {"2330": [100.0 + 0.5 * j for j in range(260)]}
        for i in range(num_symbols):
            out[f"S{i:04d}"] = [1.0 + i + 0.01 * j for j in range(260)]
        return out

    return loader


class TestLifespanWiring:
    """Spec scenario: 'Liquid symbol with full history yields an int rating after wiring'."""

    def test_lifespan_installs_and_unwires_loader(self) -> None:
        # Reset to make the pre-condition explicit.
        reset_providers()
        assert rs_module._universe_closes_loader is None

        app = create_app()
        with TestClient(app) as client:
            # Lifespan startup ran -> loader is wired.
            assert rs_module._universe_closes_loader is not None
            # Sanity: the app is actually serving routes inside the context.
            r = client.get("/healthz")
            assert r.status_code == 200

        # Lifespan shutdown ran -> loader is unwired.
        assert rs_module._universe_closes_loader is None

    def test_compute_rs_rating_returns_int_with_loader_inside_lifespan(
        self, conn: sqlite3.Connection
    ) -> None:
        app = create_app()
        with TestClient(app):
            # Override the production-wired loader with a deterministic stub
            # so we can hit a populated in-memory cache without needing real
            # universe_daily / bars_daily rows.
            set_universe_closes_loader(_stub_loader(num_symbols=150))

            result = compute_rs_rating("2330", date(2026, 4, 30), conn=conn)

            assert isinstance(result, int)
            assert 1 <= result <= 99

            # Cache was populated for the asof.
            row = conn.execute(
                "SELECT COUNT(*) FROM rs_rating_cache WHERE asof_date = ?",
                ("2026-04-30",),
            ).fetchone()
            # 1 trigger + 150 stub symbols, all eligible -> 151 cached rows.
            assert row[0] == 151
