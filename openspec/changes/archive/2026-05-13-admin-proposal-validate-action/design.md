## Context

`wfa-validation-engine` (archived 2026-05-13) exposes `ohmystock.validation.run_validation(...)` plus a `validate-proposal` Typer subcommand. The library is fully deterministic (no LLM, no network) and runs ~20 backtests over the requested period; on a 1-symbol 1-year universe it completes in roughly 3–8 seconds against in-memory bars. The existing admin endpoint module `src/ohmystock/api/routes/proposals.py:339` already carries the `_PROPOSALS_ROOT_FACTORY` test seam and the `Depends(require_admin)` mount; adding one more route on the same `APIRouter` is the smallest possible footprint. The proposal detail page `web-admin/src/pages/ProposalDetailPage.tsx` already renders a status-aware action row with a `<TransitionDialog>` mounted from `web-admin/src/components/transition-dialog.tsx`; the new dialog can clone that file's structure verbatim (Radix-free inline `<Dialog>` primitive at `components/ui/dialog.tsx`).

The validator's existing `WfaValidationError` exception carries a stable first-line token (`status_not_validating` / `unknown_strategy` / `period_too_short` / `missing_bars: <sym>` / `backtest_failed: ...` / `invalid_*: ...`) that callers pattern-match on. The endpoint MUST preserve this token in the response envelope so the dialog's inline error display reads naturally.

## Goals / Non-Goals

**Goals:**
- One synchronous endpoint that wraps `run_validation` with the same response-envelope and Bearer-auth invariants as the rest of `routes/proposals.py`.
- One dialog component that lets a human supply the same flags the CLI takes (strategy, period, universe, param overrides, wfa-windows, in-sample-ratio, initial-capital, dry-run).
- Reuse — not duplicate — the `_PROPOSALS_ROOT_FACTORY` and slug-resolution helpers already in the proposals route module.
- Preserve the validator's "token: detail" error shape verbatim in the envelope so the dialog can show actionable messages without per-error UI branches.
- Keep this change additive: no existing route, dialog, page, or capability changes signature.

**Non-Goals:**
- Async / background-queue mode. v0 stays synchronous; if real validations grow past ~30s we add `?async=true` in a separate change.
- EventBus `proposal_validated` event. Deferred to the next `eventbus-emitters` batch.
- LLM auto-population of `param_overrides` from `diff_draft`. Same human-in-loop reasoning the CLI ships with.
- Per-window SSE progress. Synchronous request/response is the smallest thing that works.
- A "Re-validate" affordance for `approved`/`rejected` proposals. Would require a new legal edge in the state machine; out of scope.
- Browser-side `ast.literal_eval`. The param value-typing rules live on the server (in `cli/_validate_proposal._parse_param_pairs`); the dialog sends the raw `key=value` list and the endpoint applies the same parsing. One source of truth.

## Decisions

### D1: Sync wrapper, not async queue
`run_validation` blocks for ~5s on typical inputs. FastAPI runs the route in a thread (sync def) so the event loop isn't pinned. Adding asyncio.run_in_executor + a background task table would more than triple the surface area of this change for zero v0 user value. Revisit when median validation time exceeds 20s in production.
- **Alternative considered:** kick off in background, poll status. Rejected — the user is staring at the dialog; making them wait synchronously is fine and avoids a status-table migration.

### D2: Endpoint payload mirrors the CLI flag set exactly
Body shape `{strategy, period, param_overrides, universe, wfa_windows?, in_sample_ratio?, initial_capital?, dry_run?}` is a direct projection of the CLI options. No new field names, no renames. This means a future LLM that drives the endpoint can also drive the CLI with literally identical params, and the dialog's `localStorage` cache can round-trip without translation.
- **Alternative considered:** flatten `period` to two top-level `period_from` / `period_to` fields. Rejected — keeps payload symmetric with the `ValidationReport` it returns (`report.period: {from, to}`) and matches the existing `transition` endpoint's nested-object convention.

### D3: Reuse `_PROPOSALS_ROOT_FACTORY`; add `_MARKET_DATA_LOADER_FACTORY`
The existing test seam for proposals root stays as-is — the new endpoint imports it from the same module. For bars I/O the endpoint adds a parallel `_MARKET_DATA_LOADER_FACTORY = lambda: (lambda sym, s, e: select_bars(get_connection(), sym, s, e))` so tests can `monkeypatch.setattr(routes.proposals, "_MARKET_DATA_LOADER_FACTORY", lambda: synthetic_loader)`. Same pattern as `cli._validate_proposal._MARKET_DATA_LOADER_FACTORY`.
- **Why two factories:** they have different lifetimes — proposals root reads `Settings()` per request; market loader needs a fresh sqlite connection per request. Combining them would force one factory to know about both concerns. Separate keeps tests focused.

### D4: Envelope-coded errors map to validator tokens 1:1
The body parser raises pydantic ValidationError → 422 `invalid_input` (FastAPI default). After that, only two exception classes can fire:
- `WfaValidationError(msg)` — emit 422 `wfa_validation_failed` with `message = msg` (keeps the `<token>: <detail>` prefix intact). Exception: if the first token is `status_not_validating`, emit 409 `illegal_transition` so the dialog can recognise the "you already validated this" case without parsing.
- `ProposalStateError` — reuse the existing `_map_state_error` → `_STATE_ERROR_TO_ENVELOPE` table already in this file.

Any other exception bubbles to `map_exception_to_envelope` → 500 `internal_error`, same as the rest of the module.

### D5: `period` is validated by pydantic, dates by string-regex only
The endpoint's `ValidateRequest.period` is a pydantic `PeriodModel(from_: str, to: str)` with `Field(alias="from")` and a `@field_validator` that checks `^\d{4}-\d{2}-\d{2}$` + `from <= to`. We do NOT parse to `datetime` server-side: the validator library re-parses with `date.fromisoformat` and the two parsers agree on the same regex. Keeps the route's responsibility narrow ("shape gate") and the library's narrow ("compute gate").

