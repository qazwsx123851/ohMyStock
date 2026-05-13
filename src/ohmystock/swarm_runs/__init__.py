"""``swarm_runs`` — admin-triggered pipeline runs (Phase 5 review et al.).

Public surface (extended incrementally as task groups land):

- :class:`PresetSpec` / :data:`PRESETS` / :func:`get_preset` — preset registry
- :func:`run_swarm` / :class:`SwarmRunResult` / :class:`SwarmRunnerError` —
  added by task group 4 (runner)

The ``swarm_runs`` name (rather than ``swarm``) avoids collision with the
existing :mod:`ohmystock.swarm` package which owns the Phase 2B Swarm
Input Assembler.

Spec: openspec/changes/admin-swarm-endpoints-and-pages/specs/swarm-runs/spec.md
"""

from __future__ import annotations

from ohmystock.swarm_runs.presets import PHASE5_REVIEW, PRESETS, PresetSpec, get_preset
from ohmystock.swarm_runs.runner import SwarmRunnerError, SwarmRunResult, run_swarm

__all__ = [
    "PHASE5_REVIEW",
    "PRESETS",
    "PresetSpec",
    "SwarmRunnerError",
    "SwarmRunResult",
    "get_preset",
    "run_swarm",
]
