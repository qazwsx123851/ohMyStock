## Context

The Phase 2B Swarm Input Assembler (archived 2026-05-01) is a pure builder. It declares three Protocol-based dependencies in `src/ohmystock/swarm/_adapters.py` — `MarketSnapshotProvider`, `PortfolioSnapshotProvider`, `JournalStatsProvider` — and a `Live*Provider` stub for each. The stubs raise `NotImplementedError` with messages pointing at upstream tools that "land in later phases" (`market_data_tool.get_index('TAIEX')`, `portfolio_tool.get_positions()`, `trade_journal_tool.query`).

The CLI `oms assemble-entry-input` (`src/ohmystock/cli/_assemble.py`) defaults the five candidate technical metrics (`current_price`, `ema20_distance_pct`, `atr_14_pct`, `distance_from_52w_high_pct`, `distance_from_52w_low_pct`) to `0.0` when no fakes are injected. End-to-end runs from real data are therefore impossible today: either `NotImplementedError` fires or zeroed metrics flow into the assembler.

Existing surfaces this design leans on (no rewrites):
- `ohmystock.data.market_data.get_kline()` — daily-bar fetch with FinMind→twstock→yfinance fallback and SQLite cache (`bars_daily`).
- `ohmystock.indicators.*` — EMA / ATR primitives on daily bars (Phase 1 spec `technical-indicators`).
- Trade journal SQLite (`journal_entries` table) per spec `trade-journal-schema` — authoritative source of entry/exit events.
- `ohmystock.config.Settings` — DB paths, FinMind tokens, Shioaji credentials.

Phase 3 (LLM Decider, target 2026-07-07) blocks on this gap. Phase 4 admin UI also wants the same providers behind its `/dashboard` endpoint, so the design avoids CLI-only assumptions.

## Goals / Non-Goals

**Goals:**
- Make `oms assemble-entry-input <symbol> --asof <date> --trigger-at <iso>` produce a valid `EntryDecisionInput` from real cached data without any test fakes.
- Standardize provider failures into `LiveProviderError` with classification codes that the CLI maps to deterministic exit codes — same envelope discipline as `get_kline`.
- Keep the assembler pure: providers do I/O, the assembler does not.
- Provide a single import surface (`from ohmystock.swarm import LiveMarketSnapshotProvider, …`) that already works in CLI imports today, so the CLI change is a one-liner-per-provider, not a refactor.

**Non-Goals:**
- Building the registered `@register_tool` layer (`market_data_tool`, `portfolio_tool`, `trade_journal_tool`). When that layer lands later, providers refactor to wrap tools — not now.
- `ShioajiLiveClient` for real (CA-credentialed) brokerage — Phase 3.5+ work, gated by safety §2.9.
- Real-time tick streaming, websocket subscriptions, or sub-daily quotes. The Decider operates on daily-resolution snapshots at the trigger timestamp.
- Sector mapping authority. This change consumes whatever sector source already exists (FinMind `TaiwanStockInfo` snapshot or screener static list) — it does not redefine the canonical mapping.
- Backfilling historical Risk-Off flags. The provider reports Risk-Off **as of** the asof date using available signals; a future change can extend coverage.

## Decisions

### Decision 1: Providers call data sources directly, not through `@register_tool`

The `_adapters.py` docstrings imply providers should wrap `market_data_tool.get_index()`, `portfolio_tool.get_positions()`, `trade_journal_tool.query()`. Those tool wrappers are Phase 3 work and would expand this change beyond its purpose.

**Choice**: providers import `get_kline`, `ohmystock.indicators`, and a new `ohmystock.journal.repository` (thin SQLite query helper) directly. When the registered-tool layer lands, providers refactor to delegate — no spec change required, since the spec defines provider contracts, not their internal call graph.

**Alternatives considered**:
- *Build the tool layer in this change*: rejected — doubles the scope and couples this work to the registered-tool decoration pattern, which is still being designed.
- *Inline the SQLite queries inside `_live_*.py`*: rejected — query logic is reusable by the future trade-journal tool and the Phase 4 admin dashboard. Putting it in `ohmystock.journal.repository` lets both consume it.

