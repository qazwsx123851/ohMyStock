## ADDED Requirements

### Requirement: LiveProviderError taxonomy

The system SHALL provide a `LiveProviderError` exception class importable as `from ohmystock.swarm import LiveProviderError` with a string `code` attribute drawn from the closed set `{"DATA_UNAVAILABLE", "STALE_DATA", "UPSTREAM_ERROR", "AUTH_FAILED"}`. Every live provider in this capability SHALL raise `LiveProviderError` (or a subclass) on failure — bare `RuntimeError` / `ValueError` MUST NOT escape the provider. The CLI `oms assemble-entry-input` SHALL map these codes to exit codes: `DATA_UNAVAILABLE` → 4, `STALE_DATA` → 5, `UPSTREAM_ERROR` → 6, `AUTH_FAILED` → 7. Existing exit codes `1` (generic), `2` (`AssemblerInputError`), `3` (legacy `NotImplementedError` — kept for backward compatibility but no longer reachable) are preserved.

#### Scenario: code attribute exposed
- **WHEN** a `LiveProviderError(code="STALE_DATA", message="taiex bars older than 5 business days")` is raised and caught
- **THEN** `caught.code == "STALE_DATA"` and `str(caught)` contains the message

#### Scenario: CLI maps STALE_DATA to exit 5
- **WHEN** `oms assemble-entry-input` is invoked and the live market provider raises `LiveProviderError(code="STALE_DATA")`
- **THEN** the CLI exits with status 5 and stderr contains `"STALE_DATA"`

#### Scenario: Unknown code is rejected at construction
- **WHEN** `LiveProviderError(code="GREMLIN", message="oops")` is constructed
- **THEN** `ValueError` is raised referencing the closed set of valid codes

---

### Requirement: LiveMarketSnapshotProvider returns TAIEX-derived MarketSnapshot

The system SHALL replace `LiveMarketSnapshotProvider.get()` (in `ohmystock.swarm._adapters`) with an implementation that, given a constructor argument `asof: str` (YYYY-MM-DD), returns a `MarketSnapshot` populated as follows:
- `taiex_close`: closing price of the TAIEX daily bar with `ts == asof`, or the most recent bar with `ts <= asof` if no exact match within 5 business days.
- `taiex_change_pct`: percent change from the previous trading-day close, computed from the same cached bars.
- `risk_off`: boolean evaluating Risk-Off per `docs/workflow-cheatsheet.md §0.1` using **at minimum** the TAIEX-vs-MA60 condition. Conditions whose data is not yet wired (SPY 5-day return, VIX, TWD/USD, TAIFEX foreign-investor net-short) MUST be treated as `unknown` and MUST NOT cause `risk_off=True` on their own.
- `monthly_pnl_pct`: month-to-date realized P&L from the trade journal as of `asof`, expressed as a percentage of starting equity.

If TAIEX bars are absent from the cache and `get_kline` cannot fetch them, the provider SHALL raise `LiveProviderError(code="DATA_UNAVAILABLE")`. If the most recent cached TAIEX bar's `ts` is more than 5 business days older than `asof`, the provider SHALL raise `LiveProviderError(code="STALE_DATA")`.

#### Scenario: TAIEX present, risk-on returned
- **WHEN** the cache contains 200 TAIEX daily bars ending on `asof=2026-04-30`, the close is above the 60-day MA, and the journal shows `monthly_pnl_pct=+1.2`
- **THEN** `LiveMarketSnapshotProvider(asof="2026-04-30").get()` returns a `MarketSnapshot` with `risk_off=False`, `taiex_close == bar[asof].close`, and `monthly_pnl_pct == 1.2`

#### Scenario: TAIEX below MA60 triggers risk_off
- **WHEN** TAIEX cached bars show close < MA60 on `asof` and MA60 is flat-or-falling
- **THEN** `risk_off == True` in the returned snapshot

#### Scenario: Stale cache raises STALE_DATA
- **WHEN** the most recent cached TAIEX bar's `ts` is `2026-04-15` and `asof="2026-04-30"` (more than 5 business days older)
- **THEN** `get()` raises `LiveProviderError` with `code == "STALE_DATA"`

