## Why

The `wfa-validation-engine` change (archived 2026-05-13) ships a deterministic WFA gate that mechanizes the `validating → approved`/`rejected` transition — but the only way to fire it today is `uv run ohmystock validate-proposal <slug> ...` from a terminal. The admin UI already lists `validating` proposals at `/proposals` and shows their detail at `/proposals/:slug`, yet there's no "Run Validation" affordance there. Closing this last UX gap means the entire proposal lifecycle (created → pending → validating → approved/rejected → merged) is one-click-driveable from web-admin without ever dropping to CLI.

## What Changes

- **NEW endpoint** `POST /api/admin/proposals/{slug}/validate` under existing Bearer-auth guard:
  - Body: `{ strategy: str, period: {from, to}, param_overrides: dict[str, Any], universe: list[str], wfa_windows?: int = 5, in_sample_ratio?: float = 0.7, initial_capital?: int, dry_run?: bool = false }` (validated via pydantic `extra="forbid"`).
  - Reuses the same slug-resolution helper (`_resolve_slug_to_path`) and `_PROPOSALS_ROOT_FACTORY` test-seam already in `api/routes/proposals.py`.
  - Calls `ohmystock.validation.run_validation(...)` synchronously (validator is fast enough — 20 backtests over ~5s typical — no need for async/queue v0).
  - Builds `market_data_loader` from the same `get_connection() + select_bars` pair the CLI uses, behind a new `_MARKET_DATA_LOADER_FACTORY` test seam mirroring the CLI module.
  - Response envelope follows `{ok, data, error}` standard. On verdict=pass: `{ok: true, data: {verdict: "pass", slug, new_status: "approved", new_path: "PENDING_REVIEW/<slug>.md", report_path: "PENDING_REVIEW/<slug>.validation.json", deltas: {...}}}`. On verdict=fail: same shape with `new_status: "rejected"`. On `WfaValidationError`: HTTP 422 `{ok: false, error: {code: "wfa_validation_failed", message: "<token>: <detail>"}}`. On `ProposalStateError`: reuse existing `_STATE_ERROR_TO_ENVELOPE` mapping. On status != "validating": HTTP 409 `{code: "illegal_transition"}` (validator's own status check). On unknown strategy / missing bars / period_too_short: 400 `invalid_input`.
  - **No EventBus event** in v0 (deferred; same scope decision as `transition` endpoint).
  - **No background queue** in v0 — synchronous response carries verdict + new path. If a future change needs async (e.g. >30s validations), this endpoint stays — it'll just gain a `queue=true` flag.

- **MODIFIED** `/proposals/:slug` page — when frontmatter `status == "validating"`, the action row gains a new primary button `[Run Validation…]` (replacing today's "Mark Validating" affordance which is `pending`-only). Clicking opens a new `<ValidationDialog>`:
  - Required fields: Strategy (`<select>` populated from `listStrategies()`), Period (two `<input type=date>`), Universe (chip input, default `2330,0050,2317`).
  - Optional fields: WFA windows (number, default 5), IS ratio (number, default 0.7), Initial capital (number, default 1_000_000), Parameter overrides (key=value chip input — values parsed identically to CLI via the endpoint, **not** in browser).
  - Checkbox: "Dry run (preview verdict, no state change)".
  - Submit → `POST /api/admin/proposals/<slug>/validate` → on success: invalidate `['proposal', slug]` query, show toast `verdict=pass — moved to PENDING_REVIEW` (or `verdict=fail — moved to rejected — <failures count>`), close dialog. On error: keep dialog open, surface `{code}: {message}` inline same pattern as `<TransitionDialog>`.
  - Persists last-used Strategy + Universe + Initial capital + WFA windows + IS ratio to `localStorage['ohmystock.admin.lastValidation']` so repeat runs auto-fill.
  - Dry-run result toast: `verdict=pass (dry run, no state change)` + opens an expanded result card with the full `deltas` block + failure list (if any).

- **Intentionally deferred** (NOT in this change):
  - Async / background-job mode for long validations (>30s). v0 is synchronous because today's typical validation is ~5s.
  - EventBus `proposal_validated` event. Add when the wider `eventbus-emitters` capability gets its next batch.
  - LLM-driven `param_overrides` autosuggest from the proposal's `diff_draft`. Same human-in-loop reasoning as the CLI ships with.
  - Streaming per-window progress over SSE. Synchronous is fine until proven otherwise.
  - "Re-validate" affordance for already-approved/rejected proposals (would require a legal `approved → validating` edge in the state machine; out of scope).

## Capabilities

### New Capabilities
（無——本 change 全部走既有 capability 的 delta。）

### Modified Capabilities
- `admin-proposals-endpoints`: adds the `POST /api/admin/proposals/{slug}/validate` route + new `_MARKET_DATA_LOADER_FACTORY` test seam in the same module. No existing endpoint signature changes.
- `web-admin-proposals-pages`: adds `<ValidationDialog>` component + the conditional `[Run Validation…]` action row entry when `status == "validating"`. No layout or routing changes; the existing `<TransitionDialog>` stays for the `pending → validating` and `approved → merged`/`rejected` edges.

## Impact

- **Code 新增:**
  - `web-admin/src/components/validation-dialog.tsx`
  - `tests/api/test_admin_proposals_validate_endpoint.py`
- **Code 修改:**
  - `src/ohmystock/api/routes/proposals.py` — new route + `_MARKET_DATA_LOADER_FACTORY` indirection.
  - `web-admin/src/pages/ProposalDetailPage.tsx` — add `[Run Validation…]` button to the `validating` branch of the status-aware action row.
  - `web-admin/src/lib/api.ts` — new `validateProposal()` helper + types.
- **無:**
  - No new env vars / Settings fields.
  - No new DB schema / migration.
  - No EventBus event / SSE channel.
  - No LLM calls (validator stays fully deterministic — endpoint is a thin wrapper).
- **External deps:** none new — reuses `ohmystock.validation.run_validation`, `get_connection`, `select_bars`, the existing `_PROPOSALS_ROOT_FACTORY` pattern, and the existing shadcn `<Dialog>` primitive shipped with `<TransitionDialog>`.
- **CLAUDE.md §5 SSOT 新增一列** by archive step (pattern same as prior changes).
