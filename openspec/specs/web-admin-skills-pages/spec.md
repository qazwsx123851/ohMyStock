# web-admin-skills-pages Specification

## Purpose
TBD - created by archiving change web-admin-skills-pages. Update Purpose after archive.
## Requirements
### Requirement: `/skills` route renders read-only list

The web-admin SHALL render `/skills` via a new `SkillsPage` component (replacing the existing `ComingSoon` stub at `web-admin/src/pages/stubs.tsx`). The page MUST fetch from `GET /api/admin/skills` via the shared `apiFetch<T>` client wrapped in a `useQuery` hook with key `['skills']`.

The page MUST present, in vertical order: a page header with `<h1>Skills</h1>` + a one-line description, a filter bar (search input + category select), and a 1-/2-/3-/4-column responsive grid of `Card` elements.

Each card MUST display, in this order: skill `name` (semibold), one-line `description`, a `category` badge using shadcn `Badge variant="secondary"`. Cards MUST NOT show enable toggles, "last run" timestamps, or save buttons in v0.

Clicking anywhere on a card MUST navigate to `/skills/<name>` via `react-router-dom` `useNavigate`. Each card MUST be keyboard-focusable; pressing Enter while a card has focus MUST navigate the same way.

#### Scenario: list loads and renders 10 seed cards
- **WHEN** the user opens `/skills` with a valid Bearer token
- **AND** the endpoint returns the 10 production seed skills
- **THEN** 10 cards render in alphabetical order
- **AND** each card shows `name`, `description`, and a category `Badge`

#### Scenario: card click navigates to detail
- **WHEN** the user clicks a card whose `name` is `market-data`
- **THEN** the router navigates to `/skills/market-data`

#### Scenario: card keyboard navigation
- **WHEN** the user Tab-focuses a card and presses Enter
- **THEN** the router navigates to `/skills/<that-card-name>`

### Requirement: `/skills` filter bar is client-side only

The filter bar SHALL apply filters synchronously to the in-memory list returned by the single initial fetch. There MUST NOT be any network request triggered by typing in the search input or changing the category select; the page MUST NOT debounce.

The search input SHALL match (case-insensitive substring) against `name` OR `description`. The category select SHALL include an "全部" option (default) plus exactly the seven `SkillCategory` values (`data`, `indicator`, `signal`, `decider`, `gate`, `tool`, `report`); when a non-"全部" value is selected, only cards with the matching `category` are shown.

#### Scenario: search filters by name substring
- **WHEN** the user types "market" into the search input
- **THEN** only cards whose `name` or `description` contain "market" (case-insensitive) remain visible
- **AND** no network request is made

#### Scenario: category filter narrows results
- **WHEN** the user selects category `data` in the select
- **THEN** only cards with `category == "data"` remain visible

#### Scenario: combined filter
- **WHEN** the user types "rs" and selects category `indicator`
- **THEN** only cards whose name/description contain "rs" AND category equals `indicator` are shown

### Requirement: `/skills` loading-empty-error states

The page SHALL render distinct loading, empty (no skills match filter), and error states:

- **Loading**: 12 `Skeleton` cards in the grid (NOT spinners), per `docs/web-admin-page-designs.md` §共用 patterns.
- **Empty (post-filter)**: a centred message "無符合條件的 skill" plus a `Button variant="outline"` labelled "清除 filter" that resets both filter inputs.
- **Empty (registry returned `[]`)**: a centred message "尚未註冊任何 skill" with no clear-filter button.
- **Error**: a top-of-page `Card` with `border-destructive/50 bg-destructive/5`, an `AlertCircle` icon (`size-4 text-destructive`), the error message text, and a `Button` "重試" that calls `query.refetch()`.

#### Scenario: loading shows 12 skeletons
- **WHEN** the page mounts and the query is in flight
- **THEN** 12 `Skeleton` placeholders render in the grid
- **AND** no card or error UI is visible

#### Scenario: empty after filter
- **WHEN** the search input is "zzzz" and no card matches
- **THEN** the empty message "無符合條件的 skill" renders
- **AND** the "清除 filter" button is visible
- **WHEN** the user clicks "清除 filter"
- **THEN** both filter inputs reset to their defaults and the cards re-appear

#### Scenario: error shows retry
- **WHEN** the endpoint returns 500
- **THEN** a destructive `Card` renders at the top of the page with `role="alert"`
- **AND** the error message is shown
- **AND** clicking "重試" calls the underlying query's refetch

### Requirement: `/skills/:name` route renders read-only detail

The web-admin SHALL render `/skills/:name` via a new `SkillDetailPage` component (replacing the existing stub). The page MUST fetch from `GET /api/admin/skills/{name}` via `apiFetch` wrapped in `useQuery` with key `['skill', name]`.

The page MUST display:
- A header row with a `<Link to="/skills">← Skills</Link>` back-link, the skill `name` as `<h1>`, and a `category` `Badge`.
- A "Cited specs" row rendering each `cited_specs` entry as a `<code>`-styled chip; if the array is empty, render the literal text "（無 cited_specs）".
- A `Card` containing the full `body` rendered as `<pre className="whitespace-pre-wrap font-mono text-sm">{body}</pre>`. There MUST NOT be a Markdown parser, syntax highlighter, or preview toggle.

