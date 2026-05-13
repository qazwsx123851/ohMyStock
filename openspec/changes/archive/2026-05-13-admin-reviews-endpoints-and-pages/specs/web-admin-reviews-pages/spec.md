## ADDED Requirements

### Requirement: `/reviews` route renders read-only list

The web-admin SHALL render `/reviews` via a new `ReviewsPage` component. The page MUST fetch from `GET /api/admin/reviews?kind=<selected>&limit=50` via the shared `apiFetch<T>` client wrapped in `useQuery` with key `['reviews', selectedKind]`. The router import MUST be from `react-router` (matching the existing `ProposalsPage`), NOT from `react-router-dom`.

The page MUST present, in vertical order: a page header with `<h1>Reviews</h1>` + a one-line description ending in 「共 N/M 筆。」 once data is loaded (mirroring `ProposalsPage`), a kind filter row using a `<KindTabs>` custom button-group (NOT the shadcn `<Tabs>` primitive — mirror the existing `<StatusTabs>` button-group at `web-admin/src/pages/ProposalsPage.tsx`: `role="tablist"`, `inline-flex rounded-md border border-input bg-muted/40 p-1` shell, each tab a `<button role="tab" aria-selected>` toggling `bg-background shadow-sm`), and a `<DataTable>` of review rows.

The table MUST have exactly 7 columns in this order:
1. `completed_at` (`font-mono text-xs`, displayed as `YYYY-MM-DD` portion via `toLocaleDateString('zh-TW')` or string slice; full ISO retained in `title` attribute)
2. `review_id` (`font-medium`, monospace-ish — does NOT require `font-mono` but MUST NOT truncate aggressively below 36ch)
3. `kind` (`Badge variant="secondary"` with the literal kind text)
4. `period` (rendered as `<period.from>` → `<period.to>` shortened to `MM-DD` portions, `text-muted-foreground`)
5. `trade_count` (right-aligned)
6. `win_rate` (right-aligned percentage; `text-up` + leading `<TrendingUp className="size-3.5" aria-hidden>` when `>= 0.5`, otherwise `text-down` + leading `<TrendingDown className="size-3.5" aria-hidden>`)
7. `pf` (right-aligned 2-decimal float; `text-up` + leading `<TrendingUp className="size-3.5" aria-hidden>` when `>= 1`, otherwise `text-down` + leading `<TrendingDown className="size-3.5" aria-hidden>`)

The metrics dual-encoding (icon + colour) applies to columns 6 and 7 BOTH, so `pf < 1` (unprofitable) renders red/down identically to `win_rate < 0.5`. The TrendingUp/Down icon MUST be `aria-hidden` because the adjacent number is its accessible label.

Clicking anywhere on a row MUST navigate to `/reviews/<review_id>` via `react-router` `useNavigate`. Each row MUST be keyboard-focusable; pressing Enter while a row has focus MUST navigate the same way. Rows MUST render with `cursor-pointer` and `focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none` (delegated to `<DataTable>` if it owns row styling, otherwise applied directly).

The page MUST NOT render: SSE listeners, edit buttons, re-run buttons, body previews, or transition buttons.

#### Scenario: list loads and renders rows
- **WHEN** the user opens `/reviews` with a valid Bearer token
- **AND** the endpoint returns 3 reviews (one monthly, one quarterly, one manual)
- **THEN** 3 rows render in the table
- **AND** each row shows the 7 columns in order
- **AND** each kind `Badge` uses `variant="secondary"`

#### Scenario: header description shows row count
- **WHEN** the endpoint returns `total: 12` and the page shows 12 items
- **THEN** the header description ends with `共 12/12 筆。`

#### Scenario: win_rate uses dual encoding (colour + icon)
- **WHEN** a row has `win_rate == 0.62` and another has `win_rate == 0.41`
- **THEN** the first row's `win_rate` cell has class containing `text-up` AND renders a `TrendingUp` icon
- **AND** the second row's `win_rate` cell has class containing `text-down` AND renders a `TrendingDown` icon

#### Scenario: pf uses dual encoding (colour + icon)
- **WHEN** a row has `pf == 1.84` and another has `pf == 0.74`
- **THEN** the first row's `pf` cell has class containing `text-up` AND renders a `TrendingUp` icon
- **AND** the second row's `pf` cell has class containing `text-down` AND renders a `TrendingDown` icon

#### Scenario: row click navigates to detail
- **WHEN** the user clicks a row whose `review_id` is `manual-2026-04-01-to-2026-04-30`
- **THEN** the router navigates to `/reviews/manual-2026-04-01-to-2026-04-30`

#### Scenario: row keyboard navigation
- **WHEN** the user Tab-focuses a row and presses Enter
- **THEN** the router navigates to `/reviews/<that-row-review_id>`

---

### Requirement: `/reviews` kind tabs drive query

