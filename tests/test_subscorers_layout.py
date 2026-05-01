"""Layout guard for the subscorers package.

Spec: openspec/changes/phase-2b-shipped-subscorers/specs/phase-2b-scoring-engine/spec.md
("Sub-scorer file layout under `subscorers/` package" requirement).
"""

from __future__ import annotations

import importlib
from pathlib import Path


def test_subscorers_package_imports() -> None:
    module = importlib.import_module("ohmystock.scoring.subscorers")
    assert module is not None


def test_subscorers_is_a_package_directory() -> None:
    module = importlib.import_module("ohmystock.scoring.subscorers")
    assert hasattr(module, "__path__"), "subscorers must be a package, not a single module"
    package_dir = Path(module.__path__[0])
    assert package_dir.is_dir(), f"expected directory, got {package_dir}"
    assert (package_dir / "__init__.py").exists(), "__init__.py missing"
