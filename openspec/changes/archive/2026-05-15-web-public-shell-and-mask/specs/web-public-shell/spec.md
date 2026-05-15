## ADDED Requirements

### Requirement: web-public/ SHALL be a standalone Vite + React 19 + TypeScript project

The repository SHALL contain a top-level `web-public/` directory parallel to
`web-admin/`. Its `package.json` SHALL declare `react@^19`, `react-dom@^19`,
`typescript@^5`, `vite@^8`, `tailwindcss@^4` as direct dependencies. The project SHALL
NOT be a pnpm workspace member; it SHALL build with `pnpm install && pnpm build` run
from inside `web-public/`. Its Vite config SHALL set dev `port: 5173` and SHALL
proxy `/api` to `http://localhost:8000`.

#### Scenario: Standalone install and build succeed

- **WHEN** `pnpm install && pnpm build` is run from `web-public/`
- **THEN** both commands SHALL exit with status `0`
- **AND** a `web-public/dist/index.html` file SHALL exist

#### Scenario: Vite dev proxy targets backend

- **WHEN** the `web-public/vite.config.ts` is read
- **THEN** the parsed config SHALL define `server.proxy['/api']` with `target:
  'http://localhost:8000'`

### Requirement: DisclaimerBanner SHALL be permanently mounted and non-dismissable

The app root component SHALL render a `<DisclaimerBanner />` component above all other
page content. The banner SHALL render the zh-TW disclaimer text specified in
`docs/auth-and-mask.md` §4.3 verbatim (the "⚠️ 本網站為 AI 系統運作展示，非投資建議。"
block). The banner SHALL NOT have a close button, dismiss control, or any way to hide
it via UI interaction. The banner SHALL have `position: sticky; top: 0; z-index >= 50`
in CSS so it remains visible while the user scrolls.

#### Scenario: Disclaimer text is present on app load

- **WHEN** the app renders at `http://localhost:5173/`
- **THEN** the DOM SHALL contain the substring `本網站為 AI 系統運作展示，非投資建議`
- **AND** the DOM SHALL contain the substring `所有股票代號（STK-A、STK-B 等）為虛構代換`

#### Scenario: No dismiss control exists

- **WHEN** the rendered DOM is searched for elements with text like "關閉", "Close",
  "Dismiss", or `aria-label` containing those words within the banner's subtree
- **THEN** zero such elements SHALL be found

### Requirement: MaskedEventsFeed SHALL display the last 50 events oldest-evicted

The app SHALL render a `<MaskedEventsFeed />` component that opens an `EventSource`
to `/api/public/events` on mount. For each received message, the component SHALL parse
the JSON payload and prepend it to an in-memory list. When the list exceeds 50 items,
the oldest item SHALL be evicted. Each item SHALL render as a `<li>` with the
following visible content (text or attributes):

- The `timestamp` (formatted in TPE local time, HH:MM:SS).
- The `event_type` as a label.
- The `agent` as a label.
- The masked `payload` as `JSON.stringify(payload)` inside a `<code>` element.

The feed SHALL NOT render any field whose key appears in `eventbus-public-mask`'s
`DENYLIST_FIELDS`; if the server's `payload` somehow contains one (a regression), the
component SHALL filter it out client-side before rendering.

#### Scenario: New event prepends to the feed

- **WHEN** the SSE stream pushes a `decision_made` event
- **THEN** within one event-loop tick the rendered feed SHALL contain a new `<li>`
  with the event's masked payload at the top of the list

#### Scenario: 51st event evicts the oldest

- **WHEN** 51 events are received in sequence
- **THEN** the rendered feed SHALL contain exactly 50 `<li>` elements
- **AND** the first event (oldest) SHALL NOT be present

#### Scenario: Duplicate event_id is de-duplicated on reconnect

- **WHEN** the same `event_id` is delivered twice (e.g. EventSource auto-reconnect with
  `Last-Event-ID`)
- **THEN** the feed SHALL contain only one `<li>` for that `event_id`

#### Scenario: Client-side DENYLIST filter blocks rogue field

- **WHEN** a payload `{"symbol": "2330", "confidence": 0.7}` is somehow delivered (a
  server regression)
- **THEN** the rendered JSON in the `<li>` SHALL NOT contain the substring
  `"symbol":"2330"`

### Requirement: robots.txt SHALL allow indexing but block /api

The file `web-public/public/robots.txt` SHALL exist with at minimum the contents:

```
User-agent: *
Allow: /
Disallow: /api/
```

#### Scenario: robots.txt is served at /robots.txt

- **WHEN** an HTTP `GET /robots.txt` is issued against the dev server
- **THEN** the response body SHALL contain `Disallow: /api/`

### Requirement: 404 page SHALL render disclaimer and home link

Unknown routes SHALL render a 404 view that still displays the DisclaimerBanner and
a single `<a href="/">` back-link. The 404 view SHALL NOT contain any stock-specific
content.

#### Scenario: Unknown path shows 404 with banner

- **WHEN** the user navigates to `/this-does-not-exist`
- **THEN** the DOM SHALL contain the disclaimer text
- **AND** the DOM SHALL contain an anchor whose `href` is `/`

### Requirement: No analytics, no cookies, no localStorage PII

The app SHALL NOT include any third-party analytics script (Google Analytics, Plausible,
PostHog, etc.). The app SHALL NOT set any cookie. The app SHALL NOT write to
`localStorage` or `sessionStorage` any value derived from server data. The
`EventSource` connection SHALL be the only network call to a non-static origin.

#### Scenario: Static check finds no analytics imports

- **WHEN** the test suite greps `web-public/src/` for the substrings `gtag`, `ga(`,
  `plausible`, `posthog`, `mixpanel`, `analytics`
- **THEN** zero matches SHALL be found

#### Scenario: No storage writes on app load

- **WHEN** the app loads in a fresh browser context
- **THEN** `document.cookie` SHALL be empty
- **AND** `localStorage.length` SHALL be `0`
- **AND** `sessionStorage.length` SHALL be `0`
