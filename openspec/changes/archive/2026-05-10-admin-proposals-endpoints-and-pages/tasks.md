## 1. Backend — settings + route module skeleton

- [x] 1.1 Confirm/add `proposals_dir: Path = Path("proposals")` field on `Settings` (`src/ohmystock/config.py`); default is CWD-relative. If already present, skip; otherwise add with the same `Field(...)` style as other paths.
- [x] 1.2 Create `src/ohmystock/api/routes/proposals.py` with module docstring referencing `openspec/changes/admin-proposals-endpoints-and-pages/specs/admin-proposals-endpoints/spec.md` and the design decisions for `_PROPOSALS_ROOT_FACTORY` indirection.
- [x] 1.3 Define `_PROPOSALS_ROOT_FACTORY: Callable[[], Path]` as a module-level lambda calling `Settings().proposals_dir`. Add a comment block explaining the test-override pattern (`monkeypatch.setattr(routes.proposals, "_PROPOSALS_ROOT_FACTORY", lambda: tmp_path / "proposals")`).
- [x] 1.4 Define `_INVALID_NAME_TOKENS: tuple[str, ...] = ("/", "\\", "..", os.sep)` and `_is_safe_slug(slug)` helper (mirrors `routes/skills.py:46`).
- [x] 1.5 Define `_STATE_ERROR_TO_ENVELOPE: list[tuple[str, int, str]]` mapping table per design D10 + spec ProposalStateError requirement, in declared order: `unknown_status` → 400 invalid_input, `illegal_transition` → 409 illegal_transition, `missing_actor` → 400 invalid_input, `missing_validation_report` → 400 invalid_input, `missing_merged_to_version` → 400 invalid_input, `missing_rejection_reason` → 400 invalid_input, `destination_exists` → 409 conflict, `malformed_changelog` → 422 unprocessable_entity. Provide `_map_state_error(exc) -> tuple[int, dict]` that scans the table and falls back to `map_exception_to_envelope(exc)` for unrecognised messages.

## 2. Backend — frontmatter + changelog parsing helpers

- [x] 2.1 Add `_FRONTMATTER_RE` regex in the route module mirroring `proposal/writer.py:43` (`^---\s*\n(.*?)\n---\s*\n(.*)$` DOTALL).
- [x] 2.2 Add `_read_frontmatter(path) -> dict[str, str] | None` that reads UTF-8, applies the regex, parses `key: value` lines into a dict, and returns `None` (logging a structured warning) on any malformed input. MUST tolerate (skip) the optional appended keys `validation_report_path` / `merged_to_version` / `merged_at` / `rejected_reason`.
- [x] 2.3 Add `_TRANSITION_LINE_RE` and `_CREATED_LINE_RE` regexes for changelog parsing (per spec Detail-endpoint requirement). Add `_parse_changelog(section_text) -> list[dict]` that returns one of the 3 discriminated-union entry shapes (`transition` / `created` / `raw`). MUST skip blank lines and HTML comments (`<!-- ... -->`).
- [x] 2.4 Add `_resolve_slug_to_path(root, slug) -> Path | None` that probes `<root>/`, `<root>/PENDING_REVIEW/`, `<root>/merged/`, `<root>/rejected/` (in that order) for `<slug>.md`; returns the first match or `None`.
- [x] 2.5 Add `_summary_from_frontmatter(slug, fm) -> dict` that builds the `ProposalSummary` shape (slug, proposal_id, status, topic, target_section, created_by, created_at, review_id, priority). `topic` is derived from `proposal_id` by stripping the `<YYYY-MM-DD>-` prefix. `review_id == "null"` becomes `None`.

## 3. Backend — `GET /api/admin/proposals` (list endpoint)

