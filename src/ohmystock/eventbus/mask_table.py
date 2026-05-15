"""Symbol → masked-label mapping for the public SSE channel.

SymbolMaskTable is process-scoped: the same input ``symbol`` is mapped to the
same label for the lifetime of one instance (typically one app lifespan).
Constructing a fresh instance resets the counter — that is intentional and
documented in ``docs/auth-and-mask.md`` §3.3 ("avoid visitors accumulating
the mapping over long-running sessions").

Labels are assigned in encounter order using base-26 uppercase rollover:
``STK-A``, ``STK-B``, …, ``STK-Z``, ``STK-AA``, ``STK-AB``, …

Spec: openspec/changes/web-public-shell-and-mask/specs/eventbus-public-mask/spec.md
      ("SymbolMaskTable labels are stable in-instance and base-26-encoded")
"""

from __future__ import annotations

from string import ascii_uppercase

_INDUSTRY_FALLBACK = "其他"
_LABEL_PREFIX = "STK-"


class SymbolMaskTable:
    def __init__(self, industry_lookup: dict[str, str]) -> None:
        self._map: dict[str, str] = {}
        self._counter = 0
        self._industry = industry_lookup

    def mask(self, symbol: str) -> str:
        existing = self._map.get(symbol)
        if existing is not None:
            return existing
        label = _LABEL_PREFIX + self._next_suffix()
        self._map[symbol] = label
        return label

    def industry_of(self, symbol: str) -> str:
        return self._industry.get(symbol, _INDUSTRY_FALLBACK)

    def _next_suffix(self) -> str:
        n = self._counter + 1
        self._counter += 1
        chars: list[str] = []
        while n > 0:
            n, r = divmod(n - 1, 26)
            chars.append(ascii_uppercase[r])
        return "".join(reversed(chars))
