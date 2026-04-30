"""Reverse-import guard: screener layer must not pull in FastAPI/Starlette/Uvicorn.

Spec: openspec/changes/screener-tw-universe/specs/screener-tw-universe/spec.md
("Reverse-import isolation" requirement).
"""

from __future__ import annotations

import json
import subprocess
import sys


SNIPPET = """
import sys
import ohmystock.screener
import ohmystock.screener.cache
import ohmystock.screener.filters
import ohmystock.screener.universe
import json as _json
forbidden = sorted(m for m in ('fastapi', 'uvicorn', 'starlette') if m in sys.modules)
print(_json.dumps({'forbidden_loaded': forbidden}))
"""


def test_screener_modules_do_not_load_fastapi():
    proc = subprocess.run(
        [sys.executable, "-c", SNIPPET],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"subprocess failed: stderr={proc.stderr!r}"
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["forbidden_loaded"] == [], (
        f"screener layer pulled in {payload['forbidden_loaded']}"
    )


def test_screener_package_exports_screen_universe() -> None:
    from ohmystock.screener import screen_universe

    assert callable(screen_universe)