- [x] 3.1 Implement `list_proposals_endpoint(status: str | None, limit: int, offset: int)` that:
  1. Validates `status` against the 5 `ProposalStatus` literals → 400 `invalid_input` on mismatch.
  2. Validates `offset >= 0` and clamps `limit` to `min(max(limit, 0), 200)` (default 50).
  3. Walks the 4 sub-locations of `_PROPOSALS_ROOT_FACTORY()` listing direct `.md` children only; skips files at root whose stem is one of the 3 sub-dir names.
  4. For each file, calls `_read_frontmatter`; skips `None` results with a `logger.warning`.
  5. Applies the in-memory `status` filter on the parsed frontmatter `status` value (NOT directory).
  6. Sorts by `created_at` descending, ties broken by `slug` descending.
  7. Slices `items[offset:offset+limit]` and computes `total` (post-filter, pre-pagination), `has_more`.
  8. Returns `JSONResponse(200, to_success({"items": items, "total": total, "limit": limit, "offset": offset, "has_more": has_more}))`.
- [x] 3.2 Wrap the body in `try / except` delegating to `map_exception_to_envelope` for any unexpected error (mirrors `routes/skills.py`).

## 4. Backend — `GET /api/admin/proposals/{slug}` (detail endpoint)

- [x] 4.1 Implement `get_proposal_endpoint(slug: str)` that:
  1. Validates `_is_safe_slug(slug)` → 400 `invalid_input`.
  2. Resolves `_resolve_slug_to_path(root, slug)`; if `None` → 404 `not_found` with message `"proposal not found: <slug>"`.
  3. Reads frontmatter via `_read_frontmatter`; if `None` → 422 `malformed_proposal`.
  4. Calls `parse_proposal(path)`; on `ProposalParseError` → 422 `malformed_proposal` with safe message `"proposal markdown is malformed: <safe-summary>"`.
  5. Reads the raw `## 8. 變更紀錄` section (split body by `_SECTION_BREAK_RE`) and parses it via `_parse_changelog`.
  6. Builds `extra_frontmatter` dict from the 4 optional keys present in raw frontmatter (omit absent).
  7. Builds the `data` payload per the spec shape (proposal summary fields + `body` dict + `changelog` + `extra_frontmatter`).
  8. Returns `JSONResponse(200, to_success(data))`.

## 5. Backend — `POST /api/admin/proposals/{slug}/transition` (transition endpoint)

- [x] 5.1 Define a pydantic `TransitionRequest` model with `new_status: ProposalStatus`, `actor: str`, `reason: str | None = None`, `validation_report_path: str | None = None`, `merged_to_version: str | None = None`. `extra="forbid"`.
- [x] 5.2 Implement `transition_proposal_endpoint(slug: str, body: TransitionRequest)` that:
  1. Validates `_is_safe_slug(slug)` → 400 `invalid_input`.
  2. Resolves the file via `_resolve_slug_to_path(root, slug)`; if `None` → 404 `not_found`.
  3. Calls `transition_proposal(path, body.new_status, actor=body.actor, reason=body.reason, validation_report_path=Path(body.validation_report_path) if body.validation_report_path else None, merged_to_version=body.merged_to_version)` inside `try`.
  4. On `ProposalStateError`, calls `_map_state_error(exc)` to get `(status, envelope)` and returns the JSONResponse.
  5. On `ProposalParseError` (raised by `transition_proposal` reading frontmatter / changelog), maps to 422 `malformed_proposal` per the same shape as the detail endpoint.
  6. On success, computes `new_path_relative = new_path.relative_to(root).as_posix()` and returns `JSONResponse(200, to_success({"slug": slug, "new_status": body.new_status, "new_path": new_path_relative}))`.
- [x] 5.3 Mount `Depends(require_admin)` on the router (NOT per-route). Register only the 3 endpoints + ensure no other HTTP methods on these paths.
- [x] 5.4 Register `proposals_router` in `src/ohmystock/api/app.py` next to the other admin routers.

## 6. Backend — tests (`tests/api/test_proposals_endpoint.py`)

