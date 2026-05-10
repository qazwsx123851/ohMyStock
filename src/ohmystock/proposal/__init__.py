"""Proposal markdown writer + parser package.

Spec: openspec/changes/phase5-review-mvp/specs/proposal-writer/spec.md
"""

from ohmystock.proposal.schema import ProposalDraft
from ohmystock.proposal.writer import (
    ProposalParseError,
    parse_proposal,
    render_markdown,
    write_proposal,
)

__all__ = [
    "ProposalDraft",
    "ProposalParseError",
    "parse_proposal",
    "render_markdown",
    "write_proposal",
]
