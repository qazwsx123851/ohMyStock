"""Structural filters for the TW universe.

Spec: openspec/changes/screener-tw-universe/specs/screener-tw-universe/spec.md
"""

from __future__ import annotations

import sqlite3
from typing import Any


_FLAG_COLUMN = {
    "warning": "is_warning",
    "disposal": "is_disposal",
    "fully_paid": "is_fully_paid",
    "KY": "is_ky",
}


def apply_negative_filter(
    rows: list[dict[str, Any]], exclude: list[str]
) -> list[dict[str, Any]]:
    """Drop rows whose flag column equals 1 for any name in `exclude`.

    Recognised flags: ``"warning"``, ``"disposal"``, ``"fully_paid"``, ``"KY"``.
    Raises ``ValueError`` on unknown flag (caller maps to ``INVALID_INPUT``).
    """
    columns: list[str] = []
    for flag in exclude:
        if flag not in _FLAG_COLUMN:
            raise ValueError(f"unknown exclude flag: {flag!r}")
        columns.append(_FLAG_COLUMN[flag])

    if not columns:
        return list(rows)

    return [
        row for row in rows if not any(int(row.get(col, 0)) == 1 for col in columns)
    ]


def apply_volume_filter(
    rows: list[dict[str, Any]],
    conn: sqlite3.Connection,
    min_avg: int,
    asof_date_used: str,
    error_policy: str = "skip_missing",
) -> list[dict[str, Any]]:
    """Drop rows whose 5-business-day average ``bars_daily.amount`` is below
    ``min_avg``.

    Reads only from ``bars_daily``; never calls the network. Behaviour on
    insufficient bars (fewer than 5 within the window ending ``asof_date_used``):

    - ``"skip_missing"`` (default): drop the symbol.
    - ``"fail_fast"``: raise ``ValueError("data unavailable")`` so the caller
      can surface ``DATA_UNAVAILABLE``.
    """
    if error_policy not in {"skip_missing", "fail_fast"}:
        raise ValueError(f"unknown error_policy: {error_policy!r}")

    out: list[dict[str, Any]] = []
    for row in rows:
        symbol = row["symbol"]
        cursor = conn.execute(
            "SELECT amount FROM bars_daily "
            "WHERE symbol = ? AND date <= ? "
            "ORDER BY date DESC LIMIT 5",
            (symbol, asof_date_used),
        )
        amounts = [r[0] for r in cursor.fetchall()]
        if len(amounts) < 5:
            if error_policy == "fail_fast":
                raise ValueError(
                    f"data unavailable: {symbol} has {len(amounts)} bars "
                    f"in window ending {asof_date_used}"
                )
            continue
        avg = sum(amounts) / 5
        if avg >= min_avg:
            out.append(row)
    return out
