## ADDED Requirements

### Requirement: `/proposals/:slug` exposes a [Run Validation…] action when status is `validating`

When the proposal detail page renders a proposal whose frontmatter `status === "validating"`, the status-aware action row SHALL include a new primary button labelled `Run Validation…` (kept in its original English label, no localisation churn). The button MUST be mounted alongside — not in place of — the existing manual override buttons (`Approve…` / `Reject…`) so a human can still bypass WFA when they intentionally want to.

The button MUST NOT appear for any status other than `validating`. The page MUST NOT alter its 404 / 422 / loading / error empty states.

#### Scenario: Run Validation appears only for validating status
- **WHEN** the user navigates to `/proposals/<slug>` and the loaded proposal's status is `validating`
- **THEN** the rendered action row contains a primary button with text `Run Validation…`
- **AND** the same row also contains the existing `Approve…` and `Reject…` buttons unchanged

#### Scenario: Run Validation absent for pending status
- **WHEN** the user navigates to `/proposals/<slug>` and the loaded proposal's status is `pending`
- **THEN** the action row contains the existing `Mark Validating` button
- **AND** the action row does NOT contain a `Run Validation…` button

#### Scenario: Run Validation absent for terminal statuses
- **WHEN** the loaded proposal's status is `merged` or `rejected`
- **THEN** the action row shows the existing "終局狀態" label
- **AND** the `Run Validation…` button is NOT rendered

---

### Requirement: ValidationDialog component shape and fields

The system SHALL ship a new component `<ValidationDialog>` at `web-admin/src/components/validation-dialog.tsx` built on the existing inline `<Dialog>` primitive at `components/ui/dialog.tsx` (same primitive `<TransitionDialog>` uses; no new Radix dependency).

The dialog MUST render the following fields in order:

