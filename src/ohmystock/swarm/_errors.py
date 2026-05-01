"""Swarm-input-assembler error types.

Specs:
- openspec/changes/phase-2b-swarm-input-assembler/specs/swarm-input-assembler/spec.md
- openspec/changes/live-providers/specs/live-providers/spec.md
"""

from __future__ import annotations


class AssemblerInputError(Exception):
    """Raised when build_entry_decision_input cannot construct a valid payload."""


class RulesDigestError(Exception):
    """Raised when load_rules_digest fails (missing file, malformed, wrong counts)."""


_LIVE_PROVIDER_CODES = frozenset(
    {"DATA_UNAVAILABLE", "STALE_DATA", "UPSTREAM_ERROR", "AUTH_FAILED"}
)


class LiveProviderError(Exception):
    """Raised by Live*Provider implementations on data-source failure.

    `code` is one of `DATA_UNAVAILABLE`, `STALE_DATA`, `UPSTREAM_ERROR`,
    `AUTH_FAILED`. Constructing with any other code raises ``ValueError``.
    """

    def __init__(self, *, code: str, message: str) -> None:
        if code not in _LIVE_PROVIDER_CODES:
            raise ValueError(
                f"LiveProviderError code must be one of {sorted(_LIVE_PROVIDER_CODES)}, "
                f"got {code!r}"
            )
        super().__init__(message)
        self.code = code
        self.message = message
