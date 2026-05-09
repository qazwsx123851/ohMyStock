## Why

`/skills` and `/skills/:name` are currently `ComingSoon` stubs (`web-admin/src/pages/stubs.tsx`), but as of `skill-registry-foundation` (archived 2026-05-09) the backend has 10 production seed skills loadable via `load_skills()` returning frozen `SkillSpec` objects. Mark needs a browser-side way to confirm which skills are deployed, what each one actually does, and which spec files it cites — today this requires `ls src/ohmystock/skills/registry/ && cat <name>.md` on the host, which defeats the point of a remote-accessible admin shell. The user-scenarios cold-start flow (`docs/user-scenarios.md` §10) explicitly assumes operators can audit registered skills before trusting the agent loop; the page-designs SSOT (`docs/web-admin-page-designs.md` §12–§13) has reserved this slot since v3 design.

We ship a **read-only v0** that lists every skill on disk and shows the full body + cited specs of one skill. Edit, save, enable/disable toggle, last-run timestamp, and search debounce are deferred — the registry foundation has no enabled flag and no execution log to surface, so any toggle UI would be cosmetic. This change closes the gap between "skills are deployable" and "skills are inspectable from the admin UI" without inventing storage that does not yet exist.

## What Changes

- New `GET /api/admin/skills` endpoint: returns the full list of `SkillSpec` objects loaded from the production registry directory (`src/ohmystock/skills/registry/`), sorted by name, with `body` truncated to a short preview (≤200 chars). Reuses existing Bearer auth + `{ok,data,error}` envelope. No filter / no search params (client-side filter only).
- New `GET /api/admin/skills/{name}` endpoint: returns one `SkillSpec` with full `body` and `cited_specs`. 404 envelope (`code: "not_found"`) when the skill does not exist; 400 (`code: "invalid_input"`) for path-traversal-style names rejected by `_validate_name`.
- New `SkillsPage` (`/skills`): replaces the stub. Filter bar (search input + category select, **client-side filter**, no debounce), grid of cards showing `name` / `description` / `category` badge. Card click → `/skills/<name>`. No enable toggle, no "last run" timestamp.
- New `SkillDetailPage` (`/skills/:name`): replaces the stub. Header with back-link + name + category badge + cited-specs row (each spec name as a `<code>` chip, no link). Body rendered as preformatted Markdown text inside a `Card` (no markdown parser — `<pre className="whitespace-pre-wrap">` only). No edit textarea, no preview toggle, no save button, no Cmd/Ctrl+S handler.
- Extend `web-admin/src/lib/api.ts` with `Skill` / `SkillDetail` types + `listSkills()` / `getSkill(name)` wrappers.
- Update `docs/web-admin-page-designs.md` §12–§13 to mark the read-only-v0 scope (note that toggle / editor / preview / save remain deferred).
- Add CLAUDE.md §5 SSOT row pointing at the new specs + endpoint files.

Out of scope (deferred, explicitly): PUT/PATCH endpoints, enabled toggle, last-run timestamp surfaces, Markdown renderer, YAML editor, search debounce, server-side `?category=`/`?q=` filtering, "previous / next skill" navigation, SSE subscription.

## Capabilities

### New Capabilities
- `admin-skills-endpoints`: `GET /api/admin/skills` (list, body preview only) and `GET /api/admin/skills/{name}` (full body + cited specs) under unified envelope, gated by Bearer auth, sourced from filesystem registry via `load_skills` / `load_skill`.
- `web-admin-skills-pages`: `/skills` route + `/skills/:name` route — read-only browse + read-only detail, replacing the existing `SkillsPage` / `SkillDetailPage` stubs.

### Modified Capabilities
- (none — both routes are stub-replacements; the existing `skill-registry` capability is consumed unchanged)

## Impact

- **Code**: new `src/ohmystock/api/routes/skills.py` + register in `api/app.py`; new `web-admin/src/pages/SkillsPage.tsx` and `web-admin/src/pages/SkillDetailPage.tsx`; remove `SkillsPage` / `SkillDetailPage` from `web-admin/src/pages/stubs.tsx`; update `web-admin/src/router.tsx` imports; extend `web-admin/src/lib/api.ts` with `listSkills` / `getSkill` + types; tests for endpoint (FastAPI `TestClient`) + page (RTL); CLAUDE.md §5 row + small note in `docs/web-admin-page-designs.md` §12–§13.
- **APIs**: 2 new GET endpoints. No schema migrations. No SSE event types added.
- **Dependencies**: none. Reuses already-installed `pyyaml`, `pydantic`, `react-query`, shadcn primitives.
- **Security**: filename safety relies on the existing `_validate_name` defence in `ohmystock.skills.loader` (rejects `/`, `\`, `..`, `os.sep` BEFORE filesystem access). Endpoint applies the same validation surface so a path-traversal attempt returns `invalid_input` before any disk read. No secret data is ever sent (skill files are public source).
- **Risk**: low. Read-only on a directory that ships in the repo; no write path, no broker behaviour change, no breaker change. Misuse-worst-case is exposing an unintended `.md` file under `src/ohmystock/skills/registry/`, which is mitigated by hardcoding that single dir as the load root.
