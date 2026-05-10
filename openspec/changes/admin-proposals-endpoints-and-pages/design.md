## Context

The proposal-handling backend is now mechanically complete (all archived 2026-05-10):

- **`proposal-writer`** ships `write_proposal(draft, dir)` + `parse_proposal(path) -> ProposalDraft` + `render_markdown(...)` (`src/ohmystock/proposal/writer.py`). Frontmatter keys = `proposal_id` / `target_section` / `status` / `created_by` / `created_at` / `review_id` / `priority`; body = 7 fixed `## N. <title>` sections + `## 8. 變更紀錄`.
- **`proposal-state-machine`** ships `transition_proposal(path, new_status, *, actor, reason=None, validation_report_path=None, merged_to_version=None) -> Path` + `ProposalStatus` (`Literal["pending","validating","approved","merged","rejected"]`) + `ProposalStateError` (`src/ohmystock/proposal/state.py`). 5 legal edges only; auto-moves files between `proposals/{root,PENDING_REVIEW,merged,rejected}/`; appends one `- <iso-ts> status: <old> → <new> by <actor>[ (<reason>)]` line to `## 8.`.
- **`post-trade-review-pipeline`** is the only writer of new proposals today (the `proposer` node calls `write_proposal()`).

The web-admin shell (`web-admin-shell`, archived 2026-05-07) gives us router, layout, `apiFetch` envelope client, Bearer auth lifecycle, shadcn primitives, react-query. Routes `/proposals` and `/proposals/:slug` already exist and render `ComingSoon` stubs from `web-admin/src/pages/stubs.tsx`.

The previous slice (`web-admin-skills-pages`) established the read-detail pattern this change extends: `Depends(require_admin)` router + `JSONResponse(to_success(...))` envelope, `apiFetch<T>` wrapper, react-query for fetch state, `<pre className="whitespace-pre-wrap">` for body, neutral `Badge variant="secondary"` for non-price-semantic tags, error `Card` with `AlertCircle` icon + `role="alert"`. The new wrinkle is the **mutation** endpoint — we need a small modal-driven action row that calls `POST /api/admin/proposals/{slug}/transition` and refetches detail on success.

## Goals / Non-Goals

**Goals:**

- A list page that surfaces every proposal on disk across all 4 status sub-locations, with a status filter — so Mark can answer "what's in my queue?" in one click.
- A detail page that renders the full markdown verbatim (no parser) plus a parsed changelog, and exposes only the legal next-state buttons for the current status.
- A transition endpoint that is a thin shim over `transition_proposal()`: parse body, call the function, map `ProposalStateError` to the standard envelope, on success return `{slug, new_status, new_path}`.
- Reuse `transition_proposal()` verbatim — no second copy of the state-machine logic, no business rules in the route layer.
- Keep the auth model unchanged (Bearer on every `/api/admin/*` route, including the new POST).

**Non-Goals:**

- WFA validation engine. The endpoint accepts a `validation_report_path` string and stores it; whether such a report actually exists is the caller's problem in v0.
- Auto-run scheduling. Operator clicks the button.
- Git commit / PR automation on `merged`. The transition just renames the file and updates frontmatter; merging the actual diff into cheatsheet is a separate v1 concern.
- EventBus `proposal_transitioned` event type. The admin SSE bus stays unchanged.
- Markdown renderer for the body. `<pre>` is enough.
- Full-text search across proposals, bulk-transition UI, `reverted_at` rollback flow.
- A separate Markdown-editor route (`/proposals/:slug/edit`). v0 is read + transition only.

## Decisions

**D1. Three endpoints: list, detail, transition.** `GET /api/admin/proposals` returns frontmatter-only summaries; `GET /api/admin/proposals/{slug}` returns full body + parsed changelog; `POST /api/admin/proposals/{slug}/transition` mutates. Why split list vs detail: list view never renders body, and proposals can grow long (7 sections + history); sending the full bodies on list mount wastes bytes and forces re-render on every filter keystroke. Alternative considered: single `GET /api/admin/proposals` returning everything — rejected for the same reason as `admin-skills-endpoints` D1.

