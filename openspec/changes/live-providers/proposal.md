## Why

Phase 2B shipped a pure swarm input assembler that depends on three protocol-based providers (`MarketSnapshotProvider`, `PortfolioSnapshotProvider`, `JournalStatsProvider`) plus five candidate technical metrics (`current_price`, `ema20_distance_pct`, `atr_14_pct`, `distance_from_52w_high_pct`, `distance_from_52w_low_pct`). Today the live implementations of those providers all raise `NotImplementedError`, and the `oms assemble-entry-input` CLI defaults the technical metrics to `0.0` — so the end-to-end Phase 3 LLM Decider input cannot be produced from real data without test fakes. Phase 3 (LLM Decider, target 2026-07-07) is blocked on this gap.

## What Changes

- Wire `LiveMarketSnapshotProvider` to read TAIEX daily bars from the existing `get_kline` cache, compute `taiex_change_pct`, evaluate `risk_off` per `workflow-cheatsheet.md §0`, and read `monthly_pnl_pct` from the trade journal.
- Wire `LivePortfolioSnapshotProvider` to read paper-broker positions (Shioaji simulation account-derived holdings via the trade journal as authoritative source) joined with sector metadata.
- Wire `LiveJournalStatsProvider` to query the trade journal SQLite directly for `recent_winrate(n)` and `consecutive_loss()`.
- Add a `candidate_snapshot` helper that derives `current_price` / `ema20_distance_pct` / `atr_14_pct` / `distance_from_52w_high_pct` / `distance_from_52w_low_pct` for `(symbol, asof)` from cached daily bars + the existing technical-indicators module.
- Standardize provider failures into typed `LiveProviderError` exceptions with classification codes (`DATA_UNAVAILABLE`, `STALE_DATA`, `UPSTREAM_ERROR`) so the CLI can map them to deterministic exit codes, mirroring the `get_kline` envelope pattern.
- Update `oms assemble-entry-input` to populate the technical-snapshot fields from `candidate_snapshot` instead of defaulting to zero, and to surface the new error codes.

Out of scope (deferred):
- `ShioajiLiveClient` for real (non-simulation) brokerage — Phase 3.5+ work.
- Real-time tick streaming / websocket subscriptions.
- The full registered `@register_tool` layer (`market_data_tool`, `portfolio_tool`, `trade_journal_tool`) — providers call data sources and SQLite directly for now; later refactor wraps them through tools.

## Capabilities

### New Capabilities

- `live-providers`: Concrete runtime implementations of the swarm-input-assembler's `MarketSnapshotProvider` / `PortfolioSnapshotProvider` / `JournalStatsProvider` protocols, plus the `candidate_snapshot` derivation helper. Defines provider error taxonomy, freshness requirements, and the contract the Phase 3 entry-input CLI relies on.

### Modified Capabilities

None. The `swarm-input-assembler` spec is unchanged — it already declares the protocols; this change supplies implementations that satisfy them.

## Impact

- **Code added**:
  - `src/ohmystock/swarm/_live_providers.py` (or split: `_live_market.py`, `_live_portfolio.py`, `_live_journal.py`) replacing the bodies of the three `Live*` stub classes in `src/ohmystock/swarm/_adapters.py`.
  - `src/ohmystock/swarm/_candidate_snapshot.py` for technical-metric derivation from cached bars.
  - `src/ohmystock/swarm/_errors.py` extended with `LiveProviderError` + classification codes.
- **Code modified**:
  - `src/ohmystock/cli/_assemble.py` — populate technical-snapshot fields, map new error codes to exit codes.
  - `src/ohmystock/swarm/__init__.py` — re-exports.
- **Dependencies**: No new external libraries. Reuses `get_kline`, `ohmystock.indicators`, trade-journal SQLite, and `ohmystock.config.Settings`.
- **Tests**: New unit tests per provider (with cache-prepared fixtures), new integration test for `oms assemble-entry-input` end-to-end without `NotImplementedError`. Existing assembler tests using fake providers stay unchanged.
- **Docs**: `docs/design-zh-TW.md` §4.7.0 (Phase 2B Swarm Input Assembler) — short note that live providers are now wired. CLAUDE.md §5 SSOT table — add row for live-providers spec if relevant.
- **Risk**: Provider failures must fail fast with typed errors so the Decider never receives silently-zeroed inputs. Freshness checks (cache age vs `asof`) are enforced or the provider raises `STALE_DATA`.
