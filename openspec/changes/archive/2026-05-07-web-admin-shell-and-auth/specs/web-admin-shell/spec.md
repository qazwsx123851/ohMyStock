## ADDED Requirements

### Requirement: Vite + React 19 + TypeScript scaffold under `web-admin/`
The system SHALL provide a Vite-based React 19 + TypeScript project under `web-admin/` with `pnpm` as the package manager and Tailwind CSS v4 configured for the dark-mode-default UI. The project SHALL build to a static `web-admin/dist/` bundle via `pnpm build` and serve a working dev server via `pnpm dev` on port `5173` with a proxy that forwards `/api/*` to `http://localhost:8000`.

#### Scenario: Fresh checkout boots
- **WHEN** a developer runs `cd web-admin && pnpm install && pnpm dev` on a fresh checkout with Node 20+
- **THEN** Vite SHALL start on `http://localhost:5173` and serve the app without console errors

#### Scenario: Production build emits a static bundle
- **WHEN** `pnpm build` runs to completion
- **THEN** `web-admin/dist/index.html` SHALL exist; `web-admin/dist/assets/*.js` SHALL include hashed bundles; gzipped initial JS SHALL be under 500 KB

#### Scenario: Dev proxy forwards API requests
- **GIVEN** the Vite dev server is running and a backend exists at `http://localhost:8000`
- **WHEN** the browser fetches `http://localhost:5173/api/admin/stats/today`
- **THEN** Vite SHALL proxy the request to `http://localhost:8000/api/admin/stats/today` and return its response unchanged

---

### Requirement: Bearer token lifecycle (login, persist, logout, auto-401)
The system SHALL provide a `/login` page that accepts a Bearer token, persists it to `localStorage` under key `ohmystock.admin.token`, and redirects to the previously requested URL (or `/` if none). The system SHALL clear the stored token and redirect to `/login` on (a) explicit logout button click, or (b) any `/api/admin/*` response with HTTP status 401.

#### Scenario: Successful login persists token and redirects
- **GIVEN** the user is on `/login` with no token in `localStorage`
- **WHEN** the user enters a valid token and clicks "Login"
- **THEN** `localStorage.getItem('ohmystock.admin.token')` SHALL return the entered token
- **AND** the browser SHALL navigate to `/`

#### Scenario: Login preserves return URL
- **GIVEN** an unauthenticated user navigates to `/paper/positions`
- **WHEN** the auth guard redirects them to `/login`, they enter a token, and submit
- **THEN** the browser SHALL navigate to `/paper/positions` (not `/`)

#### Scenario: 401 response triggers auto-logout
- **GIVEN** a user is logged in and viewing `/`
- **WHEN** any `/api/admin/*` fetch returns HTTP 401
- **THEN** `localStorage.getItem('ohmystock.admin.token')` SHALL return `null`
- **AND** the browser SHALL navigate to `/login`

#### Scenario: Logout button clears token
- **GIVEN** a user is logged in
- **WHEN** the user clicks the logout button in `<TopBar>`
- **THEN** `localStorage.getItem('ohmystock.admin.token')` SHALL return `null`
- **AND** the browser SHALL navigate to `/login`

---

### Requirement: Auth-protected layout wraps all 18 routes
The system SHALL define a single `<Layout>` component that wraps every non-`/login` route. The layout SHALL check the auth store on mount and on every navigation. If no token is present, it SHALL redirect to `/login` with the current path captured as `state.from`. The layout SHALL render `<Sidebar>`, `<TopBar>`, `<Outlet>`, and `<DisclaimerFooter>` in that visual order.

#### Scenario: Unauthenticated request to protected route redirects
- **GIVEN** `localStorage.getItem('ohmystock.admin.token')` is `null`
- **WHEN** the browser navigates directly to `/swarm`
- **THEN** the URL SHALL change to `/login`
- **AND** `useLocation().state.from` SHALL be `/swarm`

