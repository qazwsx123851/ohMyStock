"""Reverse-import guards for Phase 0d connector / observability / journal modules.

Spec: openspec/changes/external-connectors-and-cost/proposal.md
- These four modules MUST NOT import from ``ohmystock.api`` (one-way arrow:
  api → connectors, never connectors → api).
- Importing them MUST NOT pull in ``fastapi``/``uvicorn``/``starlette`` —
  those are HTTP-layer-only and would bloat CLI startup.
"""

from __future__ import annotations

import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

GUARDED_MODULES = {
    "ohmystock.data.finmind_client": Path("src/ohmystock/data/finmind_client.py"),
    "ohmystock.paper.shioaji_client": Path("src/ohmystock/paper/shioaji_client.py"),
    "ohmystock.observability.cost_tracker": Path(
        "src/ohmystock/observability/cost_tracker.py"
    ),
    "ohmystock.journal.schema": Path("src/ohmystock/journal/schema.py"),
}

FORBIDDEN_IMPORT_PATTERNS = [
    re.compile(r"^\s*from\s+ohmystock\.api\b", re.MULTILINE),
    re.compile(r"^\s*import\s+ohmystock\.api\b", re.MULTILINE),
]


@pytest.mark.parametrize("module_name,path", list(GUARDED_MODULES.items()))
def test_no_reverse_api_import_in_source(module_name: str, path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    for pattern in FORBIDDEN_IMPORT_PATTERNS:
        assert pattern.search(source) is None, (
            f"{module_name} ({path}) must not import from ohmystock.api"
        )


def test_importing_guarded_modules_does_not_pull_http_stack() -> None:
    code = textwrap.dedent(
        """
        import sys
        import ohmystock.data.finmind_client
        import ohmystock.paper.shioaji_client
        import ohmystock.observability.cost_tracker
        import ohmystock.journal.schema

        forbidden = {"fastapi", "uvicorn", "starlette"}
        leaked = sorted(forbidden & set(sys.modules))
        if leaked:
            print("LEAKED:" + ",".join(leaked))
            sys.exit(2)
        sys.exit(0)
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"unexpected stdout={result.stdout!r} stderr={result.stderr!r}"
    )
