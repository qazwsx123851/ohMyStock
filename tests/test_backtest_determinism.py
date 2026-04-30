"""Determinism + non-randomness static checks for the backtest engine.

Spec: openspec/changes/backtest-engine-mvp/specs/backtest-engine/spec.md
("Determinism" requirement).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from ohmystock.backtest import run_backtest
from tests._strategies import BuyAndHold

BACKTEST_DIR = Path(__file__).resolve().parents[1] / "src" / "ohmystock" / "backtest"

FORBIDDEN_PATTERNS = [
    (re.compile(r"\bimport\s+random\b"), "import random"),
    (re.compile(r"\bfrom\s+random\b"), "from random"),
    (re.compile(r"\bnumpy\.random\b"), "numpy.random"),
    (re.compile(r"\bnp\.random\b"), "np.random"),
    (re.compile(r"\btime\.time\("), "time.time()"),
    (re.compile(r"\bdatetime\.now\("), "datetime.now()"),
    (re.compile(r"\bdatetime\.today\("), "datetime.today()"),
    (re.compile(r"\bdate\.today\("), "date.today()"),
]

# `time.perf_counter_ns` is allowed only at the engine boundary.
PERF_COUNTER_RE = re.compile(r"\bperf_counter_ns\b")


def _bars(prices: list[float]) -> list[dict]:
    base = date(2026, 4, 1)
    return [
        {
            "ts": (base + timedelta(days=i)).isoformat(),
            "o": float(p),
            "h": float(p),
            "l": float(p),
            "c": float(p),
            "v": 1000,
            "amount": int(p * 1000),
        }
        for i, p in enumerate(prices)
    ]


def test_two_runs_byte_identical():
    bars = _bars([100 + i for i in range(30)])
    args = dict(
        bars_by_symbol={"2330": bars},
        period={"from": "2026-04-01", "to": "2026-05-01"},
        initial_capital=1_000_000,
    )
    a = run_backtest(BuyAndHold("2330", qty=100), **args)
    b = run_backtest(BuyAndHold("2330", qty=100), **args)
    assert a["ok"] is True and b["ok"] is True
    assert a["data"]["equity_curve"] == b["data"]["equity_curve"]
    assert a["data"]["trades"] == b["data"]["trades"]


def test_no_random_or_walltime_in_backtest_modules():
    """No `random`, `numpy.random`, `time.time`, `datetime.now` anywhere in the package."""
    sources = list(BACKTEST_DIR.rglob("*.py"))
    assert sources, f"no python files found under {BACKTEST_DIR}"
    offenders: list[str] = []
    for path in sources:
        text = path.read_text(encoding="utf-8")
        for pat, label in FORBIDDEN_PATTERNS:
            for m in pat.finditer(text):
                line = text[: m.start()].count("\n") + 1
                offenders.append(f"{path.name}:{line} -> {label}")
    assert not offenders, "non-deterministic source detected:\n" + "\n".join(offenders)


def test_perf_counter_ns_only_in_engine():
    """`time.perf_counter_ns` is the only wall-clock read; restrict it to engine.py."""
    sources = list(BACKTEST_DIR.rglob("*.py"))
    leaks: list[str] = []
    for path in sources:
        if path.name == "engine.py":
            continue
        if PERF_COUNTER_RE.search(path.read_text(encoding="utf-8")):
            leaks.append(str(path))
    assert not leaks, f"perf_counter_ns leaked outside engine.py: {leaks}"
