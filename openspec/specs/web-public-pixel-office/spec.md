# web-public-pixel-office Specification

## Purpose
TBD - created by archiving change web-public-pixel-office-mvp. Update Purpose after archive.
## Requirements
### Requirement: Office Scene Layout
The `OfficeScene` page SHALL render a single `<canvas>` element of fixed logical resolution 564×445 (pathfinding grid 35×27, cell 16×16 px) displayed 1:1. The scene background is the design mockup itself — `public/office/office-bg.png`, extracted by `scripts/extract_office_assets.py` (dark frame, cream wall + furniture band, sage checkered floor, mid-left workstations with two seated workers, L-shaped reception counter, bottom-right review desks with two seated workers, library table, water cooler, waste bin). Only the three standing protagonists (proposer / decider / trader) are drawn as dynamic sprites on top. A role legend row renders below the canvas. CSS MUST apply `image-rendering: pixelated` and the canvas context MUST set `imageSmoothingEnabled = false`. Obstacle rects in `characters/obstacles.ts` MUST mirror the furniture painted in the background image.

#### Scenario: Canvas mounted at the design-mockup resolution
- **WHEN** the user opens `/`
- **THEN** a `<canvas width="564" height="445">` element is mounted with `image-rendering: pixelated` CSS, `imageSmoothingEnabled = false` on its 2D context, and the design-mockup background with the three standing sprites is visible

#### Scenario: Resize preserves pixel art
- **WHEN** the viewport is resized
- **THEN** the canvas scales via CSS only with integer factors (logical resolution stays 384×256) and sprites remain crisp without sub-pixel blur

### Requirement: Character Roster
The scene SHALL instantiate exactly 13 character instances across 9 character types (`scanner`, `pattern_analyst`, `decider`, `trader`, `librarian`, `reviewer_1`..`reviewer_5`, `proposer`, `validator`, `guard`) at the default grid seats listed in `docs/frontend-public-pixel.md` §4.2. Visual tiers: (1) **movable sprites** — proposer / decider / trader use single-pose PNG sprites extracted from the design mockup (`public/office/char_*.png`), walk with a 2-frame bob; (2) **baked** — scanner / pattern_analyst / reviewer_1 / reviewer_2 are painted into the background at their desks, are clickable via fixed hit boxes, and act in place (`targetPos` stripped); (3) **bubble-only** — the remaining roster characters render no body and surface activity via speech bubbles anchored at their themed furniture.

#### Scenario: All 13 characters present at default seats on load
- **WHEN** the scene initialises with no SSE events
- **THEN** all 13 character instances render in `idle` state at their default grid coordinates from §4.2

#### Scenario: Sprite assets come from the design mockup
- **WHEN** the scene loads
- **THEN** the three movable characters load their extracted PNG sprites from `/office/char_*.png`; if an image has not finished loading, its draw is skipped for that frame and rendering proceeds normally

### Requirement: Character State Machine
Each character SHALL be in exactly one of three states: `idle`, `walking` (with `path: GridPos[]` and `pathIdx: number`), or `acting` (with `action: string`, `startedAt: number`, `durationMs: number`, optional `bubble: string`). Transitions: `idle` → `walking` on action arrival when path needed; `idle` → `acting` directly when already at target; `walking` → `acting` when `pathIdx >= path.length`; `acting` → `idle` when `now - startedAt >= durationMs`.

#### Scenario: Idle character receives action requiring movement
- **WHEN** an action with `targetCharId` set and target grid != current pos is enqueued for a character in `idle`
- **THEN** the character transitions to `walking` with a BFS-computed path, advances one grid cell per tick, then transitions to `acting` on arrival

#### Scenario: Acting character finishes after durationMs
- **WHEN** a character has been in `acting` for `durationMs` ms
- **THEN** it transitions back to `idle` and dequeues the next action from its queue if any

### Requirement: BFS Pathfinding
The scene SHALL provide `pathfind(from: GridPos, to: GridPos, obstacles: Set<GridKey>): GridPos[] | null` implemented as 4-neighbour BFS over the 24×16 grid. The function MUST return `null` when no path exists and MUST not allocate more than 384 visited entries.

