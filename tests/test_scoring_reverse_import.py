"""Reverse-import guard: scoring layer must not pull FastAPI/Starlette/Uvicorn.

Spec: openspec/changes/phase-2b-scoring-engine/specs/phase-2b-scoring-engine/spec.md
("Reverse-import isolation" requirement).
"""

from __future__ import annotations

import json
import subprocess
import sys


def _snippet(target_import: str) -> str:
    return (
        "import sys\n"
        f"{target_import}\n"
        "import json as _json\n"
        "forbidden = sorted(m for m in ('fastapi', 'uvicorn', 'starlette') if m in sys.modules)\n"
        "print(_json.dumps({'forbidden_loaded': forbidden}))\n"
    )


def _run(target_import: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", _snippet(target_import)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"subprocess failed: stderr={proc.stderr!r}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_scoring_modules_do_not_load_fastapi() -> None:
    payload = _run("import ohmystock.scoring")
    assert payload["forbidden_loaded"] == [], (
        f"scoring layer pulled in {payload['forbidden_loaded']}"
    )


def test_subscorers_package_does_not_load_fastapi() -> None:
    payload = _run("import ohmystock.scoring.subscorers")
    assert payload["forbidden_loaded"] == [], (
        f"subscorers package pulled in {payload['forbidden_loaded']}"
    )
