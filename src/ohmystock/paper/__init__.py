"""Paper trading subsystem.

Public API:
- ``PaperBroker`` Protocol + ``FakePaperBroker`` default impl + ``Fill`` /
  ``BrokerError`` from :mod:`ohmystock.paper.broker`.

The Shioaji simulation client lives in :mod:`ohmystock.paper.shioaji_client`
and is intentionally not re-exported (importing it requires the ``shioaji``
package, which is optional for the gate code path).
"""

from ohmystock.paper.broker import (
    BrokerError,
    FakePaperBroker,
    Fill,
    PaperBroker,
)

__all__ = [
    "BrokerError",
    "FakePaperBroker",
    "Fill",
    "PaperBroker",
]