#### Scenario: Path exists around obstacles
- **WHEN** `pathfind` is called with `from`, `to`, and an obstacle set that does not fully enclose `to`
- **THEN** it returns a shortest 4-neighbour grid path from `from` to `to`

#### Scenario: Path blocked
- **WHEN** `to` is fully enclosed by obstacles
- **THEN** `pathfind` returns `null`

### Requirement: SSE Connection
The `usePublicSSE` hook SHALL open an `EventSource` against `/api/public/events` on mount, close it on unmount, and rely on the browser's built-in reconnect. It MUST NOT send any custom auth header.

#### Scenario: Connection opens on mount
- **WHEN** `OfficeScene` mounts
- **THEN** exactly one `EventSource` is created targeting `/api/public/events` with no `Authorization` header

#### Scenario: Reconnect after transient disconnect
- **WHEN** the SSE connection drops
- **THEN** the browser's native `EventSource` retry attempts to reconnect within 5 seconds; no manual retry logic is added

### Requirement: Event Router
A pure `EVENT_ROUTER` map SHALL handle the 16 `event_type` values from `docs/backend-eventbus.md` §3.2 (`screener_started`, `screener_completed`, `pattern_detected`, `decider_thinking`, `decision_made`, `awaiting_confirm`, `order_sent`, `journal_written`, `journal_queried`, `review_node_started`, `review_completed`, `proposal_created`, `wfa_started`, `wfa_passed`, `wfa_failed`, `risk_off_triggered`) and translate each to a `CharacterAction` with `{ targetCharId, action, durationMs, bubble? }`. Unknown `event_type` values MUST be ignored without throwing.

#### Scenario: Known event routes to character
- **WHEN** an SSE message with `event_type: "decision_made"` and a valid masked payload arrives
- **THEN** `EVENT_ROUTER.decision_made(event)` returns an action targeting `decider` with `action: "decided"` and `durationMs: 3000`

#### Scenario: Unknown event ignored
- **WHEN** an SSE message with `event_type: "future_unknown_v2"` arrives
- **THEN** no action is enqueued and no exception is thrown

### Requirement: Action Queue Backpressure
Each character SHALL have a FIFO action queue with capacity 5. When an action is enqueued for an `idle` character, it executes immediately. When the character is `walking` or `acting`, the action is pushed to the queue. If the queue is at capacity, the oldest queued action MUST be dropped to make room.

#### Scenario: Idle character executes immediately
- **WHEN** an action is enqueued for a character in `idle`
- **THEN** the character transitions out of `idle` in the same tick, and the queue length stays 0

#### Scenario: Oldest action dropped at capacity
- **WHEN** an action is enqueued for a character whose queue already holds 5 actions
- **THEN** the queue length stays 5, the front (oldest) action is removed, and the new action is appended at the tail

### Requirement: Frontend Mask Defense
Before any speech bubble or timeline text is rendered, the UI SHALL strip any contiguous run of exactly 4 ASCII digits via `/\b\d{4}\b/g` → `STK-?`. No character or text field MUST display raw 4-digit numbers.

#### Scenario: Backend leaks a 4-digit token in bubble text
- **WHEN** an SSE payload contains the string `"買 2330 100 股"` in a bubble
- **THEN** the rendered bubble shows `"買 STK-? 100 股"`

#### Scenario: Non-4-digit numbers preserved
- **WHEN** a bubble contains `"score 0.72"` or `"100 股"` or `"12345"`
- **THEN** those substrings are rendered unchanged (only standalone 4-digit groups are stripped)

### Requirement: No PII Storage
The `web-public/` app MUST NOT write to `document.cookie`, `localStorage`, `sessionStorage`, or `IndexedDB`. It MUST NOT load any third-party analytics, error reporting, or tag manager script.

#### Scenario: Static analysis finds zero storage writes
- **WHEN** the production bundle is grepped for `localStorage`, `sessionStorage`, `document.cookie`, `indexedDB`
- **THEN** no usages exist outside of vendor library internals that are not invoked

