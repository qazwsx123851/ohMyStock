"""Tests for LiveProviderError taxonomy.

Spec: openspec/changes/live-providers/specs/live-providers/spec.md
"""

from __future__ import annotations

import pytest

from ohmystock.swarm import LiveProviderError


def test_code_attribute_exposed() -> None:
    err = LiveProviderError(
        code="STALE_DATA", message="taiex bars older than 5 business days"
    )
    assert err.code == "STALE_DATA"
    assert "taiex bars older than 5 business days" in str(err)


def test_message_round_trips_through_args() -> None:
    err = LiveProviderError(code="DATA_UNAVAILABLE", message="cache empty")
    assert err.message == "cache empty"
    assert str(err) == "cache empty"


def test_unknown_code_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="GREMLIN"):
        LiveProviderError(code="GREMLIN", message="oops")


@pytest.mark.parametrize(
    "code", ["DATA_UNAVAILABLE", "STALE_DATA", "UPSTREAM_ERROR", "AUTH_FAILED"]
)
def test_all_documented_codes_accepted(code: str) -> None:
    err = LiveProviderError(code=code, message="ok")
    assert err.code == code


def test_is_exception_subclass() -> None:
    assert issubclass(LiveProviderError, Exception)


def test_can_be_raised_and_caught() -> None:
    with pytest.raises(LiveProviderError) as exc_info:
        raise LiveProviderError(code="UPSTREAM_ERROR", message="finmind 502")
    assert exc_info.value.code == "UPSTREAM_ERROR"
