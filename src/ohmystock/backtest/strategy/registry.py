"""Enumerate registered backtest strategies for the admin UI.

The frontend's strategy ``<select>`` is populated from
``available_strategies()`` so the dropdown stays in sync as new strategies
are added under ``ohmystock.backtest.strategy`` without page changes.

Each entry:

* ``name``         — class-level ``name`` attribute (e.g. ``"sma_cross"``).
* ``description``  — first non-empty line of the class ``__doc__``.

Classes that fail to construct with no arguments are silently skipped so a
broken strategy degrades the dropdown rather than 500-ing the endpoint.

Spec: openspec/changes/web-admin-backtest-pages/specs/admin-backtest-endpoints/spec.md
"""

from __future__ import annotations

import inspect
from typing import TypedDict

from ohmystock.backtest import strategy as strategy_pkg


class StrategyEntry(TypedDict):
    name: str
    description: str


def _first_doc_line(obj: object) -> str:
    doc = inspect.getdoc(obj) or ""
    for line in doc.splitlines():
        s = line.strip()
        if s:
            return s
    return ""


def available_strategies() -> list[StrategyEntry]:
    """Return strategies discoverable from ``ohmystock.backtest.strategy``.

    A class is considered a strategy when it exposes both ``warmup_bars``
    and ``on_bar`` callables and has a string ``name`` attribute. Each
    candidate is constructed with no arguments inside a try/except so a
    broken strategy is omitted rather than raising.
    """

    out: list[StrategyEntry] = []
    seen: set[str] = set()
    for attr_name in dir(strategy_pkg):
        candidate = getattr(strategy_pkg, attr_name, None)
        if not inspect.isclass(candidate):
            continue
        if not (
            callable(getattr(candidate, "warmup_bars", None))
            and callable(getattr(candidate, "on_bar", None))
        ):
            continue
        try:
            instance = candidate()
        except Exception:  # noqa: BLE001 — broken strategies degrade gracefully.
            continue
        name = getattr(instance, "name", None) or getattr(candidate, "name", None)
        if not isinstance(name, str) or not name:
            continue
        if name in seen:
            continue
        seen.add(name)
        out.append(
            StrategyEntry(name=name, description=_first_doc_line(candidate))
        )
    return sorted(out, key=lambda e: e["name"])