### D6: Response carries `new_path` + `report_path` as forward-slash strings relative to proposals root
Mirrors the existing `transition` endpoint's `new_path: "PENDING_REVIEW/<slug>.md"` convention so the dialog's success toast can deep-link without knowing about OS path separators. For verdict=pass: `new_path: "PENDING_REVIEW/<slug>.md"`, `report_path: "PENDING_REVIEW/<slug>.validation.json"`. For verdict=fail: `rejected/<slug>.md` and `rejected/<slug>.validation.json`. For dry-run: both fields are `null` and `new_status: "validating"` (unchanged).

### D7: Dialog persists a *partial* `lastValidation` to localStorage
We persist `{strategy, universe, wfa_windows, in_sample_ratio, initial_capital}` to `localStorage["ohmystock.admin.lastValidation"]` but NOT `period` (date-specific to the run) or `param_overrides` (proposal-specific) or `dry_run` (user reasserts per call). Same rationale as `<TransitionDialog>` only persists `actor` — preserve the boring stuff, force re-think of the decision-relevant stuff.

### D8: Validator runs in the request thread, not a worker
FastAPI's sync `def` route handlers run in a threadpool. `run_validation` is CPU-bound (Python-level backtest loop). With the default starlette executor (`ThreadPoolExecutor` of `min(32, cpu+4)`) a single concurrent call is fine. If multiple admin users validate simultaneously we'd block N workers for N×5s — acceptable for solo-dev v0. Re-evaluate if usage patterns change.

## Risks / Trade-offs

- **[Risk] Synchronous 5s call ties up one FastAPI worker thread per request** → if a future user kicks off 20 validations from 20 tabs, the threadpool saturates and other admin requests stall. **Mitigation:** dialog button enters a `disabled + spinner` state on submit so the same user can't fire multiples; the threadpool's bounded queue absorbs occasional bursts. If this proves wrong, D1 (async) becomes the upgrade path.
- **[Risk] Browser sends `param_overrides` as `{key: stringValue}` but the CLI's `ast.literal_eval` types values to int/float/bool/etc.** → if the dialog passes `{"fast": "10"}` instead of `{"fast": 10}`, `SmaCross.__init__` raises `TypeError("fast must be > 0")` because `0 < "10"` is a Python 3 error. **Mitigation:** the endpoint applies the same `_parse_param_pairs` helper as the CLI — dialog sends a `param: ["fast=10", ...]` array of `key=value` strings, server parses values consistently with `ast.literal_eval`. Single source of truth.
- **[Risk] `run_validation` may write half a report if the process dies mid-call** → handled by the existing `_write_report_atomic` tmpfile + os.replace. No new risk here.
- **[Risk] `new_path.relative_to(root).as_posix()` blows up if the validator returns a path outside the proposals root** → can't happen with current state-machine sinks (root / PENDING_REVIEW / merged / rejected) but worth defending: wrap the relative_to call in try/except and fall back to `str(new_path)` with a logger warning.
- **[Trade-off] Endpoint duplicates the CLI's universe/period parsing** → fine because they share the same pydantic + helper layer; the duplication is at the *route-wrapping* level (5 lines), not the validation logic.
- **[Trade-off] No EventBus event** → admin dashboard SSE feed won't show validation runs until a future change. Accepted because the user is on the `/proposals/:slug` page when they fire the action and gets the result inline.

## Migration Plan

No schema migration. No env var changes. Implementation order:
1. `routes/proposals.py` — add `ValidateRequest` pydantic model + `_MARKET_DATA_LOADER_FACTORY` + the new `POST /{slug}/validate` route. Reuse `_resolve_slug_to_path` and `_PROPOSALS_ROOT_FACTORY`.
2. `tests/api/test_admin_proposals_validate_endpoint.py` — 8 tests covering happy-pass / happy-fail / dry-run / status guard / unknown strategy / missing bars / malformed body / 401 unauthenticated.
3. `web-admin/src/lib/api.ts` — `validateProposal(slug, body)` helper + `ValidateRequest` / `ValidateResponse` types.
4. `web-admin/src/components/validation-dialog.tsx` — new dialog. Copy `<TransitionDialog>`'s scaffold (Dialog primitive + form + on-submit + error mapping), swap field set for the new payload.
5. `web-admin/src/pages/ProposalDetailPage.tsx` — branch the `status === "validating"` action row to render `[Run Validation…]` and wire it to the new dialog. Keep existing `[Approve…]`/`[Reject…]` so a human can still bypass WFA if they want (matches the existing transition endpoint's freedom).

Rollback: revert commit; no schema, no persistent state, the endpoint goes away and the dialog with it. Existing `/proposals` and `/proposals/:slug` continue to work unchanged.

## Open Questions

- **Q:** Should the dialog auto-populate `param_overrides` from the proposal's `diff_draft` via a regex/heuristic? **Tentative answer:** No — the diff is freeform markdown and any heuristic is wrong some of the time. Force the human to type the flags. When/if an LLM interpreter ships, it can prefill the dialog via a separate endpoint that calls Claude.
- **Q:** Should `[Run Validation…]` replace the existing `[Approve…]` / `[Reject…]` manual-override buttons when `status === "validating"`, or sit alongside them? **Tentative answer:** sit alongside. Manual override is still useful when the human knows the diff is correct but the validator's chosen universe wouldn't exercise it; removing the buttons would force a "validate first or revert to validating" workflow that's clunkier than the current freedom.

Neither blocks implementation; both have defensible defaults documented above. Re-open if implementation reveals a clearer answer.