- [x] 6.1 Add a `conftest.py`-level fixture `proposals_tmp_root` that creates `tmp_path/proposals` + the 3 sub-dirs, writes 5 fixture proposals (one per status) using `write_proposal` + `transition_proposal` to land them in the correct locations, and patches `_PROPOSALS_ROOT_FACTORY` via `monkeypatch.setattr`.
- [x] 6.2 Test list endpoint: 200 shape (5 items, sorted desc by created_at), correct `total/limit/offset/has_more`, all required keys present.
- [x] 6.3 Test list `?status=approved` filter: 1 item returned with `status == "approved"`.
- [x] 6.4 Test list `?status=approve` (typo): 400 `invalid_input`.
- [x] 6.5 Test list with a malformed file (write a `.md` with no frontmatter to root): item count drops by 1 silently; warning is logged via `caplog`.
- [x] 6.6 Test list status-source-of-truth: write a file with frontmatter `status: pending` into `<root>/merged/`; assert `?status=pending` includes it and `?status=merged` excludes it.
- [x] 6.7 Test list pagination clamps: `?limit=10000` → response uses `limit=200`; `?offset=-1` → 400 `invalid_input`.
- [x] 6.8 Test detail 200: full payload shape, body fields verbatim, changelog has the right `kind`, `extra_frontmatter` is `{}` for the pending fixture.
- [x] 6.9 Test detail with a transitioned file: changelog contains a `kind == "transition"` entry with `from_status` / `to_status` / `actor` matching the transition that produced it.
- [x] 6.10 Test detail with a rejected file: `changelog` last entry has `reason` populated; `extra_frontmatter` includes `rejected_reason`.
- [x] 6.11 Test detail with a merged file: `extra_frontmatter` contains `merged_to_version` + `merged_at`; absent keys (`validation_report_path`, `rejected_reason`) are NOT present.
- [x] 6.12 Test detail 404 for a well-formed but missing slug.
- [x] 6.13 Test detail 422 for a file with a missing body section: envelope `code == "malformed_proposal"`, message names the section, body does NOT contain `Traceback`.
- [x] 6.14 Test detail 400 `invalid_input` for path-traversal slugs (`foo/bar`, `..`, `foo\\bar`); assert no file is opened.
- [x] 6.15 Test transition 200 for `pending → validating`: response has `new_path` relative + forward-slash; file frontmatter on disk has `status: validating`; `## 8.` has one new transition line.
- [x] 6.16 Test transition 200 for `validating → approved`: file moves into `PENDING_REVIEW/`; `new_path == "PENDING_REVIEW/<slug>.md"`; frontmatter has `validation_report_path`.
- [x] 6.17 Test transition 409 `illegal_transition` for `pending → approved`; file unchanged.
- [x] 6.18 Test transition 400 `invalid_input` (substring `missing_validation_report`) for `validating → approved` without `validation_report_path`.
- [x] 6.19 Test transition 409 `conflict` (`destination_exists`) by pre-creating a stale `PENDING_REVIEW/<slug>.md`; both files unchanged after the failed call.
- [x] 6.20 Test transition 400 for `unknown_status` (typo `approve`).
- [x] 6.21 Test transition 404 for missing slug; 405 for `GET /api/admin/proposals/<slug>/transition`.
- [x] 6.22 Test 401 `auth_missing` and `auth_invalid` on all 3 endpoints.
- [x] 6.23 Parametrised test that exercises every row of `_STATE_ERROR_TO_ENVELOPE` (8 rows) by raising the corresponding `ProposalStateError(...)` from a monkeypatched `transition_proposal` and asserting the envelope output.

## 7. Frontend — API client (`web-admin/src/lib/api.ts`)

