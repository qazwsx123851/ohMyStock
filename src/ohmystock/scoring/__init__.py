"""Phase 2B scoring engine.

Public API: score_watchlist + Pydantic contracts.
Importing the ``subscorers`` package registers every real sub-scorer at
package import.
"""

from ohmystock.scoring.models import Phase2BCandidate, SubScoreResult
from ohmystock.scoring import registry  # noqa: F401 — needed before subscorers
from ohmystock.scoring import subscorers  # noqa: F401 — registers real sub-scorers
from ohmystock.scoring._engine import score_watchlist
from ohmystock.scoring._repository import (
    iter_qualified_candidates,
    reset_candidate_loader,
    set_candidate_loader,
)


__all__ = [
    "Phase2BCandidate",
    "SubScoreResult",
    "iter_qualified_candidates",
    "reset_candidate_loader",
    "score_watchlist",
    "set_candidate_loader",
]