#### Scenario: Network panel during full session
- **WHEN** a user loads `/`, watches it idle, and triggers each event type once
- **THEN** the only network destinations are the same-origin `/api/public/events` SSE stream and static assets from the same origin

### Requirement: Agent Info Sheet
Clicking a character SHALL open an `AgentInfoSheet` panel showing `{ agent: <character_id>, current_state, recent_events: PublicEvent[] (max 5), total_events_today: number }`. The panel MUST NOT display `reasoning_full`, raw confidence lists, or any field outside the public mask whitelist.

#### Scenario: Click opens sheet with 5 recent events
- **WHEN** the user clicks the `decider` sprite after 7 decider events have arrived
- **THEN** the sheet renders with the 5 most recent decider events (masked), the current state, and a count of 7

#### Scenario: Sheet hides reasoning_full
- **WHEN** the sheet renders any event
- **THEN** the DOM contains no `reasoning_full` field even if the SSE payload contained one

### Requirement: Activity Timeline
A `TimelineMarquee` component SHALL display a horizontally scrolling list of the most recent 8 events at the bottom of the page. The underlying store MUST cap retained events at 100 (oldest dropped). Clicking the marquee SHALL expand it to a full list view.

#### Scenario: Marquee shows latest 8
- **WHEN** 12 events have been received
- **THEN** the marquee shows the 8 most recent in newest-first order

#### Scenario: Store caps at 100
- **WHEN** 150 events have been received
- **THEN** `useStore.getState().timeline.length === 100` and the 50 oldest are dropped

### Requirement: Disclaimer Banner Non-Closable
A `DisclaimerBanner` SHALL render at the top of every page (`OfficeScene`, `About`) with educational-demo / not-investment-advice text. It MUST NOT have a close button.

#### Scenario: Banner present on every route
- **WHEN** the user navigates between `/` and `/about`
- **THEN** the banner remains visible on both routes

#### Scenario: No close affordance in DOM
- **WHEN** the rendered banner DOM is inspected
- **THEN** no `<button>`, `aria-label="close"`, or `data-dismiss` element exists inside the banner

### Requirement: Idle Fallback Display
When no SSE event has been received for 60 seconds, the scene SHALL display the localised string `"目前 idle，等待開盤 09:00"` (zh-TW) or its English equivalent overlaid on the canvas. All characters MUST remain in `idle` state with their idle animation frame cycling.

#### Scenario: First load with no events
- **WHEN** the page loads at 22:00 with no events arriving
- **THEN** after 60 seconds the idle overlay appears and all 13 characters cycle their idle frames

#### Scenario: Event arrives clears idle overlay
- **WHEN** an SSE event arrives while the idle overlay is visible
- **THEN** the overlay hides within the next tick

### Requirement: Internationalization
The app SHALL ship `i18next` with locales `zh-TW` (default) and `en`. Locale selection MUST come from `URLSearchParams` (`?lang=en`) and fall back to `<html lang>` then `zh-TW`. Locale state MUST NOT be persisted to storage.

#### Scenario: Default locale is zh-TW
- **WHEN** the user opens `/` with no query string
- **THEN** all i18n strings render in zh-TW

#### Scenario: ?lang=en switches locale
- **WHEN** the user opens `/?lang=en`
- **THEN** all i18n strings render in English; no cookie or storage entry is written

### Requirement: Performance Budget
The production build SHALL satisfy: gzip bundle (entry chunk + lazy chunks excluding sprite assets) < 150 KB; Lighthouse Performance score > 90 on a desktop run against `npm run preview`; LCP < 1.5 s; canvas tick rate stable at 30 Hz on a 2024-era laptop (with degradation to 15 Hz only when `document.hidden`).

#### Scenario: Build size check passes
- **WHEN** `npm run build` is run and gzip sizes are summed for all `*.js` chunks
- **THEN** the total is < 150 KB