The 5 kind tabs SHALL be exactly: `全部`, `monthly`, `quarterly`, `forced`, `manual`. Selecting `全部` MUST omit the `?kind=` query parameter; selecting any other tab MUST send that literal value as `?kind=`.

Tab change MUST trigger a new fetch via react-query's keyed cache (`['reviews', kind]`) — switching back to a previously-viewed tab MUST serve from cache without a network roundtrip.

The active tab MUST persist in URL search params so that navigating away and back via browser history restores the same view.

#### Scenario: kind tab updates query
- **WHEN** the user clicks the `monthly` tab
- **THEN** the network request is `GET /api/admin/reviews?kind=monthly&limit=50`
- **AND** only rows with `kind == "monthly"` render

#### Scenario: 全部 tab omits kind param
- **WHEN** the user clicks the `全部` tab
- **THEN** the network request is `GET /api/admin/reviews?limit=50` (no `kind=` parameter)

#### Scenario: tab persists in URL
- **WHEN** the user selects `manual` and then opens a new tab via browser back
- **THEN** the URL retains `?kind=manual`
- **AND** the same tab is active on remount

---

### Requirement: `/reviews` loading-empty-error states

The page SHALL render distinct loading, empty, and error states:

- **Loading**: 8 `Skeleton` table rows (NOT spinners).
- **Empty (filter narrowed to 0)**: a centred message "目前 <kind> 沒有 review" plus a `Button variant="outline"` labelled "回到全部" that resets the tab to `全部`.
- **Empty (index returned `[]` overall)**: a centred message "尚無 review；執行 `uv run ohmystock review --from ... --to ...` 產出第一份" with no reset button.
- **Error**: a top-of-page `Card` with `border-destructive/50 bg-destructive/5`, an `AlertCircle` icon (`size-4 text-destructive`), the error message text, and a `Button` "重試" that calls `query.refetch()`. The Card MUST have `role="alert"`.

#### Scenario: loading shows 8 skeleton rows
- **WHEN** the page mounts and the query is in flight
- **THEN** 8 `Skeleton` row placeholders render
- **AND** no row or error UI is visible

#### Scenario: empty after kind filter
- **WHEN** the `forced` tab is active and `total == 0`
- **THEN** the empty message "目前 forced 沒有 review" renders
- **AND** the "回到全部" button is visible
- **WHEN** the user clicks "回到全部"
- **THEN** the `全部` tab activates and the query refetches

#### Scenario: error shows retry
- **WHEN** the endpoint returns 500
- **THEN** a destructive `Card` renders at the top of the page with `role="alert"`
- **AND** clicking "重試" calls the underlying query's refetch

---

### Requirement: `/reviews/:reviewId` route renders read-only detail

The web-admin SHALL render `/reviews/:reviewId` via a new `ReviewDetailPage` component. The page MUST fetch from `GET /api/admin/reviews/{review_id}` via `apiFetch` wrapped in `useQuery` with key `['review', reviewId]`.

The page MUST display, in this order:

1. **Header row** — a `<Link to="/reviews">← Reviews</Link>` back-link, the `review_id` as `<h1>`, a `kind` `Badge variant="secondary"`, and a `period` line (`period.from` → `period.to`) in `text-muted-foreground`.
2. **3 KPI Cards** (only when `summary` is non-null):
   - `trade_count` — label「期間交易筆數」, value `summary.trade_count`
   - `win_rate` — label「勝率」, value as percentage with `text-up`/`text-down` + `TrendingUp`/`TrendingDown` icon following the `>= 0.5` rule from the list spec.
   - `pf` — label「Profit Factor」, value `summary.pf` with `text-up` when `>= 1` + `TrendingUp` icon, `text-down` when `< 1` + `TrendingDown` icon.
3. **「本期復盤檔案」Card** — a 6-row checklist of `files.data_json` / `attribution_json` / `metrics_json` / `critique_md` / `report_md` / `proposals_created_md`, rendered as a dense definition list with `py-1.5` row spacing (visually distinct from the body-style Report Card below). Each row MUST render with a leading `CheckCircle2` icon (`size-4 text-foreground` with `aria-label="已產出"`) when `exists: true`, or a `Circle` icon (`size-4 text-muted-foreground/50` with `aria-label="缺漏"`) when `exists: false`. The row label MUST be the bare filename (e.g. `data.json`, `text-sm`), and existing rows MUST render the `path` value in `text-xs font-mono text-muted-foreground` after the label; missing rows MUST render `—` in `text-muted-foreground/50` in the path slot.
4. **「Report」Card** — a `<pre className="whitespace-pre-wrap font-mono text-sm">{report}</pre>` rendering the full `report.md` text. The Card SHALL be omitted entirely when `report is null`.
5. **「本次產出的提案」Card** — a 4-column table (`slug` / `status` / `priority` / `target`) listing `proposals_created`. Each row MUST be a `Link to={"/proposals/" + row.slug}`. When `proposals_created` is empty, the Card body MUST render `<p className="text-muted-foreground">本期無提案</p>`.