The page MUST NOT render: a `Save` button, an `Edit` button, a YAML editor `<Textarea>`, dirty-state UI, autosave hints, or a `<form>`.

#### Scenario: detail loads and renders
- **WHEN** the user opens `/skills/market-data` with a valid Bearer token
- **AND** the endpoint returns the full `SkillDetail` payload
- **THEN** the header shows `← Skills`, "market-data", and a category badge
- **AND** the `cited_specs` chips render in order
- **AND** the body is shown in a `<pre>` block with the full text
- **AND** no Save / Edit / Textarea / preview-toggle elements exist in the DOM

#### Scenario: empty cited_specs renders fallback
- **WHEN** the loaded skill has `cited_specs == []`
- **THEN** the cited-specs row renders the literal "（無 cited_specs）"

### Requirement: `/skills/:name` 404 and error states

When the endpoint returns 404 (`code: "not_found"`), the page SHALL render an empty state with the message "找不到 skill: {name}" and a `Button variant="outline"` labelled "返回 Skills" linking to `/skills`. The HTTP status MUST be respected — `query.error` is set to an `ApiError` with code `not_found` and the page must NOT show the body / cited-specs / category badge sections.

When the endpoint returns 400 (`invalid_input`) or 500, the page SHALL render the same destructive `Card` + `AlertCircle` + retry pattern as `/skills`. The retry button calls `refetch()`.

#### Scenario: 404 shows back-link
- **WHEN** the client navigates to `/skills/nonexistent`
- **AND** the endpoint returns HTTP 404 with `code: "not_found"`
- **THEN** the page shows "找不到 skill: nonexistent" plus a "返回 Skills" button
- **AND** no body Card or category badge is rendered

#### Scenario: 500 error shows retry
- **WHEN** the endpoint returns HTTP 500
- **THEN** the page renders the destructive error Card with retry
- **AND** clicking retry calls `refetch()`

### Requirement: API client wrappers and types

The shared client `web-admin/src/lib/api.ts` SHALL export:
- `Skill` type: `{ name: string; description: string; category: SkillCategory; body_preview: string; body_truncated: boolean; cited_specs: string[] }`
- `SkillDetail` type: `{ name: string; description: string; category: SkillCategory; body: string; cited_specs: string[] }`
- `SkillCategory` type: `'data' | 'indicator' | 'signal' | 'decider' | 'gate' | 'tool' | 'report'`
- `listSkills(): Promise<{ items: Skill[] }>` calling `apiFetch<{ items: Skill[] }>('/api/admin/skills')`
- `getSkill(name: string): Promise<SkillDetail>` calling `apiFetch<SkillDetail>('/api/admin/skills/' + encodeURIComponent(name))`

The wrappers MUST NOT add their own retry, caching, or 401 handling; that is handled by `apiFetch`.

#### Scenario: listSkills returns items array
- **WHEN** `listSkills()` is awaited and the endpoint succeeds
- **THEN** the resolved value matches `{ items: Skill[] }` with no extra fields

#### Scenario: getSkill encodes path component
- **WHEN** `getSkill("foo bar")` is invoked
- **THEN** the underlying `fetch` URL is `/api/admin/skills/foo%20bar`
- **AND** the resolved value matches the `SkillDetail` shape

### Requirement: Routing and stub removal

`web-admin/src/router.tsx` SHALL import `SkillsPage` from `@/pages/SkillsPage` and `SkillDetailPage` from `@/pages/SkillDetailPage` (NOT from `@/pages/stubs`). The `SkillsPage` and `SkillDetailPage` symbols MUST be removed from `web-admin/src/pages/stubs.tsx`. The router-smoke test MUST still pass with the new components mounted under `/skills` and `/skills/:name`.

#### Scenario: router uses real components
- **WHEN** the build compiles
- **THEN** `router.tsx` imports `SkillsPage` and `SkillDetailPage` from their dedicated page files
- **AND** `stubs.tsx` no longer exports those symbols

#### Scenario: smoke test renders without error
- **WHEN** the existing router smoke test mounts each route
- **THEN** `/skills` and `/skills/:name` render without throwing

### Requirement: 紅漲綠跌 not applied; status-icon pairing only where needed

Skill cards and the detail page have no price semantics. Therefore the page MUST NOT use `--up` / `--down` / `--destructive` colours for category badges or content. The only place destructive colour is used is the error `Card`, which is paired with an `AlertCircle` icon per the universal "color-is-never-the-only-signal" rule from `docs/web-admin-page-designs.md` §0.3.

#### Scenario: category badges use neutral palette
- **WHEN** the list page renders any category badge
- **THEN** the badge uses shadcn's `secondary` (or equivalent neutral) variant
- **AND** no `text-up` / `text-down` / `bg-destructive` class is applied to the badge

#### Scenario: error Card pairs colour with icon
- **WHEN** the error state renders
- **THEN** the destructive border colour is accompanied by `AlertCircle` from `lucide-react`
- **AND** the error has `role="alert"` for assistive tech