#### Scenario: Tick rate degrades on hidden tab
- **WHEN** `document.visibilitychange` fires with `document.hidden === true`
- **THEN** the game loop reduces from 30 Hz to 15 Hz, and restores to 30 Hz when the tab becomes visible again

### Requirement: SEO Fallback
Both `/` and `/about` SHALL ship server-rendered static HTML with `<title>`, `<meta name="description">`, and OG tags. A `<noscript>` block on `/` MUST describe the project in one paragraph plus a link to `/about`.

#### Scenario: Crawler sees meta tags without JS
- **WHEN** the page is fetched with JavaScript disabled
- **THEN** the response includes `<title>`, `<meta name="description">`, `<meta property="og:*">`, and a non-empty `<noscript>` paragraph

### Requirement: Routing
React Router v7 SHALL define exactly two routes under the existing `App` shell: `/` → `OfficeScene` and `/about` → `About`. No catch-all or additional routes MAY be added in this MVP.

#### Scenario: Unknown path falls back to office
- **WHEN** the user navigates to `/anything-else`
- **THEN** the router resolves to the index route (`/`) or 404 boundary; no third route is registered

### Requirement: Single-Module Palette
All visual output (Canvas fill / stroke, sprite generation, UI overlay text colour, Tailwind theme tokens for non-Canvas components) MUST use only colours imported from `src/styles/palette.ts`. The palette is derived from the reference design mockup (sage checkered floor, cream wall, warm wood furniture, near-black outlines, per-character hair / shirt colours) and exported as a single `PALETTE` const object. Hard-coded hex / rgb / hsl literals outside this file MUST NOT appear anywhere under `src/canvas/`, `src/components/`, or `src/pages/`.

#### Scenario: Palette module is the single colour source
- **WHEN** `src/styles/palette.ts` is imported
- **THEN** it exports a `PALETTE` object marked `as const` plus named token exports, and every Canvas / sprite colour resolves to one of its values

#### Scenario: Source grep finds no off-palette literals
- **WHEN** `grep -rE '#[0-9a-fA-F]{3,6}|rgb\(|hsl\(' src/canvas src/components src/pages` is run
- **THEN** every match resolves to a value imported from `src/styles/palette.ts` (or appears inside a comment / test fixture explicitly marked as expected-violation)

### Requirement: Integer-Scale Pixel Rendering
The canvas context MUST disable image smoothing (`ctx.imageSmoothingEnabled = false`) on every frame. CSS upscaling of the canvas element MUST use integer scale factors only (1×, 2×, 3×). No CSS transform with non-integer scale, no `filter: blur`, no `transition` on `transform` MAY be applied to the canvas element. The floor and walls are part of the background image asset and MUST NOT be redrawn procedurally.

#### Scenario: Smoothing disabled every frame
- **WHEN** the render function executes
- **THEN** the first call on the 2D context is `ctx.imageSmoothingEnabled = false` (defensive, since some browsers reset this on canvas resize)

#### Scenario: Integer scale only
- **WHEN** the canvas element's computed `transform` is inspected
- **THEN** the scale factor is an integer (1, 2, or 3); no `scale(1.5)`-style fractional values appear

#### Scenario: Floor stripes alternate 1-px rows
- **WHEN** a frame is rendered
- **THEN** the floor area shows alternating 1-px horizontal stripes using `--gb-floor-light` on even rows and `--gb-floor-dark` on odd rows

### Requirement: Game Loop Cadence
A single `requestAnimationFrame` loop SHALL drive the scene. Logic ticks MUST run at a fixed 30 Hz (`MS_PER_TICK = 1000 / 30`). Renders MAY occur every animation frame (~60 Hz) and MAY interpolate character positions between ticks for smoothness.

#### Scenario: Logic and render decoupled
- **WHEN** the loop runs for 1 second on a 60 Hz display
- **THEN** logic `tick()` is called ~30 times and `render()` is called ~60 times

#### Scenario: Single loop instance
- **WHEN** the `OfficeScene` mounts and unmounts twice
- **THEN** the active `requestAnimationFrame` callback count returns to 0 between mounts (no leaked loops)

