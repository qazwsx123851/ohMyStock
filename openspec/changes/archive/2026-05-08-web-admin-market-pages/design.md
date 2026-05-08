## Context

Phase 4 web-admin currently has 5 of 18 pages real. `/market` and `/market/:symbol` (page-designs §10–§11) are the next stub pair to land. All upstream backend work — `screener-tw-universe`, `market-data-cache`, `technical-indicators`, `chip-data-skill`, `sepa-stage-classification`, `rs-percentile`, `eventbus-emitters`, `server-action-endpoints`, `admin-read-endpoints` — is already archived. The `screener.run` write endpoint and the SSE bus emit `screener_started` / `screener_completed` / `pattern_detected` events. The only missing back-end piece is a per-symbol read aggregator. The two front-end pages and that one new endpoint form the smallest cohesive landable unit.

The web-admin shell, design system (DataTable, KpiCard, StatusBadge), Bearer auth, `apiFetch` helper, and SSE subscriber are all in place from earlier changes. The 紅漲綠跌 semantic tokens (`--up`/`--down`) and Lucide arrow-pairing rule are an established invariant — follow them; do not re-derive them.

The page-designs SSOT (`docs/web-admin-page-designs.md` §10–§11) is the **layout / interaction / state-machine / a11y** authority for both pages. Do not invent layout. The K-line area is explicitly a labelled placeholder card — no chart library is being chosen now.

## Goals / Non-Goals

**Goals:**
- Replace the two `<ComingSoon>` stubs with real implementations driven entirely by existing storage.
- Ship one new read-only admin endpoint that aggregates per-symbol data from already-populated tables.
- Reuse `screener.run` as the only new write call from `/market`; rely on existing SSE subscriber for live updates.
- Match page-designs §10–§11 layout, state-machine, and 紅漲綠跌 rules exactly.
- Keep the change reversible: a single revert restores stubs and removes one router file.

**Non-Goals:**
- No K-line charting. The page renders a labelled placeholder `<Card>` only.
- No new providers, no new ingest, no new DB tables, no migrations.
- No edits to `screener-tw-universe`, `eventbus-emitters`, or any archived spec.
- No new SSE event types.
- No symbol-search autocomplete; navigation to `/market/{symbol}` is via screener row-click or direct URL only.
- No write actions on `/market/{symbol}`. It is read-only.

## Decisions

### D1 — One aggregator endpoint, not five

**Decision:** Expose a single `GET /api/admin/market/symbols/{symbol}` that returns `{symbol, quote, bars_daily[], rs, sepa, institutional[], recent_patterns[]}` in one round-trip.

**Why:** The detail page wants 5 data sources composed visually as one screen. Five chatty endpoints would mean five independent `loading` / `error` boundaries on a single page, five Skeleton variants, and five places to forget Bearer auth. One aggregator yields one tri-state (loading / empty / error) for the whole screen — matches the SSOT's "page-level state" wording in §11.

**Alternatives considered:**
- *Five separate endpoints* — rejected: more loading states, more code, more test surface, no real reuse benefit (no other page composes these five).
- *GraphQL-ish field selection on one endpoint* — rejected: solo-dev project, no other consumer, premature.

### D2 — Read tables directly; no new repository module

**Decision:** The new route reads `bars_daily`, `rs_rating_cache`, `journal_entries` directly via existing helpers (`select_bars` from `data/cache.py`) plus inline SQL for the others. Stage is recomputed on the fly via `sepa.stage.classify_stage(bars)`. Institutional flow rows come via `chip.three_major.get_three_major_investors` if it returns DB-cached rows fast, else direct SQL on the chip table the skill writes to. No new repository class.

**Why:** This is the only consumer of this composition shape. A repository class would be one-call-deep abstraction. CLAUDE.md feedback memory explicitly favours simpler designs; the existing `routes/positions.py` does direct SQL with helper functions and is the established pattern.

**Alternatives considered:**
- *Add `ohmystock/market/repository.py`* — rejected: zero reuse, premature abstraction.
- *Compose at the front-end via parallel calls* — rejected: see D1.

### D3 — `bars_daily` window default = 60, max = 252

**Decision:** Endpoint accepts `?days=N` (1..252, default 60). 60 is enough for the placeholder K-line caption "近 60 日" and is the minimum useful window for visual context. 252 is one trading year — caps response payload at well under 50 KB even for noisy symbols.

**Why:** Bound the payload deterministically. Avoids "send me everything" bug bait. 252 matches the rs-rating universe-closes floor already in use.

### D4 — `recent_patterns` source: `journal_entries` filtered to pattern-detection rows

**Decision:** Pull recent patterns from `journal_entries` for the symbol, ordered by `ts DESC`, last 30 calendar days, capped at 20 rows. Field shape: `{ts, pattern, score, outcome}` where `outcome` is best-effort derived from a paired `exit` row if present, else the literal string `"未進場"`.

**Why:** SSOT §11 patterns table shows column "結局" with values like "+2.5% 持有中", "-3% 出場", "未進場". The journal already records both pattern detections and trade outcomes. Reuse instead of invent.

