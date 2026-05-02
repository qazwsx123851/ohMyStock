"""Exit engine — daily, full-position evaluator (v0).

Spec: openspec/changes/exit-engine-v0/specs/exit-engine/spec.md
SSOT: docs/workflow-cheatsheet.md §6.6
"""

from ohmystock.exit_engine.evaluator import (
    ExitDecision,
    ExitEngineError,
    ExitResult,
    ExitTag,
    MarketDataLookup,
    evaluate_open_positions,
    evaluate_position,
)

__all__ = [
    "ExitDecision",
    "ExitEngineError",
    "ExitResult",
    "ExitTag",
    "MarketDataLookup",
    "evaluate_open_positions",
    "evaluate_position",
]
