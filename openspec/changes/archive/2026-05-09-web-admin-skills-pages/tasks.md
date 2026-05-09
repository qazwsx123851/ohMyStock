## 1. Backend — `routes/skills.py`

- [x] 1.1 Create `src/ohmystock/api/routes/skills.py` with module-level constant `_REGISTRY_DIR = Path(ohmystock.skills.__file__).resolve().parent / "registry"` and a private token tuple mirroring `loader._INVALID_NAME_TOKENS` (hardcoded inline + a comment pointing at the loader for the cross-test).
- [x] 1.2 Implement `GET /api/admin/skills` handler: call `load_skills(_REGISTRY_DIR)`, map each `SkillSpec` to `{name, description, category, body_preview, body_truncated, cited_specs}`, return `JSONResponse(200, to_success({"items": items}))`.
- [x] 1.3 Implement `GET /api/admin/skills/{name}` handler: validate `name` against the inline token tuple → 400 `invalid_input` envelope; call `load_skill(_REGISTRY_DIR, name)`; if `None` → 404 `not_found`; else map to `{name, description, category, body, cited_specs}` and return 200 success envelope.
- [x] 1.4 Wrap the body of both handlers in `try / except` that delegates to `map_exception_to_envelope(exc)` for unexpected errors (matches `routes/settings.py` pattern); ensure `SkillLoadError` and any other internal error never leaks the traceback to the client.
- [x] 1.5 Mount `Depends(require_admin)` on the router (NOT per-route) and ensure no other HTTP methods are registered.
- [x] 1.6 Register `skills_router` in `src/ohmystock/api/app.py` next to the other admin routers.

## 2. Backend — tests

- [x] 2.1 Add `tests/api/test_skills_endpoint.py` with a fixture that writes 3 valid skill `.md` files (one with body > 200 chars to exercise truncation, one with empty `cited_specs`) into `tmp_path` and `monkeypatch.setattr(routes.skills, "_REGISTRY_DIR", tmp_path)`.
- [x] 2.2 Test 200 list shape: keys exactly `{name, description, category, body_preview, body_truncated, cited_specs}`, ordering alphabetical by name, `body_truncated` set correctly for the long-body fixture.
- [x] 2.3 Test 200 detail shape including full body return and order-preserved `cited_specs`.
- [x] 2.4 Test 400 `invalid_input` envelope for each of `foo/bar`, `..`, `foo\\bar` URL-encoded into the path; assert no file under `tmp_path` is opened.
- [x] 2.5 Test 404 `not_found` envelope for a well-formed name that doesn't exist.
- [x] 2.6 Test 401 `auth_missing` and `auth_invalid` for both list and detail.
- [x] 2.7 Test 405 for POST and PUT on `/api/admin/skills` and `/api/admin/skills/market-data`.
- [x] 2.8 Test the token-tuple equality invariant: import `routes.skills._INVALID_NAME_TOKENS_LOCAL` (whatever name we pick) and `loader._INVALID_NAME_TOKENS`, assert they are equal; this fails closed if the loader adds a new traversal token.
- [x] 2.9 Test 200 with the *real* production registry (no monkeypatch): assert items length equals the number of `.md` files in `src/ohmystock/skills/registry/` (currently 10) and that `market-data` appears with the seed's actual `description`.
- [x] 2.10 Test 500 path: write a `.md` file with broken YAML frontmatter into `tmp_path`, hit the list endpoint, assert HTTP 500 + `ok: false` + envelope does not contain the string `Traceback`.

## 3. Frontend — API client

- [x] 3.1 In `web-admin/src/lib/api.ts`, add `SkillCategory` literal type, `Skill` and `SkillDetail` types matching the spec exactly.
- [x] 3.2 Add `listSkills(): Promise<{ items: Skill[] }>` and `getSkill(name: string): Promise<SkillDetail>` (encode the path component) at the bottom of the file next to `getSettings()`.
- [x] 3.3 In `web-admin/src/lib/__tests__/api.test.ts` (or sibling), add tests stubbing `fetch` to assert path encoding (`getSkill("foo bar")` hits `/api/admin/skills/foo%20bar`) and envelope unwrapping.

## 4. Frontend — `SkillsPage`