#### Scenario: detail renders complete review
- **WHEN** the user opens `/reviews/manual-2026-04-01-to-2026-04-30` with a complete review on disk
- **THEN** the header, 3 KPI Cards, file checklist (all 6 rows with `CheckCircle2`), Report Card, and Proposals Card all render
- **AND** the Report Card contains the verbatim text of `report.md`

#### Scenario: file checklist marks missing files
- **WHEN** the API returns `files.critique_md.exists == false` and `files.report_md.exists == false`
- **THEN** the `critique.md` row renders with a `Circle` icon
- **AND** the `report.md` row renders with a `Circle` icon
- **AND** the Report Card is NOT rendered (because `report is null`)

#### Scenario: proposals Card links to /proposals/<slug>
- **WHEN** `proposals_created` contains a row with `slug == "2026-04-30-vcp-volume-threshold"`
- **THEN** that row's `<a>` element has `href == "/proposals/2026-04-30-vcp-volume-threshold"`

#### Scenario: empty proposals Card shows label
- **WHEN** `proposals_created` is `[]`
- **THEN** the Card body renders the literal text "本期無提案" in `text-muted-foreground`

---

### Requirement: `/reviews/:reviewId` partial review banner

When `partial: true`, the detail page MUST render a warning banner at the top of the page (after the header row, before the KPI Cards) with:
- An outer `Card` with `border-warning` class
- A leading `AlertTriangle` icon with `text-warning size-4` class
- The literal text "部分節點未完成 — 下方僅顯示已落檔的中間產物"

The banner MUST also be present whenever `summary is null` (one of the two `partial` conditions per the endpoint spec). In that case, the 3 KPI Cards MUST NOT render at all.

#### Scenario: partial=true shows banner
- **WHEN** the API returns `partial: true` (with a populated summary)
- **THEN** the warning Card renders with `AlertTriangle` icon and the literal label
- **AND** the 3 KPI Cards still render below

#### Scenario: summary is null hides KPI cards
- **WHEN** the API returns `summary: null` (pipeline crashed before `_index` upsert)
- **THEN** the warning Card renders
- **AND** the 3 KPI Cards do NOT render
- **AND** the file checklist still renders

---

### Requirement: `/reviews/:reviewId` 404 and error states

The detail page SHALL render an empty state when the endpoint returns HTTP 404 with `error.code == "not_found"`: a centred `Card` with `role="status"` (NOT `role="alert"` — this is an informational navigation state, not a runtime failure) containing a `PackageSearch` icon, the message "Review not found: <review_id>", and a `Link to="/reviews"` labelled "回到 Reviews 列表".

For any other error (5xx, network failure, malformed payload), the page MUST render a destructive `Card` with `border-destructive/50 bg-destructive/5`, `AlertCircle` icon, the error code/message, and a `Button` "重試" that calls `query.refetch()`. The Card MUST have `role="alert"`.

#### Scenario: 404 shows empty state with back-link
- **WHEN** the API returns HTTP 404
- **THEN** the page renders "Review not found: <review_id>"
- **AND** a `Link` to `/reviews` is visible
- **AND** no destructive Card and no KPI Cards render

#### Scenario: 500 shows destructive Card with retry
- **WHEN** the API returns HTTP 500
- **THEN** the destructive Card renders at the top of the page with `role="alert"`
- **AND** clicking "重試" triggers `query.refetch()`

---

### Requirement: Side-nav `Reviews` entry

The web-admin sidebar SHALL include a `Reviews` link positioned directly above the existing `Proposals` entry. Clicking it MUST navigate to `/reviews`. The link MUST be active (highlighted) for both `/reviews` and `/reviews/:reviewId`.

The link icon SHALL be `ClipboardList` from `lucide-react`.

#### Scenario: nav entry navigates to /reviews
- **WHEN** the user clicks the `Reviews` sidebar entry
- **THEN** the router navigates to `/reviews`

#### Scenario: nav entry is active on detail page
- **WHEN** the current pathname is `/reviews/manual-2026-04-01-to-2026-04-30`
- **THEN** the `Reviews` sidebar entry has the active-state styling
- **AND** the `Proposals` sidebar entry does NOT

---

### Requirement: Bearer auth on all reviews routes

Both `/reviews` and `/reviews/:reviewId` MUST use the same Bearer-auth lifecycle as every other admin page (read `localStorage['ohmystock.admin.token']`, attach `Authorization: Bearer <token>` via `apiFetch`, auto-logout on 401 by clearing the token and redirecting to the login screen).

#### Scenario: unauthenticated user redirects to login
- **WHEN** the user opens `/reviews` without a stored token
- **THEN** the app redirects to the login screen before any fetch is issued

#### Scenario: 401 on either route clears token
- **WHEN** the user is on `/reviews/x` and a server token rotation causes the next refetch to return 401 `auth_invalid`
- **THEN** the stored token is cleared from `localStorage`
- **AND** the app redirects to the login screen
