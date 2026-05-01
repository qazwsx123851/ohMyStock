"""Tests for score_watchlist input validation envelope.

Spec: openspec/changes/phase-2b-scoring-engine/specs/phase-2b-scoring-engine/spec.md
("Input validation produces INVALID_INPUT" requirement).
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset() -> None:
    import ohmystock.scoring  # noqa: F401
    from ohmystock.scoring import registry as _reg

    saved = dict(_reg._REGISTRY)
    _reg._reset_registry()
    yield
    _reg._reset_registry()
    _reg._REGISTRY.update(saved)


def _assert_invalid(env: dict, keyword: str) -> None:
    assert env["ok"] is False
    assert env["data"] is None
    assert env["error"]["code"] == "INVALID_INPUT"
    assert env["error"]["retriable"] is False
    assert keyword in env["error"]["message"], (
        f"expected {keyword!r} in error message, got {env['error']['message']!r}"
    )
    assert env["elapsed_ms"] >= 0


def test_asof_date_wrong_format() -> None:
    from ohmystock.scoring import score_watchlist

    env = score_watchlist("2026/04/30", ["2330"])
    _assert_invalid(env, "asof_date")


def test_asof_date_not_parseable() -> None:
    from ohmystock.scoring import score_watchlist

    env = score_watchlist("2026-13-99", ["2330"])
    _assert_invalid(env, "asof_date")


def test_empty_candidates() -> None:
    from ohmystock.scoring import score_watchlist

    env = score_watchlist("2026-04-30", [])
    _assert_invalid(env, "candidates")


def test_malformed_candidate_symbol() -> None:
    from ohmystock.scoring import score_watchlist

    env = score_watchlist("2026-04-30", ["abc"])
    _assert_invalid(env, "symbol")


def test_top_n_is_bool_rejected() -> None:
    from ohmystock.scoring import score_watchlist

    env = score_watchlist("2026-04-30", ["2330"], top_n=True)
    _assert_invalid(env, "top_n")


def test_top_n_zero_rejected() -> None:
    from ohmystock.scoring import score_watchlist

    env = score_watchlist("2026-04-30", ["2330"], top_n=0)
    _assert_invalid(env, "top_n")


def test_risk_off_resolver_not_callable() -> None:
    from ohmystock.scoring import score_watchlist

    env = score_watchlist("2026-04-30", ["2330"], risk_off_resolver=False)
    _assert_invalid(env, "risk_off_resolver")