#### Scenario: Authenticated user sees full layout
- **GIVEN** a token is present in `localStorage`
- **WHEN** the user navigates to `/`
- **THEN** the rendered DOM SHALL contain a `<nav>` (Sidebar), an `<header>` (TopBar), a `<main>` (Outlet content), and a `<footer>` (DisclaimerFooter)

#### Scenario: All 18 routes are reachable
- **WHEN** the test runner navigates programmatically to each of: `/`, `/chat`, `/swarm`, `/backtest`, `/paper`, `/paper/orders`, `/paper/positions`, `/market`, `/skills`, `/memory`, `/sessions`, `/settings`, `/audit`
- **THEN** every navigation SHALL render without throwing
- **AND** stub pages SHALL render a `<ComingSoon>` placeholder

---

### Requirement: API client injects Bearer header and parses unified envelope
The system SHALL provide an API client (`apiFetch(path, init?)` or equivalent) that automatically prepends the `Authorization: Bearer <token>` header on every request to a path starting with `/api/admin/`. The client SHALL parse the unified `{ ok, data, error }` envelope returned by all admin endpoints (per `openspec/specs/server-action-endpoints/spec.md`), throw a typed `ApiError` on `ok === false`, and return `data` on `ok === true`.

#### Scenario: Successful response returns data field
- **GIVEN** the backend returns `200 OK` with body `{"ok": true, "data": {"foo": "bar"}}`
- **WHEN** the client calls `apiFetch('/api/admin/stats/today')`
- **THEN** the returned promise SHALL resolve to `{"foo": "bar"}`

#### Scenario: Envelope error throws ApiError
- **GIVEN** the backend returns `200 OK` with body `{"ok": false, "error": {"code": "validation_failed", "message": "bad input"}}`
- **WHEN** the client calls `apiFetch('/api/admin/screener.run')`
- **THEN** the returned promise SHALL reject with an `ApiError` whose `code === "validation_failed"` and `message === "bad input"`

#### Scenario: 401 response triggers auto-logout side effect
- **GIVEN** a token is present
- **WHEN** any `apiFetch(...)` receives an HTTP 401 response
- **THEN** the auth store SHALL be cleared
- **AND** the returned promise SHALL reject with an `ApiError` whose `code === "auth_invalid"` or `code === "auth_missing"`

---

### Requirement: SSE subscription with auth header and exponential backoff
The system SHALL provide a `useAdminEvents()` hook that opens a streaming connection to `/api/admin/events` with the `Authorization: Bearer <token>` header. On connection close (non-401), the hook SHALL reconnect with exponential backoff: 1s, 2s, 4s, 8s, capped at 30s. On 401, the hook SHALL abort reconnection and trigger the auto-logout side effect. The hook SHALL push received events into a Zustand "live feed" slice capped at 100 entries (FIFO eviction).

#### Scenario: Hook receives events
- **GIVEN** a backend SSE stream emits an event of type `screener.completed`
- **WHEN** `useAdminEvents()` is mounted
- **THEN** the live-feed slice SHALL contain a new entry with `event_type === "screener.completed"`

#### Scenario: Reconnection after disconnect
- **GIVEN** the connection drops (e.g., backend restart) without a 401
- **WHEN** 1 second elapses
- **THEN** the hook SHALL attempt to reconnect
- **AND** subsequent failures SHALL retry at 2s, 4s, 8s, then 30s thereafter

#### Scenario: 401 stops reconnect and clears auth
- **GIVEN** the SSE connection returns HTTP 401
- **WHEN** the hook observes the 401
- **THEN** no reconnect attempt SHALL be scheduled
- **AND** the auth store SHALL be cleared
- **AND** the browser SHALL navigate to `/login`

#### Scenario: Live feed is capped
- **GIVEN** 150 events stream in
- **WHEN** the live-feed slice is read
- **THEN** its length SHALL equal 100 (oldest 50 evicted)

---

