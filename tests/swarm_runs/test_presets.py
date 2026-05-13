"""Tests for ohmystock.swarm_runs.presets — preset registry.

Spec: openspec/changes/admin-swarm-endpoints-and-pages/specs/swarm-runs/spec.md
      § "PresetSpec 與 preset registry"
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ohmystock.swarm_runs.presets import PRESETS, PresetSpec, get_preset


def test_presets_contains_phase5_review() -> None:
    assert "phase5-review" in PRESETS
    assert PRESETS["phase5-review"].nodes == [
        "data_loader",
        "attributor",
        "aggregator",
        "critic",
        "proposer",
    ]


def test_get_preset_unknown_raises_keyerror() -> None:
    with pytest.raises(KeyError) as excinfo:
        get_preset("nonexistent")
    assert "unknown preset" in str(excinfo.value)


def test_preset_spec_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        PresetSpec(
            name="x",
            title="y",
            description="z",
            nodes=["a"],
            params_schema={},
            extra_field="boom",  # type: ignore[call-arg]
        )
