## 1. Backend — `GET /api/admin/market/symbols/{symbol}` route

- [x] 1.1 Create `src/ohmystock/api/routes/market.py` with `APIRouter(dependencies=[Depends(require_admin)])`, modelled on `routes/positions.py` (per-request `Depends(get_db)`, `_envelope.to_success` / `map_exception_to_envelope`)
- [x] 1.2 Define Pydantic models: `Quote`, `MarketBar`, `RsRating`, `SepaInfo`, `InstitutionalRow`, `RecentPattern`, `MarketSymbolData` (frozen `model_config`)
- [x] 1.3 Implement `?days` query param validation (1..252, default 60) — return 400 `invalid_days` envelope on out-of-range; let FastAPI 422 handle non-int (envelope mapping already handles it)
- [x] 1.4 Implement `bars_daily` lookup via `data.cache.select_bars(conn, symbol, start, end)` over a business-day-walked window; return 404 `market_symbol_not_found` envelope if 0 rows
- [x] 1.5 Implement `quote` derivation: `price = last.close`, `volume = last.volume`, `change = last.close - prev.close` (or `null` if only 1 bar), `change_pct = change / prev.close` (or `null`), `asof = last.date`
- [x] 1.6 Implement `rs` lookup: `SELECT symbol, asof_date, rs_rating FROM rs_rating_cache WHERE symbol = ? ORDER BY asof_date DESC LIMIT 1` → `{value, asof}` or `null`
- [x] 1.7 Implement `sepa` via `sepa.stage.classify_stage(bars)` over the just-fetched bars; on exception or insufficient data, set `data.sepa = null`
- [x] 1.8 Implement `institutional`: query the chip table written by `chip.three_major` for last 5 trading days for this symbol, ascending by date; rows with `total = foreign + trust + dealer`; empty → `[]`
- [x] 1.9 Implement `recent_patterns`: query `journal_entries` for pattern-detection rows in last 30 calendar days, `ORDER BY ts DESC`, cap 20; for each, look ahead in same `symbol` for paired `entry`/`exit` rows; compute `outcome` strings (`"+X% 出場"` / `"+X% 持有中"` / `"未進場"`)
- [x] 1.10 Register the router in `src/ohmystock/api/app.py` (import + `app.include_router(market.router)`)
- [x] 1.11 Add unit tests at `tests/api/test_market_endpoint.py` covering: 401 no-token, 401 wrong-token, 200 happy path, 400 days=0/days=253, 422 days=foo, 404 unknown symbol, fail-soft (no RS / no chips / no patterns), `change=null` when only 1 bar, `total = foreign+trust+dealer` invariant, recent-patterns outcome variants (entry+exit / entry-only / unmatched), days=1 / days=252 boundary
- [x] 1.12 `python -m pytest tests/api/test_market_endpoint.py -v` and confirm all pass
- [x] 1.13 `python -m pytest tests/ -x` (full suite) — confirm no regressions

## 2. Frontend — types + API client

- [x] 2.1 In `web-admin/src/lib/api.ts` (or matching types module) add exported types: `MarketBar`, `Quote`, `RsRating`, `SepaInfo`, `InstitutionalRow`, `RecentPattern`, `MarketSymbolDetail`, `ScreenerHit` (fields aligned to backend Pydantic models)
- [x] 2.2 Add `getMarketSymbol(symbol: string, options?: { days?: number }): Promise<MarketSymbolDetail>` wrapping `apiFetch`; URL `/api/admin/market/symbols/{symbol}` plus optional `?days=N`
- [x] 2.3 Add `runScreener(input: ScreenerInput): Promise<ScreenerRun>` if not already present; URL `/api/admin/screener/run`
- [x] 2.4 Add tests in `web-admin/src/lib/__tests__/api.test.ts` (or extend existing) for: `getMarketSymbol("2330", {days:90})` → path includes `/api/admin/market/symbols/2330` and `days=90`; `getMarketSymbol("2330")` → no `days=` in path; `runScreener` posts JSON body to correct URL

## 3. Frontend — `/market` page