#### Scenario: TAIEX cache miss with adapters disabled raises DATA_UNAVAILABLE
- **WHEN** the cache has no TAIEX bars and `get_kline` returns an error envelope with `code="DATA_UNAVAILABLE"`
- **THEN** the provider raises `LiveProviderError` with `code == "DATA_UNAVAILABLE"`

#### Scenario: Unknown Risk-Off signals do not trigger risk_off alone
- **WHEN** TAIEX is risk-on (above MA60) and SPY/VIX/FX/TAIFEX inputs are not wired
- **THEN** `risk_off == False` (unknown ≠ triggered)

---

### Requirement: LivePortfolioSnapshotProvider reconstructs positions from journal

The system SHALL replace `LivePortfolioSnapshotProvider.get()` with an implementation that reads the trade journal SQLite (`journal_entries` table per `trade-journal-schema` capability) up to `asof` and returns a `PortfolioSnapshot` containing one `PortfolioPosition(symbol, sector, exposure_pct)` per currently-open position. "Currently open" means an unmatched `kind="entry"` event where no later `kind="exit"` event exists for the same symbol (FIFO matching by `created_at`). `exposure_pct` SHALL be `(position_market_value / total_account_equity) * 100` where market value uses the most recent cached daily close `<= asof`. `total_exposure_pct` SHALL equal the sum of position `exposure_pct`. Sector SHALL be looked up from the screener universe sector index; if missing, sector SHALL be the literal string `"未分類"`.

If the journal database is unreachable, the provider SHALL raise `LiveProviderError(code="DATA_UNAVAILABLE")`.

#### Scenario: One open position
- **WHEN** the journal has one `entry` event for `2330` on `2026-04-20` at price `780` for 1000 shares, no matching exit, account equity is `NT$1,000,000`, and the cached close on `asof=2026-04-30` is `820`
- **THEN** `LivePortfolioSnapshotProvider(asof="2026-04-30").get()` returns a snapshot with one position `(symbol="2330", exposure_pct=82.0, sector=<lookup>)` and `total_exposure_pct == 82.0`

#### Scenario: Closed position is excluded
- **WHEN** the journal has an `entry` for `2454` and a later `exit` for the same symbol with matching shares
- **THEN** the position is NOT in the returned snapshot

#### Scenario: Symbol missing from sector lookup
- **WHEN** an open position's symbol is not in the screener universe sector index
- **THEN** its `sector == "未分類"` (provider does not raise)

#### Scenario: Journal DB missing raises DATA_UNAVAILABLE
- **WHEN** the journal SQLite file does not exist or fails to open
- **THEN** the provider raises `LiveProviderError(code="DATA_UNAVAILABLE")`

---

### Requirement: LiveJournalStatsProvider reads winrate and consecutive-loss from journal

The system SHALL replace `LiveJournalStatsProvider.recent_winrate(n)` and `consecutive_loss()` with implementations that query the trade journal SQLite. `recent_winrate(n)` SHALL return the fraction (0.0–1.0) of profitable closed trades among the most recent `n` closed trades (`kind="exit"` events) ordered by `created_at` descending, where a trade is profitable when its realized P&L is `> 0`. If fewer than `n` closed trades exist, the method SHALL compute over what exists; if zero closed trades exist, it SHALL return `0.0`. `consecutive_loss()` SHALL return the number of most-recent consecutive losing closed trades (P&L `<= 0`); the streak ends at the first profitable trade or when no more closed trades remain.

The provider SHALL accept an `asof: str` constructor argument and consider only closed trades whose `created_at <= asof`. Database errors SHALL surface as `LiveProviderError(code="DATA_UNAVAILABLE")`.

#### Scenario: 12 of last 20 closed trades profitable
- **WHEN** the journal has 25 closed trades with `created_at <= asof` and the most recent 20 contain 12 with P&L > 0
- **THEN** `recent_winrate(20) == 0.6`

#### Scenario: Fewer than n closed trades
- **WHEN** the journal has 7 closed trades total with `created_at <= asof`, of which 4 are profitable
- **THEN** `recent_winrate(20) == 4/7` (computed over all 7)

#### Scenario: No closed trades returns zero winrate
- **WHEN** the journal has zero closed trades with `created_at <= asof`
- **THEN** `recent_winrate(20) == 0.0` and `consecutive_loss() == 0`

#### Scenario: Three consecutive losses then a win
- **WHEN** the most recent four closed trades by `created_at` desc have P&L `[-50, -200, -100, +300]`
- **THEN** `consecutive_loss() == 3`

