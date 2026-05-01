"""Phase 2B scoring engine.

Public API: score_watchlist + Pydantic contracts.
The placeholder import below registers `_always_zero_placeholder` at package import.
"""

from ohmystock.scoring.models import Phase2BCandidate, SubScoreResult
from ohmystock.scoring import registry  # noqa: F401 — needed before _placeholder
from ohmystock.scoring import _placeholder  # noqa: F401 — registers placeholder
from ohmystock.scoring._engine import score_watchlist


__all__ = [
    "score_watchlist",
    "Phase2BCandidate",
    "SubScoreResult",
]