- [x] 3.1 Create `web-admin/src/pages/MarketPage.tsx` with filter form (universe `<Select>`, custom-symbols chip-input, 4 filter checkboxes, asof `<input type="date">` defaulting to today), action button「跑 screener」
- [x] 3.2 Wire form-submit and `Cmd/Ctrl+Enter` to `runScreener(input)`; manage `loading | hits | error` state
- [x] 3.3 Render last-run summary (`r#{run_id} · {hh:mm} · 共 N 命中 · {ms}`) above result table
- [x] 3.4 Render result `<DataTable>` with 6 columns (Symbol / 名稱 / 現價 / 漲跌 / Pattern / Score); row-click → `useNavigate()(/market/{symbol})`; Score column bold ≥0.7, no colour
- [x] 3.5 Apply 紅漲綠跌 to「漲跌」column (Lucide `ArrowUp`/`ArrowDown` + `text-up`/`text-down`); apply directional `<TrendingUp/>`/`<TrendingDown/>` to「Pattern」column based on pattern-name keyword (`breakout` / `failed entry` / `pullback` / etc.)
- [x] 3.6 Subscribe to existing SSE bus for `screener_started` / `screener_completed` / `pattern_detected`; on `pattern_detected` prepend a row + 0.5s flash; cap live-feed buffer at 20, render latest 5
- [x] 3.7 Implement loading state (≥3 Skeleton rows + summary「啟動中…」), empty state (「本次掃描無命中」+ hint), error state (`text-destructive` block + retry button, do not clear form)
- [x] 3.8 Add a11y: tab order matches scenario; `Cmd/Ctrl+Enter` global hotkey (only inside form scope); chip-input Enter/Backspace behaviour
- [x] 3.9 Add `web-admin/src/pages/__tests__/MarketPage.test.tsx` covering each scenario from `specs/web-admin-market-pages/spec.md` § "/market 頁面實作" + § "三態與 live update"

## 4. Frontend — `/market/{symbol}` page

- [x] 4.1 Create `web-admin/src/pages/MarketSymbolPage.tsx`; read `:symbol` from `useParams()`; call `getMarketSymbol(symbol)` on mount
- [x] 4.2 Render header: 千分位 `price`, signed `change_pct` (1–2 decimals), 紅漲綠跌 + arrow, `asof` date label; back-link to `/market`
- [x] 4.3 Render K-line placeholder `<Card>` with caption「K 線圖（圖庫待定）」— do NOT install any chart library
- [x] 4.4 Render 3 chip KPI cards (RS Rank / SEPA Stage / 連續買超); show `—` when `rs` is null; SEPA card shows「Stage {n}」+ since-date if available
- [x] 4.5 Render 三大法人 `<DataTable>` (compact density, 5 cols) with row-by-row 紅漲綠跌 + arrow on numeric cells; empty → 「近 5 日無法人資料」message
- [x] 4.6 Render Patterns `<DataTable>` (4 cols); row-click → `navigate('/audit?symbol=' + symbol + '&date_from=' + ts.slice(0,10))`; 「結局」cell colours by `outcome` prefix (`+` → up, `-` → down, `未進場` → muted)
- [x] 4.7 Implement loading (Skeletons across 5 sections), 404 (「該 symbol 無資料」+ back link), generic error (`text-destructive` + retry) states
- [x] 4.8 Add `web-admin/src/pages/__tests__/MarketSymbolPage.test.tsx` covering each scenario from `specs/web-admin-market-pages/spec.md` § "/market/{symbol} 頁面實作" + § "三大法人表 + Patterns 表" + § "三態"

## 5. Wire into router; remove stubs

- [x] 5.1 In `web-admin/src/router.tsx` (or `App.tsx`) replace stub imports `MarketPage`/`MarketSymbolPage` with real imports from `./pages/MarketPage` and `./pages/MarketSymbolPage`
- [x] 5.2 Remove `MarketPage` and `MarketSymbolPage` exports from `web-admin/src/pages/stubs.tsx`
- [x] 5.3 Add a smoke test that mounts the router and asserts `/market` and `/market/2330` do not render `<ComingSoon>`

## 6. Verification

- [x] 6.1 `cd web-admin; pnpm typecheck` → 0 errors
- [x] 6.2 `cd web-admin; pnpm test --run` → all green
- [x] 6.3 `cd web-admin; pnpm build` → exits 0
- [x] 6.4 `python -m pytest tests/ -x` → all green
- [ ] 6.5 _(skipped — requires manual browser smoke; automated suites all green)_ Manual smoke on `localhost:5173`: log in with token, navigate `/market`, run screener against `tw50`, click a row, confirm `/market/{symbol}` renders headers, KPIs, both tables; toggle filters; observe SSE prepend on pattern event
- [x] 6.6 `openspec validate web-admin-market-pages --strict` → passes
- [x] 6.7 Update `CLAUDE.md` §5 SSOT table (post-archive entry pointing to `openspec/specs/web-admin-market-pages/spec.md` and `openspec/specs/admin-market-symbol-endpoint/spec.md` plus the new `src/ohmystock/api/routes/market.py`)

## 7. Archive

- [ ] 7.1 `git add` + commit per CLAUDE.md style; push to `main` directly
- [ ] 7.2 Run `/opsx:archive web-admin-market-pages` to move change → `openspec/changes/archive/<date>-web-admin-market-pages/` and sync delta into `openspec/specs/`
