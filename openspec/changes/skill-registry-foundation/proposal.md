## Why

`/skills` and `/skills/:name` admin pages are blocked: there is no skill registry in the project. `src/ohmystock/skills/__init__.py` is empty, no `SkillSpec` exists, no skill `.md` files are on disk. `docs/web-admin-page-designs.md` §12 assumes ~30 skill cards exist with YAML frontmatter + Markdown body, but Phase 1 (deadline 2026-05-26) has shipped capabilities (technical-indicators, chip-data, screener, RS-percentile, SEPA, backtest-engine, etc.) without ever introducing a "skill" abstraction layer over them.

This change adds the foundation only — no UI, no admin endpoint. Once it ships, a follow-up change (`web-admin-skills-pages`) can wire `/skills` and `/skills/:name` directly on top with the same read-only-v0 pattern that `/settings` used.

The deferred-PUT pattern from `/settings` applies here too: skill files live on disk and are edited via `git`, not via a browser save button. v0 is read-only.

## What Changes

- New `src/ohmystock/skills/` package with:
  - `spec.py` defining `SkillSpec` (pydantic `BaseModel`, frozen): `name`, `description`, `category`, `body` (markdown body), `cited_specs` (list of deployed spec capability names).
  - `loader.py` with `load_skills(skills_dir: Path) -> list[SkillSpec]` and `load_skill(skills_dir: Path, name: str) -> SkillSpec | None`. Pure-Python YAML frontmatter parser (`PyYAML` already a transitive dep via `pydantic-settings`); no Markdown rendering at load time.
  - `__init__.py` exporting `SkillSpec`, `load_skills`, `load_skill`, `SkillLoadError`.
- New on-disk skill format under `src/ohmystock/skills/registry/<name>.md` — single file per skill, kebab-case `name` matches filename stem. Frontmatter: `name`, `description`, `category` (one of fixed enum: `data` / `indicator` / `signal` / `decider` / `gate` / `tool` / `report`), `cited_specs` (list).
- Seed 10 skill cards covering already-shipped Phase 1 / 2 / 3 capabilities: `market-data`, `chip-data`, `technical-indicators`, `rs-percentile`, `sepa-stage`, `sepa-trend-template`, `screener`, `phase-2b-scoring`, `entry-decider`, `exit-engine`. Each body is a 5-15 line summary with **Purpose** / **Inputs** / **Outputs** / **See also** sections.
- Loader contract: skip files starting with `_`; raise `SkillLoadError` (with file path) on (a) missing required frontmatter keys, (b) `name` mismatch with filename, (c) `category` outside the enum, (d) malformed YAML.
- CLAUDE.md §5 SSOT row added pointing at the spec + loader + seed directory.

Out of scope (deferred): admin endpoint (`GET /api/admin/skills`), web-admin pages, "enabled" toggle / persistence, last-run tracking, edit-via-browser, Markdown rendering, FTS over skill bodies.

## Capabilities

### New Capabilities
- `skill-registry`: `SkillSpec` schema + on-disk Markdown format + `load_skills` filesystem loader + 10-skill seed corpus.

### Modified Capabilities
- (none)

## Impact

- **Code**: new `src/ohmystock/skills/{spec,loader,__init__}.py` (3 files); new `src/ohmystock/skills/registry/<10-files>.md` (10 files).
- **Tests**: new `tests/test_skill_loader.py` covering happy path, all 4 validation errors, empty directory, ignored `_*.md` files.
- **Dependencies**: `PyYAML` is already pulled in transitively by `pydantic-settings` — verify before adding to `pyproject.toml` explicitly.
- **APIs**: no HTTP endpoints. No SSE event types.
- **Risk**: low. Loader is pure-function; no DB, no network, no I/O outside the skills directory.
- **Future hook**: `web-admin-skills-pages` change can `import { load_skills }` and add a `GET /api/admin/skills` admin endpoint that returns redacted `SkillSpec` rows. v0 there will mirror `/settings` (read-only, no PATCH/PUT).
