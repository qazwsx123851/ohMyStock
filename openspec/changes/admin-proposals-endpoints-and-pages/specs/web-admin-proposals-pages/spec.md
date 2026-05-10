## ADDED Requirements

### Requirement: `/proposals` route renders read-only list

The web-admin SHALL render `/proposals` via a new `ProposalsPage` component (replacing the existing `ComingSoon` stub at `web-admin/src/pages/stubs.tsx`). The page MUST fetch from `GET /api/admin/proposals?status=<selected>&limit=50` via the shared `apiFetch<T>` client wrapped in a `useQuery` hook with key `['proposals', selectedStatus]`.

The page MUST present, in vertical order: a page header with `<h1>Proposals</h1>` + a one-line description, a status `<Tabs>` row (6 tabs: 全部 / pending / validating / approved / merged / rejected), and a `<DataTable>` of proposal rows.

The table MUST have exactly 5 columns in this order: `created_at` (ISO string, monospace), `status` (`Badge variant="secondary"` with the literal status text), `topic` (font-medium), `target_section` (`text-muted-foreground` truncated to 1 line on overflow), `priority` (`Badge variant="outline"` with the literal priority text).

Clicking anywhere on a row MUST navigate to `/proposals/<slug>` via `react-router-dom` `useNavigate`. Each row MUST be keyboard-focusable; pressing Enter while a row has focus MUST navigate the same way.

The page MUST NOT render: SSE listeners, edit buttons, body previews, or transition buttons (all transitions happen on the detail page).

#### Scenario: list loads and renders rows
- **WHEN** the user opens `/proposals` with a valid Bearer token
- **AND** the endpoint returns 5 proposals (one per status)
- **THEN** 5 rows render in the table
- **AND** each row shows the 5 columns in order
- **AND** each status `Badge` uses `variant="secondary"` (no `text-up` / `text-down` colour)

#### Scenario: row click navigates to detail
- **WHEN** the user clicks a row whose `slug` is `2026-04-30-x`
- **THEN** the router navigates to `/proposals/2026-04-30-x`

#### Scenario: row keyboard navigation
- **WHEN** the user Tab-focuses a row and presses Enter
- **THEN** the router navigates to `/proposals/<that-row-slug>`

---

### Requirement: `/proposals` status tabs drive query

The 6 status tabs SHALL be exactly: `全部`, `pending`, `validating`, `approved`, `merged`, `rejected`. Selecting `全部` MUST omit the `?status=` query parameter; selecting any other tab MUST send that literal value as `?status=`.

Tab change MUST trigger a new fetch via react-query's keyed cache (`['proposals', status]`) — switching back to a previously-viewed tab MUST serve from cache without a network roundtrip.

The active tab MUST persist in URL search params so that navigating away and back via browser history restores the same view.

#### Scenario: status tab updates query
- **WHEN** the user clicks the `approved` tab
- **THEN** the network request is `GET /api/admin/proposals?status=approved&limit=50`
- **AND** only rows with `status == "approved"` render

#### Scenario: 全部 tab omits status param
- **WHEN** the user clicks the `全部` tab
- **THEN** the network request is `GET /api/admin/proposals?limit=50` (no `status=` parameter)

#### Scenario: tab persists in URL
- **WHEN** the user selects `pending` and then opens a new tab via browser back
- **THEN** the URL retains `?status=pending`
- **AND** the same tab is active on remount

---

### Requirement: `/proposals` loading-empty-error states

The page SHALL render distinct loading, empty, and error states:

- **Loading**: 8 `Skeleton` table rows (NOT spinners), per `docs/web-admin-page-designs.md` §共用 patterns.
- **Empty (filter narrowed to 0)**: a centred message "目前 <status> 沒有提案" plus a `Button variant="outline"` labelled "回到全部" that resets the tab to `全部`.
- **Empty (registry returned `[]` overall)**: a centred message "尚無提案" with no reset button.
- **Error**: a top-of-page `Card` with `border-destructive/50 bg-destructive/5`, an `AlertCircle` icon (`size-4 text-destructive`), the error message text, and a `Button` "重試" that calls `query.refetch()`. The Card MUST have `role="alert"`.

#### Scenario: loading shows 8 skeleton rows
- **WHEN** the page mounts and the query is in flight
- **THEN** 8 `Skeleton` row placeholders render
- **AND** no row or error UI is visible

#### Scenario: empty after status filter
- **WHEN** the `rejected` tab is active and `total == 0`
- **THEN** the empty message "目前 rejected 沒有提案" renders
- **AND** the "回到全部" button is visible
- **WHEN** the user clicks "回到全部"
- **THEN** the `全部` tab activates and the query refetches

