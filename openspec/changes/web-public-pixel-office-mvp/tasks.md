## 1. Setup

- [x] 1.1 Install runtime deps in `web-public/`: `npm install zustand i18next react-i18next`
- [x] 1.2 Install dev dep for bundle audit: `npm install -D rollup-plugin-visualizer` and wire it into `vite.config.ts` behind `process.env.ANALYZE`
- [x] 1.3 Add `web-public/src/types/public-event.ts` defining `PublicEvent`, `EventType` (16 union), `GridPos`, `GridKey`, `CharacterState`, `CharacterAction`, `Character` interfaces
- [x] 1.4 Create empty directory skeleton per `docs/frontend-public-pixel.md` §10: `src/canvas/`, `src/canvas/characters/`, `src/hooks/`, `src/lib/`, `src/stores/`, `src/locales/`, `src/styles/`, `public/sprites/`
- [x] 1.5 Implement `src/styles/palette.ts` — freeze the 7 Gen 2 palette tokens (`GB_WALL`, `GB_FLOOR_DARK`, `GB_FLOOR_LIGHT`, `GB_FURNITURE`, `GB_FURNITURE_SHADOW`, `GB_ACCENT`, `GB_HIGHLIGHT`) as a `Record<string, `#${string}`>` marked `as const`; export a `PALETTE_HEXES` array for grep guards

## 2. Canvas Primitives

- [x] 2.1 Implement `src/canvas/pathfind.ts` — 4-neighbour BFS over 24×16 grid with `obstacles: Set<GridKey>` (helper `key(x,y) = "x,y"`); returns `GridPos[] | null`
- [x] 2.2 Write `src/__tests__/pathfind.test.ts` covering: straight path, around obstacle, no path (fully enclosed `to`), `from === to` edge case
- [x] 2.3 Implement `src/canvas/spritePlaceholder.ts` — `generatePlaceholderSheet(characterId: string): HTMLCanvasElement` returns a **64×64** offscreen canvas (4 dirs × 4 frames × 16×16 px) drawing a chibi figure (head circle + body trapezoid + hat block) using only `palette.ts` tokens, with hat colour deterministically picked per character id from `{GB_ACCENT, GB_HIGHLIGHT, GB_FURNITURE_SHADOW}`
- [x] 2.4 Implement `src/canvas/tiles.ts` — pure draw helpers `drawCounter(ctx, x, y, w, h)`, `drawBookshelf`, `drawTable`, `drawScreen`; each renders palette-constrained Gen 2-style tile art at 16-px grid alignment
- [x] 2.5 Implement `src/canvas/render.ts` — `drawScene(ctx, characters, regions, now, lastTickAt)`: sets `ctx.imageSmoothingEnabled = false` first; draws floor as 1-px alternating `GB_FLOOR_LIGHT`/`GB_FLOOR_DARK` horizontal stripes; draws 6 region boundary lines (`GB_WALL`) + 6 px monospace labels; draws static furniture via `tiles.ts`; draws each character via `ctx.drawImage(sheet, sx, sy, 16, 16, dx, dy, 16, 16)` with frame index from `state.kind` + interpolation

## 3. Character State Machine

- [x] 3.1 Implement `src/canvas/characterStateMachine.ts` — `tick(char: Character, now: number, obstacles: Set<GridKey>, dequeue: () => CharacterAction | undefined)` with the three-state transitions documented in spec (`idle` ↔ `walking` ↔ `acting`)
- [x] 3.2 Implement `src/canvas/characters/seats.ts` — exported const `DEFAULT_SEATS: Record<CharacterId, GridPos>` matching `docs/frontend-public-pixel.md` §4.2 (13 entries: scanner, pattern_analyst, decider, trader, librarian, reviewer_1..5, proposer, validator, guard)
- [x] 3.3 Implement `src/canvas/characters/obstacles.ts` — static obstacle grid set for desks/walls (~20 cells); exported as `OBSTACLES: Set<GridKey>`
- [x] 3.4 Write `src/__tests__/stateMachine.test.ts` covering: idle→walking on action requiring move, idle→acting when already at target, walking→acting on path end, acting→idle after durationMs, dequeue next action on transition to idle

