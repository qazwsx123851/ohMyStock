## Why

Phase 4 web-admin has 5 of 18 pages real; the rest are `<ComingSoon>` stubs. The Market bundle (`/market` scan + `/market/:symbol` detail) is the next-best target because all backend dependencies (market-data-cache, technical-indicators, chip-data, RS percentile, screener-tw-universe) are archived and the `screener.run` write endpoint already ships. Replacing these two stubs unblocks visual dogfooding of the screener output and gives Mark a real per-symbol drilldown — the missing link between Audit findings and the rest of the workflow.

## What Changes

- Add **`GET /api/admin/market/symbols/{symbol}`** aggregator endpoint that composes one symbol's quote, daily-bar series (60d default, capped at 252d), latest RS rating, latest SEPA stage, recent institutional flows from `chip_data_*`, and recent `pattern_detected` rows from the journal — all from existing storage; no new providers wired.
- Implement real **`/market` page** consuming `POST /api/admin/screener/run` + SSE `screener_started` / `screener_completed` / `pattern_detected`. Filter form (universe / custom symbols chips / SEPA / RS≥80 / 法人連續買超 / 三角收斂 / asof date), result `DataTable` (6 cols, score-sortable, row-click → `/market/{symbol}`), live event feed (latest 5 events).
- Implement real **`/market/{symbol}` page** consuming the new aggregator: header with quote + 紅漲綠跌 delta, K-line area as a labelled placeholder card (chart lib still TBD per SSOT), 3 chip KPI cards (RS / SEPA / 連續買超), 5×5 institutional table (compact `DataTable`), 30-day patterns table with row-click → `/audit?symbol=...`.
- Wire both pages into `App.tsx` route tree, removing them from `pages/stubs.tsx`.
- Keep K-line chart out of scope — placeholder only — to avoid premature chart-lib commitment.

## Capabilities

### New Capabilities
- `web-admin-market-pages`: `/market` scan page and `/market/{symbol}` detail page real implementations, route-tree wiring, SSE consumption for screener/pattern events, `<ComingSoon>` removal for both routes.
- `admin-market-symbol-endpoint`: `GET /api/admin/market/symbols/{symbol}` aggregator returning `{symbol, quote, bars_daily[], rs, sepa, institutional[], recent_patterns[]}` from existing tables; same `{ok,data,error}` envelope, same per-request DB conn, same Bearer auth invariants as other admin read endpoints.

### Modified Capabilities

(none — all behavior added is new; no archived spec's requirements change)

## Impact

- **Code**:
  - `web-admin/src/pages/MarketPage.tsx` (new, replaces stub)
  - `web-admin/src/pages/MarketSymbolPage.tsx` (new, replaces stub)
  - `web-admin/src/pages/stubs.tsx` (remove `MarketPage`, `MarketSymbolPage` exports)
  - `web-admin/src/App.tsx` (swap stub imports → real components)
  - `web-admin/src/api/types.ts` (or equivalent) (add `MarketSymbolDetail`, `MarketBar`, `InstitutionalRow`, `RecentPattern` types)
  - `web-admin/src/api/client.ts` (add `getMarketSymbol(symbol)` wrapper; reuse existing `runScreener` if present, else add)
  - `src/ohmystock/api/routes/market.py` (new router, registered in `api/app.py`)
  - `src/ohmystock/api/app.py` (mount the new router)
- **Specs**: 2 new spec files; no archived spec mutated.
- **Tests**:
  - Backend: `tests/api/test_market_endpoint.py` (404 / happy / clamp / auth)
  - Frontend: `web-admin/src/pages/__tests__/MarketPage.test.tsx`, `MarketSymbolPage.test.tsx`
- **Dependencies**: no new packages. Reuses existing FastAPI router stack, vitest + RTL, msw (already in use for prior admin pages).
- **No live trading impact**: read-only endpoint over already-archived storage; touches no broker, no journal-write, no auto-execute path.
- **DB schema**: unchanged. Reads `bars_daily`, `rs_rating`, `sepa_stage_history`, `chip_data_*`, `journal_*` only.