#### Scenario: All recent trades losing
- **WHEN** the most recent five closed trades all have P&L `< 0`
- **THEN** `consecutive_loss() >= 5`

---

### Requirement: live_candidate_snapshot helper derives the five technical fields

The system SHALL provide `ohmystock.swarm.live_candidate_snapshot(symbol: str, asof: str) -> CandidateLiveSnapshot` returning a frozen dataclass with five floats: `current_price`, `ema20_distance_pct`, `atr_14_pct`, `distance_from_52w_high_pct`, `distance_from_52w_low_pct`. The function SHALL read daily bars via `get_kline` (using cache; fetching missing bars within the call) and compute each field from the bars: `current_price` = close on `asof` (or most recent bar with `ts <= asof`); `ema20_distance_pct` = `(close - ema20) / ema20 * 100`; `atr_14_pct` = `(atr14 / close) * 100`; `distance_from_52w_high_pct` = `(close / max_close_252) - 1) * 100`; `distance_from_52w_low_pct` = `(close / min_close_252 - 1) * 100`. The 52-week window MUST be the most recent 252 trading days ending at `asof` (inclusive). If fewer than 252 bars exist, the function SHALL compute over what exists and SHALL NOT pad with zeros. If `get_kline` returns an error envelope, the function SHALL raise `LiveProviderError` with the same code.

#### Scenario: All five fields populated
- **WHEN** `live_candidate_snapshot("2330", "2026-04-30")` is called and the cache has 300 bars ending on 2026-04-30
- **THEN** the returned dataclass has `current_price > 0` and the four percentages are finite floats (no NaN, no zero unless the underlying math produces it)

#### Scenario: get_kline error propagates with same code
- **WHEN** `get_kline` returns `{"ok": False, "error": {"code": "STALE_DATA", ...}}` (or any non-OK)
- **THEN** `live_candidate_snapshot` raises `LiveProviderError` with `code == "STALE_DATA"`

#### Scenario: Frozen dataclass cannot be mutated
- **WHEN** a caller attempts `snap.current_price = 999.0`
- **THEN** `dataclasses.FrozenInstanceError` is raised

---

### Requirement: oms assemble-entry-input wires live providers and surfaces error codes

The CLI command `oms assemble-entry-input <symbol> --asof <YYYY-MM-DD> --trigger-at <iso>` SHALL, when run without test-injected providers, populate `EntryDecisionInput` end-to-end from real cached data: the three live providers and `live_candidate_snapshot` SHALL be invoked. The five technical-metric defaults previously hard-coded to `0.0` in `_run_assemble` SHALL be removed; if the helper raises, the CLI MUST exit with the corresponding `LiveProviderError` exit code. On success, the JSON output remains byte-identical to the existing assembler output for matching inputs.

The CLI SHALL emit a single warning line on stderr (prefixed `warning:`) when any of the following occur:
- An open position has `sector == "未分類"`.
- `LiveMarketSnapshotProvider` returns `risk_off=False` while one or more Risk-Off signals are `unknown` (TAIEX-only mode).

Warnings SHALL NOT change the exit code.

#### Scenario: End-to-end run with seeded cache and journal
- **WHEN** the bars cache contains TAIEX and 2330 daily bars ending on 2026-04-30, the journal has one open position in 2330 with `monthly_pnl_pct == +1.2`, and the user runs `oms assemble-entry-input 2330 --asof 2026-04-30 --trigger-at 2026-04-30T14:30:00+08:00`
- **THEN** the CLI exits 0
- **AND** stdout is parseable JSON satisfying `EntryDecisionInput.model_validate(...)`
- **AND** `decision_id == "dec_2026-04-30T14-30-00_2330"`

#### Scenario: Stale cache surfaces exit code 5
- **WHEN** TAIEX cached bars are older than 5 business days relative to `asof`
- **THEN** the CLI exits with status 5 and stderr contains `STALE_DATA`

#### Scenario: Unwired Risk-Off signals emit a warning but do not change exit
- **WHEN** the run succeeds with `risk_off=False` and SPY/VIX inputs are not yet wired
- **THEN** stderr contains a line beginning with `warning:` mentioning unwired Risk-Off signals
- **AND** exit code is `0`