### Requirement: Dashboard page renders KpiRow and LiveFeed
The system SHALL render at `/` a `<DashboardPage>` containing (a) a `<KpiRow>` of 4 cards driven by `GET /api/admin/stats/today`, and (b) a `<LiveFeed>` panel showing the most recent 20 entries from the live-feed slice. The KpiRow SHALL display: today realized P&L (TWD with `--up` / `--down` color), open positions count, pending confirms count, today LLM cost (USD). The LiveFeed SHALL display each event as a row with type icon, symbol (or "—"), and a relative timestamp ("3 秒前").

#### Scenario: Stats render with semantic colors
- **GIVEN** `GET /api/admin/stats/today` returns `{"realized_pnl_twd": 12345, "open_positions": 3, "pending_confirms": 1, "llm_cost_usd": 0.42}`
- **WHEN** the Dashboard page renders
- **THEN** a card containing "12,345" SHALL have computed text color matching the `--up` token (red in zh-TW convention)

#### Scenario: Loading shows skeleton
- **GIVEN** `GET /api/admin/stats/today` is in flight
- **WHEN** the Dashboard page first renders
- **THEN** four `<Skeleton>` placeholders SHALL appear in the KpiRow positions

#### Scenario: Live feed updates from SSE
- **GIVEN** the Dashboard is mounted and the SSE stream is connected
- **WHEN** the backend emits an event with `event_type="confirm_gate.confirmed"` and `symbol="2330"`
- **THEN** the LiveFeed SHALL prepend a new row showing "2330" within 1 second

---

### Requirement: 17 stub pages render `<ComingSoon>` placeholder
The system SHALL provide a `<ComingSoon name="..." />` component and use it as the body of all 17 non-Dashboard routes. The component SHALL display the page name, a one-line description, and the text "Coming soon — tracked in a future change". The component SHALL not make any network requests.

#### Scenario: Stub renders without network calls
- **GIVEN** the user navigates to `/skills`
- **WHEN** the route renders
- **THEN** the rendered DOM SHALL contain the text "Coming soon"
- **AND** no `fetch()` call SHALL be made by the page

---

### Requirement: Design system tokens for Taiwan-stock colors and CJK typography
The system SHALL define four CSS custom properties as Tailwind v4 design tokens — `--up`, `--down`, `--destructive`, `--warning` — with the values from design.md D5. The system SHALL load `Inter`, `Noto Sans TC`, and `Fira Code` from Google Fonts and apply them as the default UI sans, CJK fallback, and tabular-numeric font respectively. Numeric cells (price, quantity, P&L) SHALL set `font-variant-numeric: tabular-nums` so columns align.

#### Scenario: Tokens are defined and accessible
- **WHEN** the app boots
- **THEN** `getComputedStyle(document.documentElement).getPropertyValue('--up')` SHALL return a non-empty hex color string
- **AND** the same property SHALL be defined for `--down`, `--destructive`, `--warning`

#### Scenario: zh-TW glyphs render via Noto Sans TC
- **GIVEN** the Dashboard page contains the string "今日損益"
- **WHEN** the page renders
- **THEN** the computed `font-family` for that text SHALL include `Noto Sans TC` before any system fallback

#### Scenario: Numeric column alignment
- **GIVEN** a `<KpiCard>` displays a TWD value
- **WHEN** the value's container is inspected
- **THEN** its computed `font-variant-numeric` SHALL include `tabular-nums`
- **AND** its computed `font-family` SHALL include `Fira Code`

---

### Requirement: Color is never the only signal for direction
The system SHALL pair every up/down direction indicator with a glyph (`↑` / `↓` or Lucide `arrow-up` / `arrow-down`) so that color-blind users (deuteranopia, protanopia) can distinguish gain from loss without relying on red vs green.

#### Scenario: Up cell has both color and glyph
- **GIVEN** a price cell shows a positive change
- **WHEN** the cell renders
- **THEN** its DOM SHALL contain a `↑` glyph (or an `arrow-up` SVG)
- **AND** its computed text color SHALL match the `--up` token

#### Scenario: Down cell has both color and glyph
- **GIVEN** a price cell shows a negative change
- **WHEN** the cell renders
- **THEN** its DOM SHALL contain a `↓` glyph (or an `arrow-down` SVG)
- **AND** its computed text color SHALL match the `--down` token