**D2. List endpoint reads frontmatter only via a route-local helper, NOT `parse_proposal()`.** `parse_proposal()` requires all 7 body sections plus `## 8.` heading; it raises `ProposalParseError` on any deviation. For list, we want a tolerant pass that surfaces *every* file on disk. Route adds a small `_read_frontmatter(path) -> dict[str,str]` that uses the same `_FRONTMATTER_RE` pattern as the writer and returns the parsed key/value dict. If frontmatter is missing or malformed, the file is skipped and a structured warning is logged (not surfaced to the client). Alternative considered: call `parse_proposal()` per file and let exceptions bubble. Rejected — a single legacy file would 500 the entire list.

**D3. Detail endpoint uses `parse_proposal()` for the body sections + the same route-local helper for raw frontmatter.** This is necessary because `ProposalDraft` does not carry `status` (writer's invariant 1: `status` is always `pending` from the writer's POV) — but the detail response needs to surface the *current* status from frontmatter. Two reads of the same file are acceptable; both are local I/O on a small markdown file. Alternative considered: extend `ProposalDraft` to carry status. Rejected — that would break the writer's "callers cannot set status" invariant.

**D4. Changelog parsing is route-local, not exported.** A small `_parse_changelog(body_section_text) -> list[ChangelogEntry]` lives in the route module. Each line is matched against the regex `^- (?P<ts>\S+) (?:status: (?P<from>\w+) → (?P<to>\w+)|created) by (?P<actor>.+?)(?: \((?P<reason>.*)\))?$`. Lines that don't match are surfaced as `{kind: "raw", text: <line>}` so the UI can still display historical free-form notes. Why route-local: the changelog format is *output* of `transition_proposal`/`render_markdown` and the UI is its only reader; making it a public proposal-module API would force a contract that locks in the line format prematurely. Alternative considered: add `parse_changelog()` to `proposal.writer`. Rejected — premature export.