- [x] 7.1 Add `ProposalStatus` literal type, `Proposal`, `ProposalDetail`, `ProposalChangelogEntry` (discriminated union), `ProposalTransitionBody`, `ProposalTransitionResult` exactly as specified.
- [x] 7.2 Add `listProposals({ status?, limit?, offset? }?)` — composes query string with `URLSearchParams` (omit empty params), returns `Promise<{items, total, limit, offset, has_more}>`.
- [x] 7.3 Add `getProposal(slug)` calling `apiFetch<ProposalDetail>('/api/admin/proposals/' + encodeURIComponent(slug))`.
- [x] 7.4 Add `transitionProposal(slug, body)` calling `apiFetch` with `method: 'POST'`, header `Content-Type: application/json`, and `JSON.stringify(body)`.
- [x] 7.5 Add tests in `web-admin/src/lib/__tests__/api.test.ts` (or sibling): stub `fetch` and assert path encoding (`getProposal("2026-04-30-x y")` hits `/api/admin/proposals/2026-04-30-x%20y`), query-string composition for `listProposals`, POST shape for `transitionProposal`, envelope unwrapping for all three.

## 8. Frontend — `ProposalsPage` (`/proposals`)

- [x] 8.1 Create `web-admin/src/pages/ProposalsPage.tsx` with header + Tabs + DataTable layout.
- [x] 8.2 Read selected status from URL search param (`useSearchParams`); default `全部` (param absent). Tabs: `全部 / pending / validating / approved / merged / rejected`.
- [x] 8.3 Fetch via `useQuery({ queryKey: ['proposals', status], queryFn: () => listProposals(status === 'all' ? {limit: 50} : {status, limit: 50}), retry: false })`.
- [x] 8.4 Render `<DataTable>` with the 5 columns per spec, neutral `Badge variant="secondary"` for status, `Badge variant="outline"` for priority, `text-muted-foreground truncate` on `target_section`.
- [x] 8.5 Row click + Enter both navigate to `/proposals/<slug>` (`role="button"`, `tabIndex={0}`).
- [x] 8.6 Loading: 8 `<Skeleton>` rows.
- [x] 8.7 Empty (filter narrowed): centred "目前 <status> 沒有提案" + "回到全部" button (resets URL search param).
- [x] 8.8 Empty (registry returned `[]` and tab is `全部`): centred "尚無提案", no reset button.
- [x] 8.9 Error: destructive Card + `AlertCircle` + "重試" button calling `refetch()`. `role="alert"`.

## 9. Frontend — `ProposalDetailPage` (`/proposals/:slug`)

- [x] 9.1 Create `web-admin/src/pages/ProposalDetailPage.tsx`. Read `slug` via `useParams<{ slug: string }>()`.
- [x] 9.2 Fetch via `useQuery({ queryKey: ['proposal', slug], queryFn: () => getProposal(slug!), retry: false, enabled: Boolean(slug) })`.
- [x] 9.3 Render header (back-link, h1 topic, status `Badge variant="secondary"`, priority `Badge variant="outline"`).
- [x] 9.4 Render meta line (`created_by` + `created_at`) and "Target section" line.
- [x] 9.5 Render the optional "Extra metadata" `Card` (omit if `extra_frontmatter` is empty).
- [x] 9.6 Render the 7 body section Cards in order with `<h2>` titles + `<pre className="whitespace-pre-wrap font-mono text-sm">` body.
- [x] 9.7 Render the "變更紀錄" Card with `<ul>` and per-entry rendering by `kind`.
- [x] 9.8 Render the action row (separately specified in the next group).
- [x] 9.9 Branch on `error.code === 'not_found'` → empty state with "返回 Proposals". `error.code === 'malformed_proposal'` → destructive Card + back-link, NO retry. Other errors → destructive Card + `AlertCircle` + retry.
- [x] 9.10 Loading: header skeleton + 7 Card skeletons.

## 10. Frontend — transition action row + `<TransitionDialog>`

