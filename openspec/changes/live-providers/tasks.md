## 1. Error taxonomy

- [x] 1.1 Add `LiveProviderError(Exception)` to `src/ohmystock/swarm/_errors.py` with `code: str` and `message: str` attributes; validate `code` against the closed set `{"DATA_UNAVAILABLE", "STALE_DATA", "UPSTREAM_ERROR", "AUTH_FAILED"}` in `__init__` (raise `ValueError` on unknown code).
- [x] 1.2 Re-export `LiveProviderError` from `src/ohmystock/swarm/__init__.py`.
- [x] 1.3 Add tests `tests/test_live_provider_error.py`: code attribute exposed, str() includes message, unknown code raises `ValueError`.

## 2. Journal repository helpers

- [x] 2.1 Create `src/ohmystock/journal/repository.py` with read-only query helpers: `closed_trades_desc(conn, asof, limit) -> list[ClosedTrade]`, `open_positions(conn, asof) -> list[OpenPosition]`, `monthly_realized_pnl_pct(conn, asof, starting_equity) -> float`. Each returns plain dataclasses; no I/O outside the passed connection.
- [x] 2.2 ~~FIFO matcher~~ — superseded by `decision_id` join (cleaner per `docs/llm-decision-schema.md` §4.5.2 "Join key: decision_id"). Implemented in `open_positions` and `closed_trades_desc` via SQL `NOT EXISTS` / `JOIN` on `decision_id`.
- [x] 2.3 Add tests `tests/test_journal_repository.py` with in-memory SQLite fixtures: empty DB, one open position, one closed trade, partial exits, asof boundary, FIFO matching of multiple entries.

## 3. TAIEX bars-cache compatibility

- [x] 3.1 Relax the `_SYMBOL_RE` validator in `src/ohmystock/data/market_data.py` to also accept alphabetic index codes `^[A-Z]{3,6}$|^\d{4,6}$` so `get_kline("TAIEX", ...)` is accepted. Verify no other callers depend on the strict `\d{4,6}` form (grep first).
- [x] 3.2 Add a TAIEX symbol-mapping helper inside the FinMind/twstock/yfinance adapters (or a single shim above them) that maps `TAIEX` → FinMind `TAIEX` / twstock `TWII` / yfinance `^TWII`. Adapter unit tests use the canonical `TAIEX` form.
- [x] 3.3 Add tests `tests/test_market_data_taiex.py` covering `get_kline("TAIEX", "2026-04-01", "2026-04-30")` against fake adapters returning index data; ensure the cache writes/reads use `symbol="TAIEX"`.

## 4. live_candidate_snapshot helper

- [x] 4.1 Create `src/ohmystock/swarm/_live_candidate.py` with frozen dataclass `CandidateLiveSnapshot(current_price, ema20_distance_pct, atr_14_pct, distance_from_52w_high_pct, distance_from_52w_low_pct)` and function `live_candidate_snapshot(symbol, asof) -> CandidateLiveSnapshot`. Internally call `get_kline(symbol, bars=300, end_date=asof)`, raise `LiveProviderError` on non-OK envelopes, compute the four percentages from the bars + `ohmystock.indicators` EMA/ATR.
- [x] 4.2 Re-export `live_candidate_snapshot` and `CandidateLiveSnapshot` from `src/ohmystock/swarm/__init__.py`.
- [x] 4.3 Add tests `tests/test_live_candidate_snapshot.py`: full 252-bar window, fewer than 252 bars (no padding), `get_kline` error propagation, frozen dataclass mutation raises `FrozenInstanceError`.

## 5. LiveMarketSnapshotProvider implementation

- [ ] 5.1 Create `src/ohmystock/swarm/_live_market.py` with `compute_taiex_snapshot(asof, *, conn=None) -> MarketSnapshot` that reads TAIEX bars via `get_kline("TAIEX", bars=80, end_date=asof)`, computes `taiex_change_pct` (vs previous trading day), evaluates Risk-Off using only the TAIEX-vs-MA60 condition for v1, reads `monthly_pnl_pct` via `journal.repository.monthly_realized_pnl_pct`, and returns a `MarketSnapshot`. Other Risk-Off signals (SPY, VIX, FX, TAIFEX) are recorded as `unknown` in a separate diagnostics dict but do not flip `risk_off=True`.
- [ ] 5.2 Add staleness check: if the most recent TAIEX bar's `ts` is more than 5 business days older than `asof`, raise `LiveProviderError(code="STALE_DATA")`.
- [ ] 5.3 Replace `LiveMarketSnapshotProvider.get()` body in `src/ohmystock/swarm/_adapters.py` to delegate to `compute_taiex_snapshot(self._asof)`. Add `__init__(self, asof: str)` constructor. Update class docstring (remove "stub" / "NotImplementedError" references).
- [ ] 5.4 Add tests `tests/test_live_market_provider.py`: TAIEX above MA60 → risk_off=False, TAIEX below MA60 with flat MA → risk_off=True, stale cache raises STALE_DATA, missing cache raises DATA_UNAVAILABLE, unknown signals do not flip risk_off.