**Alternatives considered:**
- *New `pattern_detections` table* — rejected: schema churn for a derivable view.

### D5 — `/market` reuses `runScreener` API client; the page is a thin shell over `apiFetch` + SSE

**Decision:** Add (or extend) a `web-admin/src/lib/api.ts` `runScreener(input)` wrapper for `POST /api/admin/screener/run`. Reuse the existing SSE subscriber added in `eventbus-emitters-v0`. The page holds local state for filter form, result rows, last-run summary, and live-feed buffer (capped at 20 events; render latest 5).

**Why:** Stays consistent with prior page implementations (PaperOrders / PaperOverview).

### D6 — 紅漲綠跌 columns, exactly per SSOT

**Decision:**
- `/market` "漲跌" column → `text-up` + `<ArrowUp/>` for >0, `text-down` + `<ArrowDown/>` for <0, muted "—" for 0.
- `/market` "Pattern" column → directional patterns get `<TrendingUp className="text-up"/>`, bearish get `<TrendingDown className="text-down"/>`; neutral patterns no colour.
- `/market` "Score" column → no colour; bold ≥0.7.
- `/market/:symbol` header delta → standard 紅漲綠跌 + arrow.
- `/market/:symbol` 三大法人 numeric columns → row-by-row colour + tiny inline arrow.
- `/market/:symbol` patterns "結局" column → matches P&L colouring; "未進場" muted.

**Why:** This is the locked invariant from `web-admin-design-system`. Re-stating to make it auditable per scenario. Color-only signalling is forbidden; arrow icon must accompany colour.

### D7 — Fail-soft composition: a missing sub-source returns `null`/`[]`, not 500

**Decision:** If `rs_rating_cache` has no row for the symbol/asof, return `rs: null`. If chip table is empty for the window, return `institutional: []`. If `journal_entries` has no pattern rows, `recent_patterns: []`. Endpoint is 200 with partial data; only an unrecoverable infra error returns the standard envelope error.

**Why:** Page can render meaningful UI even on partial data (e.g., a symbol just added to universe has bars but no RS yet). Prevents a single empty sub-table from blanking the whole page.

**Alternatives considered:**
- *Strict mode (any missing piece → 502)* — rejected: too brittle for a personal-use admin tool.

### D8 — 404 vs empty: only `bars_daily` is the gating data source

**Decision:** If `bars_daily` for the symbol is empty over the requested window, return 404 with envelope `{ok:false, error:{code:"market_symbol_not_found", message:"..."}}`. All other sub-sources missing → see D7.

**Why:** Without bars there is no quote, no chart, no stage classification, no useful page. With bars, every other gap is renderable.

## Risks / Trade-offs

[**Stage classification cost**] The `sepa.stage.classify_stage()` helper takes a `list[BarRow]`. Recomputing on each request is O(60) work — negligible. → **Mitigation:** none needed; if it ever shows in profiles, cache via the existing chip cache pattern.

[**Quote source asymmetry**] `quote.price` from latest `bars_daily` is end-of-day; the page UI implies live intraday quote per page-designs §11. → **Mitigation:** Endpoint clearly returns the close price labelled `asof: <last-bar-date>`. UI shows that date next to the price. Real intraday wiring is a follow-up change; not worth coupling to this one.

[**SSE feed buffer leak**] `/market` accumulates `pattern_detected` events for live-feed rendering. → **Mitigation:** Cap buffer at 20; on unmount, unsubscribe. Already the established pattern from PaperOverview.

[**Score sort tri-state churn**] page-designs §10 says "score header click → 三循環排序" (asc / desc / unsorted). The shared `<DataTable>` currently supports sort but the tri-state cycle has not been validated for this specific column. → **Mitigation:** Reuse whatever the DataTable composite supports; if currently two-state, ship two-state and note the deviation in scenarios. Don't expand DataTable in this change.

[**Cross-page navigation contract**] `/market/{symbol}` patterns row-click navigates to `/audit?symbol=...&date_from=...`. The Audit page already accepts those query params (verified in archived spec). → **Mitigation:** Add a scenario asserting the navigated URL shape; don't change Audit.

## Migration Plan

This is additive, no migrations.

**Deploy order (single commit chain on `main`):**
1. Backend: add `routes/market.py`, register in `app.py`, add unit tests.
2. Frontend: add types + `getMarketSymbol` client + `runScreener` client (if absent).
3. Frontend: implement `MarketPage.tsx`, then `MarketSymbolPage.tsx`, with vitest tests.
4. Frontend: swap stub imports in `App.tsx` (or `router.tsx`); remove from `pages/stubs.tsx`.
5. Run typecheck + tests + build for both backend and `web-admin`.
6. Manual smoke against a real symbol (e.g. `2330`) on `localhost:5173`.

**Rollback:** revert the single feature commit; both pages return to `<ComingSoon>` and the new route disappears. No DB state to undo.

## Open Questions

- None blocking. The chart-library decision is intentionally deferred per SSOT §11 ("chart lib TBD").