#### Scenario: error shows retry
- **WHEN** the endpoint returns 500
- **THEN** a destructive `Card` renders at the top of the page with `role="alert"`
- **AND** the error message is shown
- **AND** clicking "重試" calls the underlying query's refetch

---

### Requirement: `/proposals/:slug` route renders read-only detail

The web-admin SHALL render `/proposals/:slug` via a new `ProposalDetailPage` component (replacing the existing stub). The page MUST fetch from `GET /api/admin/proposals/{slug}` via `apiFetch` wrapped in `useQuery` with key `['proposal', slug]`.

The page MUST display, in this order:

1. A header row with a `<Link to="/proposals">← Proposals</Link>` back-link, the proposal `topic` as `<h1>`, a `status` `Badge variant="secondary"`, and a `priority` `Badge variant="outline"`.
2. A meta line showing `created_by` and `created_at` (ISO string).
3. A "Target section" line showing `target_section` verbatim.
4. An "Extra metadata" `Card` rendering each key/value pair from `extra_frontmatter` (omitted if `extra_frontmatter` is empty). `validation_report_path`, `merged_to_version`, `merged_at`, `rejected_reason` SHALL each render with their literal key as label.
5. Seven `Card` blocks for the body sections, in order: `## 1. 改動描述` / `## 2. 動機與佐證` / `## 3. 改動 diff 草稿` / `## 4. 預期影響範圍` / `## 5. 風險評估` / `## 6. 驗證計畫` / `## 7. 預期改善幅度`. Each Card MUST contain the section title as a `<h2>` and the body text as `<pre className="whitespace-pre-wrap font-mono text-sm">{section}</pre>`.
6. A "變更紀錄" `Card` rendering `changelog` as a `<ul>` (one `<li>` per entry). `kind == "transition"` entries SHALL render as `<timestamp> — <from_status> → <to_status> by <actor>` plus an italic reason if present. `kind == "created"` entries SHALL render as `<timestamp> — created by <actor>`. `kind == "raw"` entries SHALL render as `<pre>{text}</pre>`.
7. The transition action row (separately specified below).

The page MUST NOT render: a Save button, an Edit button, a YAML editor `<Textarea>`, dirty-state UI, autosave hints, or a `<form>` for editing the body. There MUST NOT be a Markdown parser; all body text SHALL render as preformatted text.

#### Scenario: detail loads and renders
- **WHEN** the user opens `/proposals/2026-04-30-x` with a valid Bearer token
- **AND** the endpoint returns the full payload with all 7 sections and 1 changelog entry
- **THEN** the header shows `← Proposals`, the topic as h1, status badge, priority badge
- **AND** the 7 body Cards each render with their section title and `<pre>` body text
- **AND** the 變更紀錄 Card renders 1 list item

#### Scenario: extra_frontmatter omitted when empty
- **WHEN** the loaded proposal has `extra_frontmatter == {}`
- **THEN** the Extra metadata Card SHALL NOT render

#### Scenario: extra_frontmatter renders for merged proposal
- **WHEN** the loaded proposal has `extra_frontmatter == {"merged_to_version": "v3.1", "merged_at": "2026-05-12T10:00:00+08:00"}`
- **THEN** the Extra metadata Card renders with two label/value pairs in that order

---

### Requirement: `/proposals/:slug` 404, 422, and error states

When the endpoint returns 404 (`code: "not_found"`), the page SHALL render an empty state with the message "找不到提案: {slug}" and a `Button variant="outline"` "返回 Proposals" linking to `/proposals`. The page MUST NOT show body / changelog / action-row sections in this state.

When the endpoint returns 422 (`code: "malformed_proposal"`), the page SHALL render the destructive error `Card` with the envelope `message` text + a "返回 Proposals" link. There MUST NOT be a "重試" button (retrying does not fix a malformed file on disk).

When the endpoint returns 400 (`invalid_input`) or 500, the page SHALL render the same destructive `Card` + `AlertCircle` + "重試" pattern as `/proposals`. The retry button calls `refetch()`.

#### Scenario: 404 shows back-link
- **WHEN** the client navigates to `/proposals/nonexistent`
- **AND** the endpoint returns HTTP 404 with `code: "not_found"`
- **THEN** the page shows "找不到提案: nonexistent" plus a "返回 Proposals" button
- **AND** no body Card or action row is rendered

#### Scenario: 422 shows fix-on-disk message
- **WHEN** the endpoint returns HTTP 422 with `code: "malformed_proposal"`
- **THEN** the page renders the destructive Card with the envelope message
- **AND** there is NO "重試" button
- **AND** there is a "返回 Proposals" link

