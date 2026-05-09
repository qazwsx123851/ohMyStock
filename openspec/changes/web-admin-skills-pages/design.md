## Context

The `skill-registry-foundation` change (archived 2026-05-09 as `2026-05-09-skill-registry-foundation`) shipped:

- `SkillSpec` (frozen pydantic, `extra="forbid"`) with fields `name / description / category / body / cited_specs` — `src/ohmystock/skills/spec.py`.
- `load_skills(skills_dir) -> list[SkillSpec]` and `load_skill(skills_dir, name) -> SkillSpec | None` — `src/ohmystock/skills/loader.py`. The loader is fail-loud (`SkillLoadError`) and applies path-traversal defence in `_validate_name` BEFORE any filesystem access.
- 10 production seed skills under `src/ohmystock/skills/registry/`: `chip-data`, `entry-decider`, `exit-engine`, `market-data`, `phase-2b-scoring`, `rs-percentile`, `screener`, `sepa-stage`, `sepa-trend-template`, `technical-indicators`.

The web-admin shell (`web-admin-shell`, archived) gives us router, layout, `apiFetch` envelope client, Bearer auth lifecycle, and shadcn primitives. `/skills` and `/skills/:name` routes already exist and render `ComingSoon` stubs from `web-admin/src/pages/stubs.tsx:10-11`.

`docs/web-admin-page-designs.md` §12–§13 is the visual SSOT for both pages, but it was authored when an `enabled` toggle and inline editor were planned. Since the foundation explicitly excluded those (no `enabled` field, no execution log table), the page-designs SSOT must be amended to mark the v0 scope as read-only browse + read-only detail.

The previous slice (`web-admin-settings-page`) established the pattern this change follows: `Depends(require_admin)` router + `JSONResponse(to_success(...))` envelope, `apiFetch<T>` wrapper in `web-admin/src/lib/api.ts`, react-query for fetch state, `Skeleton` / error `Card` for loading-empty-error.

## Goals / Non-Goals

**Goals:**

- Inspect-only `/skills` and `/skills/:name` that any human operator can audit from the browser without shell access.
- Reuse the existing `load_skills` / `load_skill` API verbatim — no new persistence, no new domain types.
- Stay coherent with the page-designs visual contract (Card grid, header, category badge, `loading-empty-error` triple) while marking explicitly which pieces of §12–§13 are deferred.
- Defence-in-depth: the endpoint validates `{name}` even though the loader already does, so an `invalid_input` envelope arrives before disk I/O.

**Non-Goals:**

