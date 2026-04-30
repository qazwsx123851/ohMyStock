"""Reverse-import guard: backtest layer must not pull in FastAPI/Starlette/Uvicorn.

Spec: openspec/changes/backtest-engine-mvp/specs/backtest-engine/spec.md
("No FastAPI / API-layer reverse import" requirement).
"""

from __future__ import annotations

import json
import subprocess
import sys


SNIPPET = """
import sys
import ohmystock.backtest
import ohmystock.backtest.engine
import ohmystock.backtest.costs
import ohmystock.backtest.fills
import ohmystock.backtest.metrics
import ohmystock.backtest.portfolio
import ohmystock.backtest.strategy
import ohmystock.backtest.strategy.base
import ohmystock.backtest.strategy.sma_cross
import json as _json
forbidden = sorted(m for m in ('fastapi', 'uvicorn', 'starlette') if m in sys.modules)
print(_json.dumps({'forbidden_loaded': forbidden}))
"""


def test_backtest_modules_do_not_load_fastapi():
    proc = subprocess.run(
        [sys.executable, "-c", SNIPPET],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"subprocess failed: stderr={proc.stderr!r}"
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["forbidden_loaded"] == [], (
        f"backtest layer pulled in {payload['forbidden_loaded']}"
    )