- [x] 10.1 Create `web-admin/src/components/transition-dialog.tsx` exporting `<TransitionDialog>` accepting `slug`, `target: 'approved' | 'merged' | 'rejected'`, `open`, `onOpenChange`.
- [x] 10.2 Render conditional fields per `target`: actor (always); validation_report_path (approved); merged_to_version (merged); reason (rejected).
- [x] 10.3 Disable submit while any required field for the chosen target is empty.
- [x] 10.4 On submit, call `transitionProposal(slug, body)` via `useMutation`. On success: write `actor` to `localStorage['ohmystock.admin.actor']`, close dialog, `queryClient.invalidateQueries({queryKey: ['proposal', slug]})`.
- [x] 10.5 On non-200, render the envelope `code` + `message` inline as `<p className="text-sm text-destructive">`; keep dialog open; re-enable submit.
- [x] 10.6 In `ProposalDetailPage`, render the action row at the bottom of the page driven by `data.status`:
  - `pending` → `[Mark Validating]` opening an `<AlertDialog>` confirmation (just actor input, defaulted from localStorage).
  - `validating` → `[Approve…]` `[Reject…]` opening `<TransitionDialog>` with the corresponding `target`.
  - `approved` → `[Mark Merged…]` `[Reject…]` similarly.
  - `merged` / `rejected` → muted "終局狀態" text, no buttons.
- [x] 10.7 The `[Mark Validating]` flow uses `<AlertDialog>` (NOT `<TransitionDialog>`) and submits with `{new_status: 'validating', actor}`.

## 11. Frontend — wiring + tests

- [x] 11.1 Remove `ProposalsPage` and `ProposalDetailPage` from `web-admin/src/pages/stubs.tsx`.
- [x] 11.2 Update `web-admin/src/router.tsx` to import them from their new files. Run the existing router-smoke test and confirm it still passes.
- [x] 11.3 Add `web-admin/src/pages/__tests__/ProposalsPage.test.tsx` covering: row render, status tab updates URL + triggers refetch, row click navigates, loading skeletons, empty-after-filter shows reset button, error shows retry.
- [x] 11.4 Add `web-admin/src/pages/__tests__/ProposalDetailPage.test.tsx` covering: header + body render, changelog list with all 3 `kind`s, action row variants per status, 404 / 422 / 500 error paths.
- [x] 11.5 Add `web-admin/src/components/__tests__/TransitionDialog.test.tsx` covering: required-field validation, submit flow + localStorage write + invalidation, server-error inline rendering, each `target` variant.
- [x] 11.6 Run `pnpm test` (vitest) and `pnpm build` (tsc + vite) inside `web-admin/`; both must be green.

## 12. Docs + CLAUDE.md SSOT

- [x] 12.1 In `docs/web-admin-page-designs.md`, add a "v0 範圍" note next to the `/proposals` row describing the 6-tab status filter, 5-column table, and what is deferred (no SSE, no body preview).
- [x] 12.2 In `docs/web-admin-page-designs.md`, add the same kind of "v0 範圍" note next to `/proposals/:slug`: read-only `<pre>` body, status-aware action row, no editor, no Save, no Markdown parser.
- [x] 12.3 In `CLAUDE.md` §5, add two rows: one for `admin-proposals-endpoints` pointing at the spec + `src/ohmystock/api/routes/proposals.py`; one for `web-admin-proposals-pages` pointing at the spec + page files + `web-admin/src/components/transition-dialog.tsx`.

## 13. Smoke + ship

- [x] 13.1 Run `uv run pytest tests/api/test_proposals_endpoint.py -q` — all green.
- [x] 13.2 Run full backend pytest: `uv run pytest -q` — no regressions.
- [x] 13.3 Inside `web-admin/`, run `pnpm test` and `pnpm build` — both green.
- [x] 13.4 Manual smoke (deferred OK if 13.1–13.3 are green): launch the API + dev server, log in, click into `/proposals`, switch tabs, click into a real fixture proposal, run a `pending → validating` transition, confirm the changelog updates and the file moved on disk; then run `git checkout proposals/` to roll back the smoke transition.
- [x] 13.5 Commit + push to `main` directly (per project memory `feedback_direct_push_main`); message follows the existing `feat(web-admin): /<page>` convention.