### Decision 2: Risk-Off scope = TAIEX-only conditions for v1

`workflow-cheatsheet.md §0.1` lists five Risk-Off conditions: TAIEX vs MA60, SPY 5-day return, VIX, TWD/USD, and foreign-investor TAIFEX net-short streak. Of these, only TAIEX is fetchable from existing infrastructure (`get_kline("TAIEX")` once we confirm the symbol code, fallback to FinMind `TaiwanStockPriceTick` for the index).

**Choice**: `LiveMarketSnapshotProvider` evaluates the **TAIEX MA60 condition** plus `monthly_pnl_pct` from the journal (which gates §0.3 monthly circuit-breaker). For the four conditions whose data is not yet wired, the provider records them as `unknown` in a `risk_off_diagnostics` debug field but **does not** treat unknown as triggered. `risk_off=True` requires at least one positively-evaluated condition firing.

**Alternatives considered**:
- *Conservatively treat unknown signals as triggered*: rejected — would put the system in permanent Risk-Off and prevent any Phase 3 testing.
- *Block this change on wiring SPY/VIX/FX/TAIFEX first*: rejected — those are independent data-source projects; coupling them here delays Phase 3.

The decision is honest: the provider is allowed to under-flag Risk-Off in v1, and that limitation surfaces explicitly via diagnostics, not silently. A follow-up change can extend coverage as each data source comes online.

### Decision 3: Portfolio source = Trade Journal SQLite (reconstructed positions)

Two candidate sources exist for "what do I currently hold":
- Shioaji simulation `list_positions()` (live broker state)
- Trade journal `journal_entries` (event sourced: entry events minus matched exit events)

**Choice**: Trade journal. Reasons: (a) journal is already the SSOT for event records and is queried by Phase 5 review, so positions are deterministic from it; (b) Shioaji simulation can desync from journal across restarts; (c) journal is purely local — no broker login required for `oms assemble-entry-input` to run; (d) backtests and replays already use journal-derived state, so the live path matches.

When `ShioajiLiveClient` lands in Phase 3.5+, a reconciliation check between journal and broker state can be added — that is a separate spec concern.