#### Scenario: 500 shows retry
- **WHEN** the endpoint returns HTTP 500
- **THEN** the page renders the destructive Card with `role="alert"` and a "重試" button
- **AND** clicking retry calls `refetch()`

---

### Requirement: `/proposals/:slug` transition action row

The detail page SHALL render an action row at the bottom whose visible buttons depend on `data.status`:

- `pending` → one button: `[Mark Validating]` (no ellipsis; submits immediately after a `<AlertDialog>` confirmation)
- `validating` → two buttons: `[Approve…]` and `[Reject…]` (both ellipsised; open `<TransitionDialog>`)
- `approved` → two buttons: `[Mark Merged…]` and `[Reject…]` (both ellipsised)
- `merged` or `rejected` → no buttons; render a muted `<p className="text-muted-foreground">終局狀態</p>` instead

The buttons MUST NOT be `disabled` for legal-but-not-current transitions (e.g. `pending` MUST NOT show a disabled `[Approve]` button) — only the legal next-state buttons SHALL appear.

`actor` for every transition MUST default to `localStorage.getItem('ohmystock.admin.actor') ?? ''` and MUST be persisted to that key on successful submit.

#### Scenario: pending action row
- **WHEN** the loaded proposal has `status == "pending"`
- **THEN** the action row renders exactly one button labelled "Mark Validating"
- **AND** there are no other transition buttons

#### Scenario: validating action row
- **WHEN** the loaded proposal has `status == "validating"`
- **THEN** the action row renders exactly two buttons labelled "Approve…" and "Reject…"

#### Scenario: approved action row
- **WHEN** the loaded proposal has `status == "approved"`
- **THEN** the action row renders exactly two buttons labelled "Mark Merged…" and "Reject…"

#### Scenario: merged terminal label
- **WHEN** the loaded proposal has `status == "merged"`
- **THEN** the action row renders the muted "終局狀態" text
- **AND** no transition buttons render

#### Scenario: rejected terminal label
- **WHEN** the loaded proposal has `status == "rejected"`
- **THEN** the action row renders the muted "終局狀態" text

---

### Requirement: `<TransitionDialog>` collects required args and submits

The `<TransitionDialog>` component SHALL be a single shadcn `<Dialog>` whose form fields are conditional on a `target: ProposalStatus` prop:

- `target == "validating"` → no `<TransitionDialog>` is opened; an `<AlertDialog>` confirmation runs instead, with only an `actor` input (defaulted from `localStorage`).
- `target == "approved"` → fields: `actor` (required), `validation_report_path` (required, text input).
- `target == "merged"` → fields: `actor` (required), `merged_to_version` (required, text input).
- `target == "rejected"` → fields: `actor` (required), `reason` (required, `<Textarea>` ≥ 2 rows).

Submit MUST be disabled until all required fields for the chosen `target` are non-empty.

On submit, the component MUST call `transitionProposal(slug, body)` (the `lib/api.ts` wrapper) with body `{new_status: target, actor, reason?, validation_report_path?, merged_to_version?}`. On HTTP 200 success, the dialog closes, `localStorage['ohmystock.admin.actor']` is updated to the submitted `actor`, and `queryClient.invalidateQueries({queryKey: ['proposal', slug]})` runs to refetch the detail. The component MUST NOT update the detail data optimistically.

On non-200 response, the envelope `code` and `message` MUST render inline below the form (`<p className="text-sm text-destructive">`) and the dialog stays open. The submit button MUST become re-enabled so the user can correct and retry.

#### Scenario: approve dialog requires both fields
- **WHEN** the user opens the Approve dialog with empty `actor` and empty `validation_report_path`
- **THEN** the submit button is disabled
- **WHEN** the user fills both
- **THEN** the submit button is enabled

#### Scenario: successful submit closes dialog and refetches
- **WHEN** the user submits a valid Approve transition
- **AND** the endpoint returns HTTP 200
- **THEN** the dialog closes
- **AND** `localStorage['ohmystock.admin.actor']` is updated to the submitted actor value
- **AND** the detail query is invalidated and refetches
- **AND** the new payload renders with `status == "approved"` and the new changelog entry

#### Scenario: server error shows inline message
- **WHEN** the user submits an Approve transition and the endpoint returns HTTP 409 `illegal_transition`
- **THEN** the dialog STAYS open
- **AND** the inline error shows the envelope `code` and `message`
- **AND** the submit button is re-enabled

#### Scenario: rejected dialog requires reason
- **WHEN** the user opens the Reject dialog with `actor` filled but `reason` empty
- **THEN** the submit button is disabled

---

### Requirement: API client wrappers and types