**D5. Slug is the filename stem (`<YYYY-MM-DD>-<topic>`), NOT the `proposal_id`.** They are equal for files on disk (the writer enforces `proposal_id == target.stem`), but using "stem" as the URL identifier keeps the route handler trivial: it just globs for `<slug>.md` across the 4 directories. Path-traversal validation rejects slugs containing `/`, `\`, `..`, or `os.sep`. Alternative considered: use `proposal_id` from frontmatter. Rejected — would require reading every file to find the matching id; O(n) detail lookup vs O(4) directory probe.

**D6. List endpoint walks 4 specific directories, NOT recursive glob.** It tries, in order, `<root>/`, `<root>/PENDING_REVIEW/`, `<root>/merged/`, `<root>/rejected/`, listing only direct `.md` children at each level. The root walk filters out the 3 sub-dir names so files-at-root aren't double-counted with their relocations. Why: keeps the surface predictable; a stray `.md` deeper down (e.g. `<root>/scratch/x.md`) is not a real proposal and shouldn't appear. Alternative considered: `proposals_root.rglob("*.md")`. Rejected — would surface unrelated files, including the `proposals/README.md`.

**D7. `proposals_root` is read from `Settings.proposals_dir`.** Falls back to `Path("proposals")` (CWD-relative). Tests override via `monkeypatch.setattr(routes.proposals, "_PROPOSALS_ROOT_FACTORY", lambda: tmp_path)` — the route module evaluates the path lazily per request so test scopes are honoured. Alternative considered: hardcode `Path("proposals")` like skills hardcodes its registry dir. Rejected — `proposals/` is content (changes per environment / per pytest tmp), not code (skills registry IS code, shipped in repo). The state machine itself uses the path the caller passes, so settings indirection is the clean place for it.

**D8. Status filter on the list endpoint uses an in-memory pass after the directory walk.** Even with a `?status=approved` query, we still walk all 4 directories — the file's frontmatter `status` is the truth, not its directory (per `proposal-state-machine` Decision: "current_status SHALL be read from frontmatter, NOT inferred from path"). Alternative considered: just walk the matching sub-dir. Rejected — would diverge from the state machine's source-of-truth contract; a misplaced file (manual edit) would silently disappear.

**D9. Transition endpoint accepts `actor` from request body, NOT the Bearer token.** The token is shared per-installation (one `OHMYSTOCK_ADMIN_TOKEN`), so the token tells us nothing about *who* clicked the button; `actor` is a free-form audit field that the operator types or that the UI prefills from `localStorage`. Alternative considered: derive `actor` from the token's identity. Rejected — there is no identity to derive; lying would make the audit log meaningless.

**D10. `ProposalStateError` → envelope mapping is exhaustive and explicit.** The route inspects the first-line message substring (`"unknown_status"` / `"illegal_transition"` / `"missing_actor"` / `"missing_validation_report"` / `"missing_merged_to_version"` / `"missing_rejection_reason"` / `"destination_exists"` / `"malformed_changelog"`) and maps to envelope codes:

| `ProposalStateError` substring | HTTP | envelope `code` |
|---|---|---|
| `unknown_status` | 400 | `invalid_input` |
| `illegal_transition` | 409 | `illegal_transition` |
| `missing_actor` | 400 | `invalid_input` |
| `missing_validation_report` | 400 | `invalid_input` |
| `missing_merged_to_version` | 400 | `invalid_input` |
| `missing_rejection_reason` | 400 | `invalid_input` |
| `destination_exists` | 409 | `conflict` |
| `malformed_changelog` | 422 | `unprocessable_entity` |
| (none of the above) | 500 | `internal_error` (via `map_exception_to_envelope`) |

Why substring-match instead of separate exception classes: the state machine ships one exception class with substring tags; introducing a hierarchy now would break its API. The mapping table lives in the route as a `_STATE_ERROR_TO_ENVELOPE: list[tuple[str, int, str]]` constant scanned in declared order. A test pins each substring to its expected envelope row.

**D11. Successful transition response shape: `{slug, new_status, new_path}` where `new_path` is relative to `proposals_root`.** Returning the absolute path leaks deployment layout; relative path is enough for the UI to display "Moved to PENDING_REVIEW/..." or to refetch. Alternative considered: return absolute path. Rejected — leakage.

**D12. Frontend action row: 5 transition buttons, conditionally rendered.** Driven by `current_status`:
- `pending` → `[Mark Validating]`
- `validating` → `[Approve…]` `[Reject…]`
- `approved` → `[Mark Merged…]` `[Reject…]`
- `merged` / `rejected` → no buttons, just a muted "終局狀態" label.
Each ellipsised button opens a modal collecting the required args; non-ellipsised buttons (just `[Mark Validating]`) submit immediately after a confirmation. `actor` defaults to `localStorage['ohmystock.admin.actor']` and persists on submit. Why ellipsis convention: matches OS-native UI grammar (button with `…` = opens further input).

**D13. Modal is one shadcn `<Dialog>` with conditional fields.** The same `<TransitionDialog>` component renders different fields based on which transition target the user picked. Why one component: 4 button variants × 4 separate dialogs = 16 surfaces to keep aligned; one dialog driven by a `target: ProposalStatus` prop is the simpler shape. Errors render inline below the form (`<p className="text-sm text-destructive">`).

**D14. On success, the dialog closes and the detail query is invalidated, NOT optimistically updated.** Optimistic UI on a state machine is a footgun (the file might not actually move if `os.replace` fails with `EXDEV` cross-device). Refetching is one extra round-trip but always correct.

**D15. List page uses tabs for status filter.** Six tabs: `全部 / pending / validating / approved / merged / rejected`. Tab change triggers a new `useQuery` keyed `['proposals', status]`; cache-stable when switching back. No SSE — proposals don't change without an operator action. Why tabs vs select: discoverability (operator can see which states have content at a glance); also matches `MemoryPage`'s segmented-control idiom.

**D16. List page table has 5 columns.** `created_at` (ISO, monospace) / `status` (`Badge variant="secondary"`) / `topic` (font-medium, click target) / `target_section` (truncate, `text-muted-foreground`) / `priority` (`Badge variant="outline"`). Click row → detail. Why no body preview column: rows already have 5 columns, and the detail page is one click away.

**D17. No 紅漲綠跌 anywhere on these pages.** Proposals carry no price semantic. Status and priority badges use neutral shadcn variants. The only destructive colour is the standard error `Card` (already paired with `AlertCircle` per `web-admin-skills-pages` Requirement: 紅漲綠跌 not applied; status-icon pairing only where needed).

**D18. Tests use `TestClient` against a `tmp_path/proposals` dir.** A fixture writes 5 fixture proposals (one per status sub-dir + one root) via `write_proposal()` then optionally `transition_proposal()` to land them in their target sub-dirs. The route is patched via `monkeypatch.setattr(routes.proposals, "_PROPOSALS_ROOT_FACTORY", lambda: tmp_path / "proposals")`. Endpoint tests focus on auth, envelope shape, status filter, slug-validation boundary, transition error mapping — not re-test the state-machine algebra (that has its own unit tests).

## Risks / Trade-offs

- **[Risk] Operator can corrupt audit history by submitting a misleading `actor` string.** → Mitigation: this is intentional (D9). The audit field documents who *claims* to have acted; in a single-user system it's the operator typing their own name. Document in `docs/auth-and-mask.md` that `actor` is operator-attestation, not server-attestation.
- **[Risk] If the operator clicks Reject on `validating`, the modal demands a `reason`, but the rejected file's frontmatter then has `rejected_reason` while the row in the changelog shows the same reason — slight redundancy.** → Acceptable. The frontmatter field is for machine reading (future analytics); the changelog line is for human reading on the detail page. Not deduplicated by design.
- **[Risk] `parse_proposal()` is strict: it requires all 7 body sections. Detail endpoint will 500 on a malformed file.** → Mitigation: route maps `ProposalParseError` to `code: "malformed_proposal"` 422 via the standard `map_exception_to_envelope` extension (a small one-line addition). Operator sees a clear error and can fix the file by hand.
- **[Risk] The list endpoint's frontmatter-tolerant pass means a file with malformed frontmatter is silently dropped.** → Mitigation: log a structured warning (`logger.warning("skipping malformed proposal: %s", path)`); future v1 can surface a "broken proposals" badge on the list page. v0 is acceptable because malformed proposals are operator-created (manual edits) — they'll notice the row missing.
- **[Risk] `_PROPOSALS_ROOT_FACTORY` indirection is non-obvious.** → Mitigation: comment in the route module pointing at the test pattern. Same idiom is used by `routes/skills.py` for `_REGISTRY_DIR` so it's consistent.
- **[Trade-off] No SSE means a second admin tab won't see transitions live.** → Acceptable. There's only one admin (Mark) and the transition cadence is human-paced (a few per month).
- **[Trade-off] Tabs for status filter wastes some horizontal space.** → Acceptable. The tabs serve as both filter and "what states do I have?" indicator.
- **[Risk] On `os.replace` cross-device errors (`EXDEV`), the state machine raises the underlying `OSError` unwrapped (per `proposal-state-machine` requirement).** → Mitigation: route maps unhandled `OSError` to `code: "internal_error"` 500 with a generic message; the original error is logged. The shared `map_exception_to_envelope` already handles this.

## Migration Plan

This is purely additive; no migration. Deployment steps:

1. Backend: add `routes/proposals.py`, register in `api/app.py`, extend `Settings` with `proposals_dir: Path = Path("proposals")` if not already present, run pytest.
2. Frontend: add `ProposalsPage` + `ProposalDetailPage` + `TransitionDialog` component, drop both from `stubs.tsx`, update `router.tsx`, run vitest + `pnpm build`.
3. Smoke: with a valid Bearer token, hit `GET /api/admin/proposals` (verify list shape across statuses), `GET /api/admin/proposals/<a-real-slug>` (verify body + changelog), and finally `POST /api/admin/proposals/<a-pending-slug>/transition` with `{new_status: "validating", actor: "mark"}` (verify 200 + file moved). Roll back the smoke transition by `git checkout proposals/`.
4. Update `docs/web-admin-page-designs.md` rows for `/proposals` and `/proposals/:slug` v0-scope note + CLAUDE.md §5 SSOT rows.
5. Push to main (solo-dev convention; no PR per project memory).

Rollback: revert the commit; the stubs come back automatically. No DB migration to undo. Any transitions that already happened persist as filesystem changes (the rollback removes the UI, not the state).

## Open Questions

- **Should `created_at` in the list response be the frontmatter `created_at` or the file `mtime`?** Tentatively frontmatter. The frontmatter is the authoritative authorship time; mtime drifts every transition (which is misleading for "when was this proposed"). Revisit if operators want a "last modified" sort.
- **Should the detail endpoint expose `proposal_id` separately from `slug`?** They're always equal today, but exposing both insulates the API from a future writer change that might decouple them. Ship both fields; cost is negligible.
- **Should the transition endpoint require a CSRF nonce?** No — admin is Bearer-token-only, no cookie auth, so CSRF is not applicable. Document this in the spec scenario for completeness.
