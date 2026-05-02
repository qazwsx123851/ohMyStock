"""Safety subsystem — Confirm Gate, Risk Gate (future), 9-line breaker (Phase 3.5).

Public API for Confirm Gate v0:
- ``confirm`` / ``reject`` / ``sweep_expired`` / ``list_pending`` functions.
- ``ConfirmResult`` / ``RejectResult`` / ``PendingEntry`` dataclasses.
- ``ConfirmGateError`` exception.
- ``Clock`` Protocol + ``system_clock`` default.

Spec: openspec/changes/confirm-gate-v0/specs/confirm-gate/spec.md
"""

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
]
