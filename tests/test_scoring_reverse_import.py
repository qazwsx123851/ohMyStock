"""Reverse-import guard: scoring layer must not pull FastAPI/Starlette/Uvicorn.

Spec: openspec/changes/phase-2b-scoring-engine/specs/phase-2b-scoring-engine/spec.md
("Reverse-import isolation" requirement).
"""

from __future__ import annotations

import json
import subprocess
import sys


SNIPPET = """
import sys
import ohmystock.scoring
import json as _json
forbidden = sorted(m for m in ('fastapi', 'uvicorn', 'starlette') if m in sys.modules)
print(_json.dumps({'forbidden_loaded': forbidden}))
"""


def test_scoring_modules_do_not_load_fastapi() -> None:
    proc = subprocess.run(
        [sys.executable, "-c", SNIPPET],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"subprocess failed: stderr={proc.stderr!r}"
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["forbidden_loaded"] == [], (
        f"scoring layer pulled in {payload['forbidden_loaded']}"
    )
