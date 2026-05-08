## 1. `SkillSpec` model + module skeleton

- [x] 1.1 Create `src/ohmystock/skills/spec.py` with `SkillSpec` (`pydantic.BaseModel`, `model_config = ConfigDict(frozen=True, extra="forbid")`) holding `name: str`, `description: str`, `category: Literal[...7 values]`, `body: str`, `cited_specs: list[str]`.
- [x] 1.2 Define `SKILL_CATEGORIES: tuple[str, ...]` constant in `spec.py` so the loader and tests can import the canonical list once.
- [x] 1.3 Replace empty `src/ohmystock/skills/__init__.py` with a re-export of `SkillSpec`, `load_skills`, `load_skill`, `SkillLoadError`. Set `__all__` to those four names exactly.

## 2. Loader

- [x] 2.1 Create `src/ohmystock/skills/loader.py` defining `class SkillLoadError(Exception)` with `path: Path` and `reason: str` attributes; `__str__` returns `f"{path}: {reason}"`.
- [x] 2.2 Implement private `_parse_frontmatter(text: str, path: Path) -> tuple[dict, str]` that splits on `---` lines: first line must be `---`, locates the second `---`, parses YAML between them, returns `(frontmatter_dict, body_str)`. Raise `SkillLoadError` for missing leading `---`, missing closing `---`, or `yaml.YAMLError`.
- [x] 2.3 Implement private `_to_skill_spec(frontmatter: dict, body: str, path: Path) -> SkillSpec`. Validate `name == path.stem`; validate `category in SKILL_CATEGORIES`; pass everything to `SkillSpec(...)` and let pydantic handle remaining shape errors. Wrap `pydantic.ValidationError` in `SkillLoadError`.
- [x] 2.4 Implement `load_skill(skills_dir: Path, name: str) -> SkillSpec | None`. Reject names containing `/`, `\\`, `..`, or `os.sep` with `SkillLoadError("invalid skill name")` BEFORE any I/O. Return `None` if `(skills_dir / f"{name}.md").exists()` is false.
- [x] 2.5 Implement `load_skills(skills_dir: Path) -> list[SkillSpec]`. Iterate `skills_dir.iterdir()` (non-recursive); skip directories, non-`.md` suffixes, and filenames starting with `_`. Sort results by `name` ascending. Fail-fast on any parse error.
- [x] 2.6 Verify `PyYAML` is importable (`import yaml`). If not, add `pyyaml>=6.0` to `pyproject.toml` `[project.dependencies]`.

## 3. Seed skill corpus

- [x] 3.1 Create `src/ohmystock/skills/registry/` directory.
- [x] 3.2 Author `market-data.md` (category=data, cited=market-data-cache).
- [x] 3.3 Author `chip-data.md` (category=data, cited=chip-data-skill).
- [x] 3.4 Author `technical-indicators.md` (category=indicator, cited=technical-indicators).
- [x] 3.5 Author `rs-percentile.md` (category=indicator, cited=rs-percentile).
- [x] 3.6 Author `sepa-stage.md` (category=signal, cited=sepa-stage-classification).
- [x] 3.7 Author `sepa-trend-template.md` (category=signal, cited=sepa-trend-template).
- [x] 3.8 Author `screener.md` (category=signal, cited=screener-tw-universe).
- [x] 3.9 Author `phase-2b-scoring.md` (category=signal, cited=phase-2b-scoring-engine).
- [x] 3.10 Author `entry-decider.md` (category=decider, cited=entry-decider).
- [x] 3.11 Author `exit-engine.md` (category=gate, cited=exit-engine).

Each file body MUST contain `# Purpose`, `# Inputs`, `# Outputs`, `# See also` H1 sections.

## 4. Tests

- [x] 4.1 Create `tests/test_skill_loader.py` with helper that writes a temp skills dir using `tmp_path` fixture.
- [x] 4.2 Happy-path test: write 1 valid file, assert `load_skill` returns matching `SkillSpec`.
- [x] 4.3 Validation tests: missing-frontmatter, malformed-YAML, name-mismatch, bad-category, unknown-frontmatter-key — each raises `SkillLoadError` with expected substring in message.
- [x] 4.4 `load_skills` tests: empty dir → `[]`; mixed `_template.md` + valid → only valid; sort-stable; fail-fast on one bad file (other valid files do not matter).
- [x] 4.5 Path-traversal test: `load_skill(dir, "../../../etc/passwd")` raises `SkillLoadError("invalid skill name")` and does not touch the filesystem outside `dir`.
- [x] 4.6 Frozen test: assigning to `s.name` raises `ValidationError`.
- [x] 4.7 Real-corpus smoke test: `load_skills(Path("src/ohmystock/skills/registry"))` returns ≥ 10 specs, no duplicates, and every `cited_specs` list is non-empty.

## 5. Docs / SSOT

- [x] 5.1 Update `CLAUDE.md` §5 SSOT table — add a row for `Skill Registry foundation` pointing at `openspec/specs/skill-registry/spec.md` (post-archive), `src/ohmystock/skills/spec.py`, `src/ohmystock/skills/loader.py`, and `src/ohmystock/skills/registry/`.

## 6. Verification

- [x] 6.1 Run `pytest tests/test_skill_loader.py -v`; expect all green.
- [x] 6.2 Run full backend test suite (`pytest`); ensure no regressions (e.g. import-time failures from the no-longer-empty `skills/__init__.py`).
- [x] 6.3 `openspec validate skill-registry-foundation --strict`.