The shared client `web-admin/src/lib/api.ts` SHALL export:

- `ProposalStatus` type: `'pending' | 'validating' | 'approved' | 'merged' | 'rejected'`
- `Proposal` type: `{ slug: string; proposal_id: string; status: ProposalStatus; topic: string; target_section: string; created_by: string; created_at: string; review_id: string | null; priority: 'high' | 'medium' | 'low' }`
- `ProposalDetail` type: `Proposal & { body: { description: string; motivation: string; diff_draft: string; expected_impact: string; risk_assessment: string; validation_plan: string; expected_improvement: string }; changelog: ProposalChangelogEntry[]; extra_frontmatter: Partial<Record<'validation_report_path' | 'merged_to_version' | 'merged_at' | 'rejected_reason', string>> }`
- `ProposalChangelogEntry` discriminated union: `{ kind: 'transition'; timestamp: string; from_status: ProposalStatus; to_status: ProposalStatus; actor: string; reason: string | null } | { kind: 'created'; timestamp: string; actor: string } | { kind: 'raw'; text: string }`
- `ProposalTransitionBody` type: `{ new_status: ProposalStatus; actor: string; reason?: string; validation_report_path?: string; merged_to_version?: string }`
- `ProposalTransitionResult` type: `{ slug: string; new_status: ProposalStatus; new_path: string }`
- `listProposals(params?: { status?: ProposalStatus; limit?: number; offset?: number }): Promise<{ items: Proposal[]; total: number; limit: number; offset: number; has_more: boolean }>`
- `getProposal(slug: string): Promise<ProposalDetail>` calling `apiFetch<ProposalDetail>('/api/admin/proposals/' + encodeURIComponent(slug))`
- `transitionProposal(slug: string, body: ProposalTransitionBody): Promise<ProposalTransitionResult>` calling `apiFetch` with `method: 'POST'` and JSON body

The wrappers MUST NOT add their own retry, caching, or 401 handling; that is handled by `apiFetch`.

#### Scenario: listProposals composes query string
- **WHEN** `listProposals({ status: 'approved', limit: 25, offset: 50 })` is invoked
- **THEN** the underlying `fetch` URL is `/api/admin/proposals?status=approved&limit=25&offset=50`

#### Scenario: getProposal encodes path component
- **WHEN** `getProposal("2026-04-30-x y")` is invoked
- **THEN** the underlying `fetch` URL is `/api/admin/proposals/2026-04-30-x%20y`

#### Scenario: transitionProposal sends POST with JSON body
- **WHEN** `transitionProposal("2026-04-30-x", {new_status: "validating", actor: "mark"})` is invoked
- **THEN** the underlying `fetch` is `POST /api/admin/proposals/2026-04-30-x/transition` with header `Content-Type: application/json` and body `{"new_status":"validating","actor":"mark"}`

---

### Requirement: Routing and stub removal

`web-admin/src/router.tsx` SHALL import `ProposalsPage` from `@/pages/ProposalsPage` and `ProposalDetailPage` from `@/pages/ProposalDetailPage` (NOT from `@/pages/stubs`). The `ProposalsPage` and `ProposalDetailPage` symbols MUST be removed from `web-admin/src/pages/stubs.tsx`. The router-smoke test MUST still pass with the new components mounted under `/proposals` and `/proposals/:slug`.

#### Scenario: router uses real components
- **WHEN** the build compiles
- **THEN** `router.tsx` imports `ProposalsPage` and `ProposalDetailPage` from their dedicated page files
- **AND** `stubs.tsx` no longer exports those symbols

#### Scenario: smoke test renders without error
- **WHEN** the existing router smoke test mounts each route
- **THEN** `/proposals` and `/proposals/:slug` render without throwing

---

### Requirement: 紅漲綠跌 not applied; status-icon pairing only on errors

Proposals carry no price semantic. The pages MUST NOT use `--up` / `--down` colour tokens for status badges, priority badges, or content. The only place destructive colour is used is the error `Card`, which is paired with an `AlertCircle` icon per the universal "color-is-never-the-only-signal" rule from `docs/web-admin-page-designs.md` §0.3.

Status badges and priority badges SHALL use shadcn neutral variants (`secondary` / `outline`).

#### Scenario: status badges use neutral palette
- **WHEN** any status badge renders on the list or detail page
- **THEN** the badge uses `variant="secondary"`
- **AND** no `text-up` / `text-down` / `bg-destructive` class is applied to the badge

#### Scenario: error Card pairs colour with icon
- **WHEN** an error state renders
- **THEN** the destructive border colour is accompanied by `AlertCircle` from `lucide-react`
- **AND** the error has `role="alert"` for assistive tech
