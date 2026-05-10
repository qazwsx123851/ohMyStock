"""Proposal markdown writer + parser + state machine.

Specs:
- openspec/changes/phase5-review-mvp/specs/proposal-writer/spec.md (writer v0)
- openspec/changes/proposal-state-machine/specs/proposal-state-machine/spec.md
"""

from ohmystock.proposal.schema import ProposalDraft
from ohmystock.proposal.state import (
    ProposalStateError,
    ProposalStatus,
    transition_proposal,
)
from ohmystock.proposal.writer import (
    ProposalParseError,
    parse_proposal,
    render_markdown,
    write_proposal,
)

__all__ = [
    "ProposalDraft",
    "ProposalParseError",
    "ProposalStateError",
    "ProposalStatus",
    "parse_proposal",
    "render_markdown",
    "transition_proposal",
    "write_proposal",
]