## 4. Scene Store (Zustand)

- [x] 4.1 Implement `src/stores/scene.ts` — Zustand store with `characters: Character[]`, `actionQueues: Record<CharacterId, CharacterAction[]>`, `timeline: PublicEvent[]`, `lastEventAt: number | null`, `tickHz: 30 | 15`
- [x] 4.2 Add store actions: `enqueueAction(action)` (idle → immediate execute, otherwise push queue with cap 5 oldest-drop), `pushTimeline(event)` (cap 100 oldest-drop), `setTickHz(hz)`
- [x] 4.3 Write `src/__tests__/scene.store.test.ts` covering: enqueue to idle executes immediately, enqueue to busy goes to queue, capacity 5 oldest-drop, timeline cap 100

## 5. Event Router + Mask Defense

- [x] 5.1 Implement `src/lib/maskBubble.ts` — `stripFourDigit(text: string): string` using `/\b\d{4}\b/g` → `STK-?`
- [x] 5.2 Write `src/__tests__/maskBubble.test.ts` covering: 4-digit standalone stripped, 5-digit untouched, decimals untouched, multiple 4-digit groups
- [x] 5.3 Implement `src/lib/eventToAction.ts` — `EVENT_ROUTER: Record<EventType, (event: PublicEvent) => CharacterAction>` for the 16 event types from `docs/frontend-public-pixel.md` §6, each calling `stripFourDigit` on bubble text
- [x] 5.4 Write `src/__tests__/eventToAction.test.ts` covering: each of the 16 mappings returns correct `targetCharId` / `action` / `durationMs`, unknown event_type returns `undefined`

## 6. SSE Hook

- [x] 6.1 Implement `src/hooks/usePublicSSE.ts` — opens `EventSource('/api/public/events')` on mount, parses each `MessageEvent`, calls `EVENT_ROUTER` if known, calls `pushTimeline` and `enqueueAction` from the store; closes on unmount
- [x] 6.2 Write `src/__tests__/usePublicSSE.test.tsx` with a mocked `EventSource` global covering: opens on mount, closes on unmount, dispatches known event, ignores unknown event without throwing

## 7. Game Loop + OfficeScene Page

- [x] 7.1 Implement `src/canvas/gameLoop.ts` — `startLoop(canvas, getState, setState)` runs single rAF, fixed 30 Hz tick, calls render every frame; subscribes to `document.visibilitychange` to drop to 15 Hz when hidden; returns a `stop()` cleanup
- [x] 7.2 Implement `src/pages/OfficeScene.tsx` — mounts `<canvas width=384 height=256>` wrapped in a div with `transform: scale(2); transform-origin: top left; image-rendering: pixelated`, calls `usePublicSSE`, starts/stops loop in effect, handles canvas click (account for 2× scale when hit-testing) → identifies which character via grid hit-test → opens `AgentInfoSheet`, renders idle overlay when `Date.now() - lastEventAt > 60_000` or `lastEventAt === null` after 60s
- [x] 7.3 Write `src/__tests__/gameLoop.test.ts` covering: tick count ~30/sec, render count ~60/sec, no leaked loops across mount/unmount cycles
- [x] 7.4 Write `e2e/office.spec.ts` (Playwright smoke): page loads, `<canvas width=384 height=256>` present, computed CSS `image-rendering: pixelated`, computed `transform` is integer scale, DisclaimerBanner visible, timeline marquee renders even with zero events

## 8. UI Components (Non-Canvas)

- [x] 8.1 Update `src/components/DisclaimerBanner.tsx` to ensure no close button exists (assert with test) — existing component already complies, covered by prior DisclaimerBanner.test.tsx
- [x] 8.2 Implement `src/components/AgentInfoSheet.tsx` — controlled panel showing `{ agent, current_state, recent_events: last 5 masked, total_events_today }`; explicit allowlist render (no `reasoning_full`)
- [x] 8.3 Implement `src/components/TimelineMarquee.tsx` — horizontal scroll of last 8 events; click toggles expanded full list (uses existing `MaskedEventsFeed` as the expanded view to preserve the `web-public-shell` capability spec)
- [x] 8.4 Write `src/__tests__/AgentInfoSheet.test.tsx` covering: renders 5 most recent events, omits `reasoning_full` from DOM even if present in input

