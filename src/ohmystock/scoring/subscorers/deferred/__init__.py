"""Phase 2B deferred-stub sub-scorers.

Importing this package registers all 16 deferred stubs with the scoring
registry. Each stub returns ``status="skipped"`` and ``points=0`` until its
underlying data source ships in a later change.

Spec: openspec/changes/phase-2b-deferred-cli/specs/phase-2b-scoring-engine/spec.md
("Deferred-stub sub-scorers register with `status=\"skipped\"`" requirement).
"""

from ohmystock.scoring.subscorers.deferred import analyst_target_upgrades  # noqa: F401
from ohmystock.scoring.subscorers.deferred import borrow_change  # noqa: F401
from ohmystock.scoring.subscorers.deferred import broker_concentration  # noqa: F401
from ohmystock.scoring.subscorers.deferred import eps_qoq  # noqa: F401
from ohmystock.scoring.subscorers.deferred import eps_yoy  # noqa: F401
from ohmystock.scoring.subscorers.deferred import futures_oi  # noqa: F401
from ohmystock.scoring.subscorers.deferred import important_announcements  # noqa: F401
from ohmystock.scoring.subscorers.deferred import institutional_30d_holding  # noqa: F401
from ohmystock.scoring.subscorers.deferred import kline_patterns  # noqa: F401
from ohmystock.scoring.subscorers.deferred import margin_tightening  # noqa: F401
from ohmystock.scoring.subscorers.deferred import monthly_revenue_yoy  # noqa: F401
from ohmystock.scoring.subscorers.deferred import quarterly_revenue_yoy  # noqa: F401
from ohmystock.scoring.subscorers.deferred import rs_percentile  # noqa: F401
from ohmystock.scoring.subscorers.deferred import search_heat  # noqa: F401
from ohmystock.scoring.subscorers.deferred import sue  # noqa: F401
from ohmystock.scoring.subscorers.deferred import tdcc_concentration  # noqa: F401
