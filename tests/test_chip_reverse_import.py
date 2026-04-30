"""Reverse-import guard: chip layer must not pull in FastAPI/Starlette/Uvicorn.

Spec: openspec/changes/chip-data-skill/specs/chip-data-skill/spec.md
("No FastAPI / API-layer reverse import" requirement).
"""

from __future__ import annotations

import json
import subprocess
import sys


SNIPPET = """
import sys
import ohmystock.chip
import ohmystock.chip.cache
import ohmystock.chip.three_major
import ohmystock.chip.margin_short
import json as _json
forbidden = sorted(m for m in ('fastapi', 'uvicorn', 'starlette') if m in sys.modules)
print(_json.dumps({'forbidden_loaded': forbidden}))
"""


def test_chip_modules_do_not_load_fastapi():
    proc = subprocess.run(
        [sys.executable, "-c", SNIPPET],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"subprocess failed: stderr={proc.stderr!r}"
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["forbidden_loaded"] == [], (
        f"chip layer pulled in {payload['forbidden_loaded']}"
    )


def test_chip_package_exports_public_entrypoints() -> None:
    from ohmystock.chip import get_margin_short, get_three_major_investors

    assert callable(get_margin_short)
    assert callable(get_three_major_investors)