## 6. LivePortfolioSnapshotProvider implementation

- [ ] 6.1 Create `src/ohmystock/swarm/_live_portfolio.py` with `reconstruct_portfolio(asof, *, conn=None, sector_lookup=None, starting_equity=None) -> PortfolioSnapshot`. Use `journal.repository.open_positions(conn, asof)`, look up the most recent cached close `<= asof` per symbol via `select_bars`, compute `exposure_pct = (shares * close / equity) * 100`, sum to `total_exposure_pct`. Resolve sector via the screener universe sector index; missing symbols → `"未分類"`.
- [ ] 6.2 If the journal SQLite cannot be opened, raise `LiveProviderError(code="DATA_UNAVAILABLE")`.
- [ ] 6.3 Replace `LivePortfolioSnapshotProvider.get()` body in `_adapters.py` to delegate to `reconstruct_portfolio(self._asof, ...)`. Add `__init__(self, asof: str)` constructor.
- [ ] 6.4 Add tests `tests/test_live_portfolio_provider.py`: one open position with full lifecycle math, closed position excluded by FIFO, missing sector → `"未分類"` (no raise), missing journal DB → `DATA_UNAVAILABLE`.

## 7. LiveJournalStatsProvider implementation

- [ ] 7.1 Create `src/ohmystock/swarm/_live_journal.py` with `compute_recent_winrate(conn, asof, n) -> float` and `compute_consecutive_loss(conn, asof) -> int`. Use `journal.repository.closed_trades_desc`. `recent_winrate` returns `0.0` on empty; `consecutive_loss` returns `0` on empty; both compute over what exists when fewer than `n` rows.
- [ ] 7.2 Replace `LiveJournalStatsProvider.recent_winrate(n)` and `consecutive_loss()` bodies in `_adapters.py` to delegate. Add `__init__(self, asof: str)` constructor.
- [ ] 7.3 Add tests `tests/test_live_journal_provider.py`: 12-of-20 → 0.6, fewer than n → ratio over actual count, zero closed → 0.0 / 0, three losses then a win → 3, all losing → ≥5, asof boundary excludes future trades.

## 8. CLI wiring

- [ ] 8.1 In `src/ohmystock/cli/_assemble.py`, replace the five `0.0` defaults in `_run_assemble`'s signature with a call to `live_candidate_snapshot(symbol, asof)` when no value is injected. Pass the dataclass fields into `build_entry_decision_input`.
- [ ] 8.2 Update the live-provider construction at the call site to pass `asof=asof` to each `Live*Provider`.
- [ ] 8.3 Add `LiveProviderError` exception handling in the `assemble_entry_input` Typer command: map `DATA_UNAVAILABLE`→4, `STALE_DATA`→5, `UPSTREAM_ERROR`→6, `AUTH_FAILED`→7. Existing exit codes 1/2/3 unchanged.
- [ ] 8.4 Add stderr `warning:` line emission for: any open position with `sector == "未分類"`, and successful run with `risk_off=False` while diagnostics shows unwired signals. Warnings do not change exit code.
- [ ] 8.5 Add tests `tests/test_cli_assemble_live.py`: end-to-end with seeded cache + journal returns exit 0 + valid JSON, stale cache returns exit 5 + STALE_DATA in stderr, unwired signals warning appears on stderr, sector `未分類` warning appears.

## 9. Documentation

- [ ] 9.1 Add a one-paragraph note to `docs/design-zh-TW.md` §4.7.0 (or the closest section covering the swarm input assembler) saying live providers are wired with TAIEX-only Risk-Off coverage in v1, with a forward pointer to the spec.
- [ ] 9.2 Add a row to CLAUDE.md §5 SSOT table: "Live provider error codes / freshness policy → `openspec/specs/live-providers/spec.md`".

## 10. Validation

- [ ] 10.1 Run `openspec validate live-providers --strict` and resolve any errors.
- [ ] 10.2 Run `pytest tests/ -q` and confirm 0 regressions; new tests in this change should add ~25–30 cases.
- [ ] 10.3 Smoke-test the CLI on a developer laptop with a real (non-empty) cache and journal: `oms assemble-entry-input 2330 --asof <today> --trigger-at <iso-now>`. Confirm exit 0, valid JSON, expected warnings if any signals are unwired.
- [ ] 10.4 Run `openspec status --change live-providers` and confirm `isComplete: true`.
