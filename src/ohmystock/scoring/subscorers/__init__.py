"""Real Phase 2B sub-scorers.

Importing this package registers every sub-scorer module with the
scoring registry. The top-level ``ohmystock.scoring`` package imports
this package so that ``score_watchlist`` finds them at runtime.

Spec: openspec/changes/phase-2b-shipped-subscorers/specs/phase-2b-scoring-engine/spec.md
("Sub-scorer file layout under `subscorers/` package" requirement).
"""

from ohmystock.scoring.subscorers import foreign_5d_net_buy  # noqa: F401
from ohmystock.scoring.subscorers import rs_percentile  # noqa: F401
from ohmystock.scoring.subscorers import stage_2_confirmed  # noqa: F401
from ohmystock.scoring.subscorers import trend_structure_ma  # noqa: F401
from ohmystock.scoring.subscorers import trend_template_8  # noqa: F401
from ohmystock.scoring.subscorers import trust_5d_net_buy  # noqa: F401
from ohmystock.scoring.subscorers import vcp_pivot  # noqa: F401
from ohmystock.scoring.subscorers import volume_breakout_obv  # noqa: F401
from ohmystock.scoring.subscorers import deferred  # noqa: F401