1. **Strategy** (`<select>`) — required. Options populated from `listStrategies()` (the existing helper that backs the `/backtest` page's strategy picker). Default selection: persisted `localStorage["ohmystock.admin.lastValidation"].strategy` if present, otherwise the first registered strategy.
2. **Period from** (`<input type="date">`) — required.
3. **Period to** (`<input type="date">`) — required, MUST be `>= from`.
4. **Universe** (text input parsed as comma-separated tokens) — required, ≥1 token. Default: persisted value or literal `2330,0050,2317`.
5. **Parameter overrides** (textarea, one `key=value` line per row) — optional, may be empty. Whitespace-trimmed; blank lines ignored.
6. **WFA windows** (`<input type="number">`) — optional, default 5, MUST be `>= 2`.
7. **In-sample ratio** (`<input type="number" step="0.01">`) — optional, default 0.7, MUST be in `(0, 1)`.
8. **Initial capital** (`<input type="number">`) — optional, default 1_000_000.
9. **Dry run** (`<input type="checkbox">`) — optional, default unchecked.

The dialog footer MUST contain a `Cancel` button (closes the dialog without firing the request) and a primary `Run Validation` button (fires the request).

#### Scenario: dialog opens with persisted defaults
- **WHEN** the user clicks `Run Validation…` and `localStorage["ohmystock.admin.lastValidation"]` contains a prior value `{strategy: "sma_cross", universe: "2330", wfa_windows: 5, in_sample_ratio: 0.7, initial_capital: 1000000}`
- **THEN** the dialog renders with those fields pre-filled
- **AND** the Period fields are empty (date-specific values are NOT persisted)
- **AND** the Parameter overrides textarea is empty (proposal-specific overrides are NOT persisted)
- **AND** the Dry-run checkbox is unchecked (user reasserts per call)

#### Scenario: dialog opens with hard defaults when localStorage is empty
- **WHEN** the user clicks `Run Validation…` and `localStorage["ohmystock.admin.lastValidation"]` is unset
- **THEN** the dialog renders with `universe = "2330,0050,2317"`, `wfa_windows = 5`, `in_sample_ratio = 0.7`, `initial_capital = 1_000_000`
- **AND** the Strategy select shows the first strategy returned by `listStrategies()`

#### Scenario: cancel closes without firing
- **WHEN** the user opens the dialog and clicks `Cancel`
- **THEN** the dialog closes
- **AND** no network request is made
- **AND** `localStorage["ohmystock.admin.lastValidation"]` is unchanged

---

### Requirement: ValidationDialog submit wiring

On submit the dialog SHALL invoke `validateProposal(slug, body)` from `web-admin/src/lib/api.ts`. The request body SHALL be constructed as:

```
{
  strategy,
  period: { from, to },
  param_overrides: <textarea split into non-empty lines>,
  universe: <comma-separated parsed into trimmed non-empty tokens>,
  wfa_windows,
  in_sample_ratio,
  initial_capital,
  dry_run
}
```

While the request is in flight, the dialog primary button MUST be disabled and display a spinner; the dialog MUST NOT auto-close.

On success (HTTP 200), the dialog SHALL:
1. Persist `{strategy, universe, wfa_windows, in_sample_ratio, initial_capital}` to `localStorage["ohmystock.admin.lastValidation"]` (other fields intentionally excluded — see Requirement above).
2. Invalidate the React Query key `["proposal", slug]` so the page refetches the latest frontmatter / status / extra_frontmatter.
3. Close the dialog.
4. Show a toast whose message mirrors the response envelope:
   - `verdict=pass` non-dry-run → `Validated: verdict=pass — moved to PENDING_REVIEW`.
   - `verdict=fail` non-dry-run → `Validated: verdict=fail — moved to rejected — N failure(s)` where N = `failures.length`.
   - dry-run pass → `Dry run: verdict=pass — no state change`.
   - dry-run fail → `Dry run: verdict=fail — no state change — N failure(s)`.

On error (HTTP ≠ 200), the dialog MUST remain open and surface an inline error showing `{error.code}: {error.message}` immediately above the footer; the form fields MUST remain editable so the user can correct and resubmit.

#### Scenario: pass success persists settings, invalidates query, closes dialog
- **WHEN** the user submits and the endpoint returns `{ok: true, data: {verdict: "pass", new_status: "approved", ...}}`
- **THEN** `localStorage["ohmystock.admin.lastValidation"]` is updated with the strategy, universe, wfa_windows, in_sample_ratio, initial_capital from the just-submitted form
- **AND** the React Query cache key `["proposal", <slug>]` is invalidated
- **AND** the dialog closes
- **AND** a toast appears containing the substring `verdict=pass`

#### Scenario: fail success closes dialog with failure-count toast
- **WHEN** the user submits and the endpoint returns `{ok: true, data: {verdict: "fail", new_status: "rejected", failures: ["sharpe_gap: ..."]}}`
- **THEN** the dialog closes
- **AND** a toast appears containing `verdict=fail` and `1 failure`

#### Scenario: dry-run success keeps proposal at validating
- **WHEN** the user checks Dry-run and submits, receiving `{ok: true, data: {verdict: "pass", new_status: "validating", new_path: null}}`
- **THEN** the toast contains `Dry run` and `no state change`
- **AND** the React Query cache key `["proposal", <slug>]` is invalidated (so the page refetches and shows the unchanged status, confirming nothing moved)

#### Scenario: server error keeps dialog open with inline message
- **WHEN** the endpoint returns HTTP 422 with `{ok: false, error: {code: "wfa_validation_failed", message: "missing_bars: 2330"}}`
- **THEN** the dialog stays open
- **AND** the form fields are still editable
- **AND** the inline error region renders the text `wfa_validation_failed: missing_bars: 2330`
- **AND** no toast is shown

#### Scenario: in-flight request disables the submit button
- **WHEN** the user has clicked `Run Validation` and the request is in flight
- **THEN** the primary footer button is `disabled`
- **AND** clicking it again does NOT fire a second request
- **AND** the Cancel button remains enabled

---

### Requirement: validateProposal API helper shape

The system SHALL add `validateProposal(slug: string, body: ValidateRequest): Promise<ValidateResponse>` to `web-admin/src/lib/api.ts`. The helper MUST use the existing `apiFetch` wrapper so Bearer-token attachment, envelope parsing, and 401 auto-logout behave identically to sibling helpers (`listProposals`, `getProposal`, `transitionProposal`).

`ValidateRequest` and `ValidateResponse` TypeScript types MUST be exported alongside the helper. The response type's `new_path` and `report_path` MUST be typed `string | null` to accommodate dry-run.

The helper MUST throw on non-2xx responses with the envelope's `error` object attached so callers can pattern-match on `error.code` and render the message.

#### Scenario: helper throws structured error on non-2xx
- **WHEN** the endpoint returns HTTP 422 with `{ok: false, error: {code: "wfa_validation_failed", message: "..."}}`
- **THEN** `validateProposal(slug, body)` rejects with an Error whose `.code` is `wfa_validation_failed`
- **AND** `.message` is the server's message

#### Scenario: helper resolves with envelope data on 200
- **WHEN** the endpoint returns HTTP 200 with `{ok: true, data: {...}}`
- **THEN** `validateProposal(slug, body)` resolves with the `data` object (NOT the full envelope)
