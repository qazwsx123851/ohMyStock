"""Safety subsystem — Confirm Gate, Auto-Execute breakers (Phase 3.5),
Risk Gate (future).

Public API for Confirm Gate v0:
- ``confirm`` / ``reject`` / ``sweep_expired`` / ``list_pending`` functions.
- ``ConfirmResult`` / ``RejectResult`` / ``PendingEntry`` dataclasses.
- ``ConfirmGateError`` exception.
- ``Clock`` Protocol + ``system_clock`` default.

Public API for Auto-Execute Phase 3.5:
- ``try_auto_execute`` function.
- ``AutoExecuteResult`` dataclass.
- ``AutoExecuteOutcome`` Literal type alias.
- ``AutoExecuteError`` exception.

Specs:
- openspec/changes/confirm-gate-v0/specs/confirm-gate/spec.md
- openspec/changes/auto-execute-toggle-and-breakers/specs/auto-execute/spec.md
"""

from ohmystock.safety.auto_execute import (
    AutoExecuteError,
    AutoExecuteOutcome,
    AutoExecuteResult,
    try_auto_execute,
)
from ohmystock.safety.confirm_gate import (
    Clock,
    ConfirmGateError,
    ConfirmResult,
    PendingEntry,
    RejectResult,
    confirm,
    list_pending,
    reject,
    sweep_expired,
    system_clock,
)

__all__ = [
    "AutoExecuteError",
    "AutoExecuteOutcome",
    "AutoExecuteResult",
    "Clock",
    "ConfirmGateError",
    "ConfirmResult",
    "PendingEntry",
    "RejectResult",
    "confirm",
    "list_pending",
    "reject",
    "sweep_expired",
    "system_clock",
    "try_auto_execute",
]