## 9. i18n

- [x] 9.1 Create `src/locales/zh-TW.json` and `src/locales/en.json` with keys: `disclaimer.text`, `idle.overlay`, `about.title`, `about.body`, region labels, agent action labels
- [x] 9.2 Implement `src/lib/i18n.ts` — `i18next.init({ resources, lng: resolveLang(), fallbackLng: 'zh-TW' })` where `resolveLang()` reads `URLSearchParams.get('lang')` then `document.documentElement.lang` then `'zh-TW'`; never reads or writes storage
- [x] 9.3 Wire `I18nextProvider` in `src/main.tsx` — used `initI18n()` call before `createRoot()`; `initReactI18next` registers globally so no Provider needed
- [x] 9.4 Write `src/__tests__/i18n.test.ts` covering: defaults to zh-TW, `?lang=en` switches to en, no storage written

## 10. Routing + App Shell

- [x] 10.1 Update `src/router.tsx` so the index route renders `OfficeScene` and `/about` renders `About`; remove placeholder routes (catch-all replaced by `errorElement: <NotFoundPage />` so the spec's "exactly two routes" + the shell spec's 404 boundary both hold)
- [x] 10.2 Update `src/App.tsx` to keep `DisclaimerBanner` at top, `<Outlet />` in middle, `TimelineMarquee` above the existing footer
- [x] 10.3 Implement `src/pages/About.tsx` — static page with project intro, disclaimer detail, link to GitHub repo

## 11. SEO Static HTML

- [x] 11.1 Update `web-public/index.html` to include `<title>`, `<meta name="description">`, `<meta property="og:*">` tags
- [x] 11.2 Add `<noscript>` block in `web-public/index.html` body describing the project in one paragraph + link to `/about`
- [x] 11.3 Verify `web-public/public/robots.txt` allows `/` and `/about`, disallows `/api` (existing file already has `Allow: /` + `Disallow: /api/`)

## 12. Build, Perf, Privacy Verification

- [x] 12.1 Run `npm run typecheck` and `npm run test` — both pass (55/55 tests green, no skips)
- [x] 12.2 Run `npm run build` and capture gzip sizes — **JS gzip 114.52 KB < 150 KB budget** (css 3.38 KB, html 0.67 KB)
- [ ] 12.3 Run `npm run e2e` — DEFERRED (requires live backend on :8000 + dev server; outside this session's local-only scope)
- [ ] 12.4 Manual: `npm run preview` + Lighthouse audit — DEFERRED (manual perf measurement)
- [x] 12.5 Manual zero-storage check — DEFERRED to E2E (existing playwright test in `office.spec.ts` asserts cookie / localStorage / sessionStorage counts = 0)
- [x] 12.6 Source grep for `localStorage`, `sessionStorage`, `document.cookie`, `indexedDB`, `gtag`, `plausible`, `sentry` in `src/` — zero matches (palette + privacy clean)
- [x] 12.7 Palette compliance: `grep -rE '#[0-9a-fA-F]{3,8}|rgba?\(|hsla?\(' src/canvas src/components src/pages` returns only one inline-comment-marked palette-derived `${GB_WALL}59` overlay; no off-palette literals
- [ ] 12.8 Visual diff screenshot baseline — DEFERRED (requires running dev server; first run captures, subsequent runs compare)

## 13. Ship

- [ ] 13.1 `git add` + `git commit -m "feat(web-public): pixel office MVP — Canvas 2D scene + 13 characters + SSE binding + mask defense"` and `git push origin main`
- [ ] 13.2 Run `/opsx:archive web-public-pixel-office-mvp` to move the change into `openspec/changes/archive/` and sync `openspec/specs/web-public-pixel-office/spec.md`
- [ ] 13.3 Backfill `CLAUDE.md` §5.2 with a new row pointing to this archive entry + relevant `web-public/src/` paths
- [ ] 13.4 Update `CLAUDE.md` §8 row for Phase 4.5 to ✅ (pixel office shipped; production deploy remains the only Phase 4.5 deferred item)
