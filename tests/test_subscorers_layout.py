"""Layout guard for the subscorers package.

Spec: openspec/changes/phase-2b-shipped-subscorers/specs/phase-2b-scoring-engine/spec.md
       openspec/changes/phase-2b-deferred-cli/specs/phase-2b-scoring-engine/spec.md
(both "Sub-scorer file layout under `subscorers/` package" requirements).
"""

from __future__ import annotations

import importlib
from pathlib import Path

from ohmystock.scoring.registry import list_subscorers

# Force registration via package import (side effect).
import ohmystock.scoring  # noqa: F401


def test_subscorers_package_imports() -> None:
    module = importlib.import_module("ohmystock.scoring.subscorers")
    assert module is not None


def test_subscorers_is_a_package_directory() -> None:
    module = importlib.import_module("ohmystock.scoring.subscorers")
    assert hasattr(module, "__path__"), "subscorers must be a package, not a single module"
    package_dir = Path(module.__path__[0])
    assert package_dir.is_dir(), f"expected directory, got {package_dir}"
    assert (package_dir / "__init__.py").exists(), "__init__.py missing"


def test_deferred_subpackage_imports() -> None:
    module = importlib.import_module("ohmystock.scoring.subscorers.deferred")
    assert hasattr(module, "__path__"), "deferred must be a package, not a single module"
    package_dir = Path(module.__path__[0])
    assert package_dir.is_dir(), f"expected directory, got {package_dir}"
    assert (package_dir / "__init__.py").exists(), "deferred/__init__.py missing"


def _deferred_stub_filenames() -> set[str]:
    module = importlib.import_module("ohmystock.scoring.subscorers.deferred")
    package_dir = Path(module.__path__[0])
    return {
        p.stem
        for p in package_dir.iterdir()
        if p.is_file() and p.suffix == ".py" and p.name != "__init__.py"
    }


def test_deferred_one_file_per_stub() -> None:
    files = _deferred_stub_filenames()
    registered = {name for name, _, _ in list_subscorers()}
    # Every file in deferred/ must correspond to a registered sub-scorer.
    extra_files = files - registered
    assert not extra_files, (
        f"files in deferred/ without a registered sub-scorer: {sorted(extra_files)}"
    )
    # And every registered sub-scorer with a file in deferred/ must match by stem.
    # (Real sub-scorers live one level up, so we don't expect them here.)
    deferred_registered = registered & files
    missing_files = deferred_registered - files
    assert not missing_files, (
        f"deferred stubs registered but missing source files: {sorted(missing_files)}"
    )


def test_deferred_count_matches_spec() -> None:
    # Spec locks 16 deferred stubs.
    assert len(_deferred_stub_filenames()) == 16, (
        "deferred sub-package must contain exactly 16 stub modules per spec"
    )