**Sector resolution**: positions are joined against a static sector lookup (`src/ohmystock/screener/universe.py`'s sector index, populated from FinMind `TaiwanStockInfo` snapshot). If a held symbol is missing from the lookup, the provider records `sector="未分類"` rather than failing — keeps the assembler running while the universe table is updated separately.

### Decision 4: Freshness policy — fail loud, not silent

The assembler's `asof` parameter says "build inputs as of this date". A live provider must ensure the data it returns matches that date or falls within an acceptable window.

**Choice**:
- For TAIEX bars: the most recent cached bar's `ts` MUST be `>= asof - 5 business days`. If older, raise `LiveProviderError(code="STALE_DATA")`.
- For journal: stats are computed over the window `(asof - N_days, asof]`. No staleness check needed — journal queries are by date range.
- For portfolio: positions are reconstructed by replaying journal events with `created_at <= asof`. Always self-consistent.

**Why fail loud**: a silent zero or yesterday's value flowing into the Decider's prompt is exactly the failure mode the safety §2.9 breaker tries to guard against. Raise early; let the CLI exit with a non-zero code and a recognizable error string.

### Decision 5: Replace stub bodies in `_adapters.py`, do not move classes

The `_assemble.py` CLI imports `LiveMarketSnapshotProvider` etc. directly from `ohmystock.swarm`. Tests import the protocols. Moving the classes elsewhere ripples through 5+ files.

**Choice**: keep the class names and locations. Replace each `def get(self): raise NotImplementedError(...)` body with the wired implementation. Add a new file `_live_internals.py` (or split into `_live_market.py` / `_live_portfolio.py` / `_live_journal.py`) that the methods call into — keeps `_adapters.py` short and the implementation testable independently of the protocol shell.

**Alternative considered**: rename to `_stubs.py` and create a new `_live_*.py`. Rejected — the public import path is already cited in the CLI's `error: live provider not wired` message and in the assembler's docstring.

### Decision 6: `candidate_snapshot` is a separate helper, not a provider

The five technical metrics (`current_price`, `ema20_distance_pct`, `atr_14_pct`, `distance_from_52w_high_pct`, `distance_from_52w_low_pct`) are per-candidate, not global like `MarketSnapshot`. They follow a different shape: the assembler accepts them as keyword floats, not via a Protocol object.

**Choice**: add `ohmystock.swarm.live_candidate_snapshot(symbol, asof) -> CandidateLiveSnapshot` returning a small dataclass with the five fields. The CLI calls it once per candidate. The assembler signature stays unchanged; the dataclass is unpacked into the existing kwargs.

This avoids inventing a "CandidateProvider" Protocol that would have only one production caller.

## Risks / Trade-offs

- [Risk] **TAIEX symbol code mismatch across adapters** → Mitigation: normalize at the provider boundary. FinMind uses `TAIEX`, twstock uses `TWII`, yfinance uses `^TWII`. Encapsulate the mapping inside the provider so callers always pass `TAIEX`.
- [Risk] **Journal contains entry events for closed positions if exit events are missing** → Mitigation: position reconstruction matches entry to exit by `(symbol, FIFO)`. Unmatched entries older than 90 days are flagged in a diagnostics field; the test suite includes a fixture exercising this.
- [Risk] **Underestimating Risk-Off because four of five signals are not wired** → Mitigation (1): provider returns `risk_off_diagnostics` with `unknown` markers visible in admin UI; (2) the design tracks "Risk-Off coverage extension" as an explicit follow-up change; (3) Phase 3 Decider prompt is aware that v1 coverage is partial and is conservative on borderline cases.
- [Risk] **Sector lookup gaps cause `same_sector_count` to under-report** → Mitigation: `LivePortfolioSnapshotProvider` records the count of `未分類` positions; if > 0, the CLI emits a stderr warning and the admin dashboard surfaces it.
- [Trade-off] **No tests against real network** — provider tests use the cache (pre-seeded) and SQLite (in-memory). End-to-end network tests are out of scope; the existing `get_kline` integration tests already cover the upstream adapters. We accept that the first time a real FinMind call happens through this path will be on a live machine.
- [Trade-off] **Reusing journal for portfolio means no minute-by-minute sync with Shioaji**. For Phase 3 batch decisions this is fine; tick-level sync is a Phase 3.5+ concern.

## Migration Plan

This is additive — no migration needed. Steps to land:

1. Add `ohmystock.journal.repository` query helpers (read-only).
2. Add `ohmystock.swarm.live_internals` (or per-provider modules) with the implementations.
3. Replace stub bodies in `_adapters.py`. Update docstrings.
4. Add `live_candidate_snapshot` and re-export from `ohmystock.swarm`.
5. Update `_assemble.py` to call `live_candidate_snapshot` and remove the `0.0` defaults.
6. Tests + spec compliance verification (`openspec validate live-providers --strict`).

Rollback: revert the diff. Stubs raise `NotImplementedError` again, CLI still produces the same `error: live provider not wired: …` message it does today. No DB schema changes, no config changes.

## Open Questions

- **TAIEX cache key**: should `bars_daily` accept the symbol `TAIEX` directly, or should a separate `index_bars_daily` table exist? Existing `bars_daily.symbol` validation requires 4–6 digits; this needs a tiny relaxation or a dedicated table. **Default**: relax to allow alphabetic index codes (`TAIEX`, `OTC`); the validator already lives in one place.
- **`monthly_pnl_pct` definition for partial month**: month-to-date as of `asof`, or rolling 30-day window? Cheatsheet §0.3 says "當月累積 P&L" → month-to-date. Confirmed default unless reviewer disagrees.
- **`JournalStatsProvider.recent_winrate(n)` window semantics**: last `n` *closed* trades (exit events) or last `n` *entry events* including open ones? Last `n` closed trades — open positions have no realized P&L. Confirmed default.
