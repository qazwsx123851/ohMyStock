"""Preset registry for swarm-style pipelines.

A "preset" describes a named, parameterised pipeline that can be triggered
from the admin Swarm page. v0 ships exactly one preset (``phase5-review``)
that wraps :func:`ohmystock.review.pipeline.run_review`.

Spec: openspec/changes/admin-swarm-endpoints-and-pages/specs/swarm-runs/spec.md

The module is named ``swarm_runs`` (not ``swarm``) because
``ohmystock.swarm`` is already owned by the Phase 2B Swarm Input Assembler.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class PresetSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    title: str
    description: str
    nodes: list[str]
    params_schema: dict[str, Any]


PHASE5_REVIEW = PresetSpec(
    name="phase5-review",
    title="Phase 5 復盤",
    description=(
        "跑一次 Phase 5 月度復盤：資料載入 → 歸因 → 聚合指標 → 批判 → 提案。"
    ),
    nodes=["data_loader", "attributor", "aggregator", "critic", "proposer"],
    params_schema={
        "period_from": "date",
        "period_to": "date",
        "limit_trades": "int|null",
        "dry_run": "bool",
        "force": "bool",
    },
)


PRESETS: dict[str, PresetSpec] = {
    PHASE5_REVIEW.name: PHASE5_REVIEW,
}


def get_preset(name: str) -> PresetSpec:
    """Look up a preset by name, raising ``KeyError`` on miss."""
    try:
        return PRESETS[name]
    except KeyError as exc:
        raise KeyError(f"unknown preset: {name!r}") from exc


__all__ = ["PRESETS", "PHASE5_REVIEW", "PresetSpec", "get_preset"]
