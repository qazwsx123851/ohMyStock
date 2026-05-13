"""Walk-forward validation engine for strategy-change proposals.

Spec: openspec/changes/wfa-validation-engine/specs/wfa-validation-engine/spec.md
"""

from ohmystock.validation.wfa import (
    ValidationReport,
    WfaValidationError,
    WfaWindow,
    run_validation,
)

__all__ = [
    "ValidationReport",
    "WfaValidationError",
    "WfaWindow",
    "run_validation",
]
