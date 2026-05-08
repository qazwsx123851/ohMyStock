## Context

Phase 1 (deadline 2026-05-26) has shipped 14 backend capabilities (technical-indicators, chip-data-skill, screener-tw-universe, sepa-stage-classification, sepa-trend-template, rs-percentile, market-data-cache, phase-2b-scoring-engine, entry-decider, exit-engine, confirm-gate, auto-execute, trade-journal-schema, backtest-engine) but none of them are surfaced as a "skill" the LLM agent can discover at runtime. `docs/design-zh-TW.md` and `docs/web-admin-page-designs.md` §12 reference ~30 skills with YAML frontmatter + Markdown body — that's the design target — but the seed corpus and loader have never been written.

`src/ohmystock/skills/__init__.py` is empty (0 bytes). `PyYAML` is already pulled in by `pydantic-settings`'s dependency tree. Filesystem-driven Markdown is the simplest possible registry — same pattern used by Claude Code's own `.claude/skills/<name>/SKILL.md` files.

## Goals / Non-Goals

**Goals:**
- A typed `SkillSpec` model that downstream code (admin endpoint, future Agent SDK invoker) imports without re-parsing YAML.
- A pure-function loader that fails loud on malformed frontmatter — bad files crash at startup, never silently skip.
- 10 seed skills committed to the repo, each one pointing back at a deployed spec so they stay in sync with reality.
- Compatible with the future `/skills` admin endpoint (read-only v0, mirroring `/settings`).

**Non-Goals:**
- No "enabled" toggle, no DB persistence, no last-run tracking. v0 mirrors the static text on disk.
- No Markdown rendering. The loader returns the raw body string; rendering belongs in the page (and even then, plain `<pre>` is acceptable per page-designs SSOT §13).
- No PUT/edit via browser. `git` is the only mutation path.
- No `claude-agent-sdk` integration in this change. The skill files are documentation today and will become callable later by registering them with the SDK — out of scope for this foundation.
- No tag/category index. The category enum exists for filter UX in the future page; the loader returns flat `list[SkillSpec]`.

## Decisions

### D1: Filesystem Markdown, no DB
**Choice:** Skills live as `src/ohmystock/skills/registry/<name>.md` files. The loader walks the directory, parses each, returns a list.
**Rationale:**
- Editable via the same code-review flow as the rest of the project. Drift between skill content and shipped capability is caught in PR review.
- No migration story, no SQL, no concurrent-write semantics — defers all of that to "if we ever need it".
- Mirrors the ergonomics of Claude Code's own skill loader; LLM agents reading the codebase recognise the pattern.

**Alternatives considered:**
- *SQLite table with JSON body.* Rejected — adds a migration burden and a stale-on-startup risk (`Settings` already showed how immutable-at-process-start is fine).
- *Single YAML manifest listing all skills.* Rejected — long unified files merge-conflict; one-file-per-skill scales better with `git blame`.

### D2: `name` MUST equal filename stem
**Choice:** Loader raises `SkillLoadError` when `frontmatter.name != path.stem`.
**Rationale:** Without this invariant, two skills can share a `name` (last-loaded wins, silent shadowing). Enforcing equality also guarantees URL-safe routing — `/skills/:name` directly resolves to `<name>.md` without any name-to-slug translation step.

### D3: Category is a closed enum
**Choice:** `category: Literal["data", "indicator", "signal", "decider", "gate", "tool", "report"]`.
**Rationale:**
- Closed set keeps the future `/skills` filter dropdown finite.
- Mismatched typos (`indicators` vs `indicator`) fail at load time instead of producing a phantom category in the UI.
- 7 categories cover the 14 deployed capabilities cleanly: `data` (market-data, chip-data), `indicator` (technical-indicators, rs-percentile), `signal` (sepa-stage, sepa-trend-template, screener, phase-2b-scoring), `decider` (entry-decider), `gate` (exit-engine, confirm-gate, auto-execute), `tool` (trade-journal, backtest-engine), `report` (reserved for Phase 5 復盤).

**Alternatives considered:**
- *Open string category.* Rejected — every typo becomes a new category in the UI, cluttering the filter and making the SSOT useless.

### D4: `cited_specs` cross-reference
**Choice:** Each skill carries `cited_specs: list[str]` — kebab-case names of deployed spec capabilities the skill summarises.
**Rationale:** When the user (or LLM) clicks a skill, they want to jump to the source of truth. Storing the link in the skill avoids stale "last edited spec was…" comments. Loader does NOT verify these names exist in `openspec/specs/` — that would couple the loader to the OpenSpec layout. The page can do it later (or just render them as text).

### D5: Loader fails loud
**Choice:** Any parse error raises `SkillLoadError(path, reason)`. No `try / log-and-skip` fallback.
**Rationale:** A malformed skill file means a developer made a mistake. Skipping silently produces a registry that's quietly missing a card — bug class invisible until someone notices the count is wrong. Crashing makes the bad file impossible to ignore. Same philosophy as `_validate_admin_token()` failing fast in `create_app`.

## Risks / Trade-offs

- **[Risk]** 10 hand-written seed skills can drift from their underlying specs as those specs evolve. **Mitigation:** `cited_specs` field makes the link explicit; PR review for spec changes can grep for references and catch them. Acceptable for v0 — perfect drift detection is a tooling problem to solve later if needed.
- **[Risk]** Filesystem loader hits disk on every call. **Mitigation:** v0 expects to be called once at app startup or per admin request — both acceptable. If it becomes hot, wrap in `lru_cache` keyed on `(skills_dir, mtime)`. Don't optimise prematurely.
- **[Trade-off]** No edit-via-browser means Mark must `git pull` + edit + commit + restart to change skill content. Same trade as `/settings`, same justification: the source-of-truth flow is `git`, not the admin UI.
- **[Trade-off]** PyYAML pulls in `libyaml` C bindings on some platforms. Already a transitive dep, so net new risk = 0.