- PUT/PATCH/DELETE endpoints, file writeback, YAML editor, Markdown renderer, dirty-state tracking, autosave, preview toggle.
- Server-side `?q=` / `?category=` filters (≤30 skills makes client-side filter trivial; deferring keeps the endpoint shape stable).
- Toggle / enable-disable (no `enabled` column anywhere; would be cosmetic).
- "Last run" timestamps (no execution log table exists; cosmetic without one).
- SSE subscription (skills don't change at runtime; reload-the-page is acceptable).

## Decisions

**D1. Two endpoints, not one.** `GET /api/admin/skills` returns the full list with truncated body preview; `GET /api/admin/skills/{name}` returns one skill with full body + `cited_specs`. Why split: list view never renders full body; sending ~10 × multi-KB markdown blobs over the wire on every page mount wastes bytes and forces re-render churn for filter typing. Alternative considered: single `GET /api/admin/skills` returning full bodies. Rejected — list view typing-search would re-render long markdown for every keystroke.

**D2. Body preview = first 200 chars of `body`, no smart truncation.** The list endpoint computes `body_preview = body[:200]` and exposes a `body_truncated: bool` flag. Why: simplest stable contract; any client that wants the full body must call the detail endpoint anyway. Alternative considered: send the description only and skip preview. Rejected — `description` is one line and operators want a peek at the actual instructions to disambiguate similar skills.

**D3. Hardcode the registry dir at `src/ohmystock/skills/registry/`.** The endpoint module resolves it once via a module-level constant (e.g. `_REGISTRY_DIR = Path(ohmystock.skills.__file__).resolve().parent / "registry"`), not via `Settings`. Why: configuration adds blast radius (a typo in env could expose any directory), and there is no genuine need to vary the path. Alternative considered: a `Settings.skill_registry_dir` field. Rejected — adding a settings field that nobody changes is exactly the kind of premature configurability `CLAUDE.md` §2 warns against.

**D4. Reuse the loader's path-traversal contract.** The route handler validates `name` against the same `("/", "\\", "..", os.sep)` token tuple the loader uses (`src/ohmystock/skills/loader.py:117`). On a hit, the route returns `to_error("invalid_input", …)` envelope, 400. Why: keeps the path-traversal contract single-sourced (the loader); the route mirrors it as defence-in-depth so we fail before disk I/O even if a future loader refactor weakens. Alternative considered: validate independently with new rules. Rejected — two definitions can drift.

**D5. 404 vs. 400 boundary.** A request like `GET /api/admin/skills/foo%2F..%2Fbar` is a *bad request*, not "skill not found", so it returns 400 `invalid_input`. A well-formed name that simply does not exist (`load_skill(...) is None`) returns 404 `not_found`. Why: 404 means "you asked correctly, it isn't here"; 400 means "you asked in a way I refuse to act on". Confusing the two would mask probing attempts as benign 404s in logs.

**D6. Frontend filter is client-side only, no debounce.** The list endpoint always returns all ≤30 skills; the filter input updates a `useState` and the grid re-renders. Why: with that few rows, network round-trip cost dwarfs any client-render cost; debouncing adds latency for no win. Alternative considered: server-side `?q=`. Rejected — would need its own ranking decisions; defer until count grows.

**D7. Detail page renders body as `<pre className="whitespace-pre-wrap font-mono text-sm">`.** No markdown parser, no syntax highlighter, no preview toggle. Why: read-only v0; renderers add bundle weight + XSS surface. The body is human-readable as plain text. Alternative considered: `react-markdown`. Rejected — postponed until the editor v1 needs it; introducing it now creates a dep that v0 doesn't justify.

**D8. Cited specs render as `<code>` chips, not links.** The strings stored in `cited_specs` are short capability names (e.g., `market-data-cache`); they are *not* URLs. Why: linking to spec files would either need a routing decision (open in new tab? in-app viewer?) or fail silently for archived specs. v0 surfaces the names so operators can grep; linking is a v1 concern.

**D9. Reuse `JSONResponse` envelope pattern from `routes/settings.py`.** All admin routes already wrap success in `to_success(data)` and exceptions in `map_exception_to_envelope(exc)`; this change does the same. No new auth, no new middleware. Why: consistency over novelty.

**D10. Tests use the same `TestClient` pattern as existing route tests.** A small fixture creates a temp dir, writes 2–3 valid skill files, and patches `_REGISTRY_DIR` in the route module. Why: the loader has its own unit tests; the endpoint test should focus on routing, auth, envelope shape, and 400/404 boundaries — not re-test parsing.

## Risks / Trade-offs

- **[Risk] Page-design SSOT (§12–§13) shows enable toggles and inline editor; users may expect them.** → Mitigation: both `proposal.md` and the new spec mark these as deferred; we add a one-paragraph "v0 scope" note at the top of §12 / §13 in `docs/web-admin-page-designs.md` flagging which slots are stubbed (Switch, Save button, dirty state, "last run" column, preview toggle).
- **[Risk] Body preview at 200 chars may cut mid-CJK character.** → Mitigation: Python `str` slicing handles unicode codepoints, not bytes, so the slice is safe for CJK. We don't try to align on word boundaries; the preview just terminates at the slice and the UI shows it as "…" if `body_truncated` is true.
- **[Risk] Importing the loader's private `_validate_name` from the route couples the route to a private API.** → Mitigation: D4 chooses the "mirror the token tuple inline" path. The route module pins this against the public-but-underscored `_INVALID_NAME_TOKENS` value with a parameterised test that imports both and asserts equality, so a future loader change to add a token is caught immediately.
- **[Trade-off] Hardcoded registry dir means there is no way to point the endpoint at a different directory in production.** → Acceptable; tests use `monkeypatch.setattr(ohmystock.api.routes.skills, "_REGISTRY_DIR", tmp_path)` which is the only place that needs to vary it.
- **[Trade-off] Without a markdown renderer, body display is monospaced and unstyled.** → Acceptable for v0; explicitly called out in the page-designs amendment.
- **[Risk] If a future skill grows a body >> 200 chars and the preview at exactly 200 ends inside a fenced code block, the list looks ugly.** → Mitigation: this is purely cosmetic; detail view always shows the full body. Document the truncation rule next to the field in the spec.

## Migration Plan

This is purely additive; no migration. Deployment steps:

1. Backend: add `routes/skills.py`, register in `api/app.py`, run pytest.
2. Frontend: add `SkillsPage` + `SkillDetailPage`, drop both from `stubs.tsx`, update `router.tsx`, run vitest + `pnpm build`.
3. Smoke: hit `GET /api/admin/skills` with a valid Bearer token, verify list shape; hit `GET /api/admin/skills/market-data` and `GET /api/admin/skills/does-not-exist` to verify 200 + 404.
4. Update `docs/web-admin-page-designs.md` §12–§13 v0-scope note and CLAUDE.md §5 row.
5. Push to main (solo-dev convention; no PR per project memory).

Rollback: revert the commit; the stubs come back automatically.

## Open Questions

- **Should the list endpoint expose `path` (relative to registry dir) so the UI can show "where this file lives"?** Tentatively no for v0 — leaks filesystem layout, has no operator value yet. Revisit if a future "open in editor" flow needs it.
- **Should `cited_specs` validate that the named specs actually exist in `openspec/specs/`?** Tentatively no — that is a registry / loader concern, not an endpoint concern, and adding the check here couples the API to the spec directory layout. Revisit when the registry adds its own integrity check.