- [x] 4.1 Create `web-admin/src/pages/SkillsPage.tsx` rendering header + filter bar + responsive grid.
- [x] 4.2 Fetch via `useQuery({ queryKey: ['skills'], queryFn: listSkills, retry: false })`.
- [x] 4.3 Implement local `useState` for search string + selected category; derive a `filtered` array via simple `.filter()` (no debounce, no memo unless RTL test fails on render count).
- [x] 4.4 Render the loading state as 12 `Skeleton` cards in the same grid layout (so the layout doesn't jump on resolve).
- [x] 4.5 Render the empty-after-filter state with the "清除 filter" button that resets both filter inputs.
- [x] 4.6 Render the empty-registry state ("尚未註冊任何 skill") when the API returns `items: []` and filters are at defaults.
- [x] 4.7 Render the error state as the destructive `Card` + `AlertCircle` + retry button (mirror the pattern in `SettingsPage.tsx`).
- [x] 4.8 Each card uses shadcn `Card` with `cursor-pointer hover:bg-accent/40 transition-colors`, `tabIndex={0}`, `role="button"`, `aria-label={skill.name}`, and `onKeyDown` to trigger navigate on Enter.

## 5. Frontend — `SkillDetailPage`

- [x] 5.1 Create `web-admin/src/pages/SkillDetailPage.tsx`. Read `name` via `useParams<{ name: string }>()`.
- [x] 5.2 Fetch via `useQuery({ queryKey: ['skill', name], queryFn: () => getSkill(name!), retry: false, enabled: Boolean(name) })`.
- [x] 5.3 Render header: back-link (`<Link to="/skills">← Skills</Link>`), `<h1>{name}</h1>`, category `Badge`.
- [x] 5.4 Render cited-specs row: `cited_specs.map(s => <code>{s}</code>)` separated by space, or the literal "（無 cited_specs）" if empty.
- [x] 5.5 Render body in a `Card` with `<pre className="whitespace-pre-wrap font-mono text-sm">{body}</pre>`.
- [x] 5.6 Branch on `error.code === 'not_found'` to render the "找不到 skill: {name}" empty-state with "返回 Skills" button. Other errors → destructive Card + retry.
- [x] 5.7 Loading: a single Skeleton header row + a Skeleton body Card.

## 6. Frontend — wiring + tests

- [x] 6.1 Remove `SkillsPage` and `SkillDetailPage` from `web-admin/src/pages/stubs.tsx`.
- [x] 6.2 Update `web-admin/src/router.tsx` to import them from their new files. Run the existing router-smoke test and confirm it still passes.
- [x] 6.3 Add `web-admin/src/pages/__tests__/SkillsPage.test.tsx` covering: 10-card render with stub fetch, search filter narrows to a subset (no fetch fired), category select filters, empty-after-filter renders the clear button, error renders the retry Card.
- [x] 6.4 Add `web-admin/src/pages/__tests__/SkillDetailPage.test.tsx` covering: success renders body + cited-specs chips, empty `cited_specs` renders the "（無 cited_specs）" fallback, 404 renders the "返回 Skills" empty state, 500 renders retry.
- [x] 6.5 Run `pnpm test` (vitest) and `pnpm build` (tsc + vite) inside `web-admin/`; both must be green.

## 7. Docs + CLAUDE.md SSOT

- [x] 7.1 In `docs/web-admin-page-designs.md` §12, add a "v0 範圍" note above the wireframe stating that toggle / "最後跑" / inline edit are deferred and listing what v0 actually renders (filter bar, grid, name + description + category badge).
- [x] 7.2 In `docs/web-admin-page-designs.md` §13, add the same kind of "v0 範圍" note: read-only body in a `<pre>` block, no editor, no Save, no preview toggle, no Cmd+S.
- [x] 7.3 In `CLAUDE.md` §5, add a row pointing at the new spec files + endpoint module + page files (mirror the format of the existing `web-admin Settings page` row directly above it).

## 8. Smoke + ship

- [x] 8.1 Run `uv run pytest tests/api/test_skills_endpoint.py` — all green (22/22).
- [x] 8.2 Run full backend pytest: `uv run pytest -q` — no regressions (1018 passed).
- [x] 8.3 Inside `web-admin/`, run `pnpm test` and `pnpm build` — both green (174 tests + 483 KB bundle).
- [ ] 8.4 Manual smoke: launch the API, hit `GET /api/admin/skills` with a real Bearer token, then `GET /api/admin/skills/market-data` and `GET /api/admin/skills/does-not-exist`; verify shapes and HTTP codes. (Deferred — covered by automated production-registry test 2.9.)
- [ ] 8.5 Manual smoke (optional): start the Vite dev server, log in, click into `/skills`, filter for "rs", click into the `rs-percentile` card, confirm the body renders.
- [x] 8.6 Commit + push to `main` directly (per project memory `feedback_direct_push_main`); message follows the existing `feat(web-admin): /<page>` convention.
