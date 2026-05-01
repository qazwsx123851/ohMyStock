## Why

The just-shipped swarm input assembler raises `AssemblerInputError` whenever a `Phase2BCandidate` is missing SEPA fields (`rs_percentile`, `vcp_quality`, `pivot_price`). Today every candidate is missing them: `rs_percentile` is still a deferred stub (returns `status=skipped`), and there is no VCP/pivot sub-scorer at all. The assembler is therefore non-functional on real Phase 2B output. This change makes Phase 2B → entry_decision_team end-to-end usable by replacing the two SEPA-aligned stubs with real implementations and routing their evidence into the candidate's first-class SEPA fields.

## What Changes

- Replace `src/ohmystock/scoring/subscorers/deferred/rs_percentile.py` (currently `status="skipped"`) with a real **technical** sub-scorer that computes IBD-style 252-day weighted relative strength against the TWSE+OTC liquidity-filtered universe. Awards `≥65 → 3pts / ≥80 → 5pts / ≥90 → 7pts` per cheatsheet §6.3 Trend Template + §6.4 bonus tier (max 7).
- Replace `src/ohmystock/scoring/subscorers/deferred/kline_patterns.py` (currently `status="skipped"`) with a real **technical** sub-scorer `vcp_pivot` that detects VCP / cup-handle / platform patterns and emits `vcp_quality ∈ {"none","forming","textbook","breakout"}` plus `pivot_price` (or `None`) into evidence. Awards 0-8 pts (cheatsheet §6.5: VCP > cup-handle > platform > classic).
- Move file location: `subscorers/deferred/rs_percentile.py` → `subscorers/rs_percentile.py` (it's no longer deferred); same for `kline_patterns.py` (which we rename to `vcp_pivot.py` to match the cheatsheet vocabulary). The deferred package shrinks from 16 → 14 stubs.
- Wire `_engine._extract_sepa_fields` to read `rs_percentile.evidence["rs_percentile"]` and `vcp_pivot.evidence["vcp_quality"]` / `["pivot_price"]` (the function is already prepared to read these — the sub-scorers just need to start emitting them).
- Add a TWSE+OTC liquidity-filtered universe loader — minimum viable: a static seed list of `2330 / 2317 / 2454 / 3008 / 2412` (5 large-caps) for unit tests and a documented escape hatch (`set_rs_universe(symbols)`) so future production code can replace the universe without reshipping the sub-scorer.
- Update `tests/test_subscorers_layout.py`: deferred count 16 → 14.
- Add tests `tests/test_subscorer_rs_percentile.py` (real implementation) and `tests/test_subscorer_vcp_pivot.py`.

## Capabilities

### New Capabilities
- (none)

### Modified Capabilities
- `phase-2b-scoring-engine`: add two ADDED requirements documenting the real `rs_percentile` and `vcp_pivot` sub-scorer contracts (max points, evidence fields, scoring thresholds), and a MODIFIED requirement updating the deferred sub-scorer count from 16 to 14.

## Impact

- **Code**:
  - Move + rewrite: `src/ohmystock/scoring/subscorers/deferred/rs_percentile.py` → `subscorers/rs_percentile.py` (real impl).
  - Move + rewrite + rename: `src/ohmystock/scoring/subscorers/deferred/kline_patterns.py` → `subscorers/vcp_pivot.py` (real impl).
  - Update: `src/ohmystock/scoring/subscorers/__init__.py` (registers the two new modules; remove from `deferred/`).
  - Update: `src/ohmystock/scoring/subscorers/deferred/__init__.py` (drop the two moved entries).
  - Update: `src/ohmystock/scoring/_engine.py` `_extract_sepa_fields` — already reads the right evidence keys, so verify-only.
  - New: `src/ohmystock/scoring/_rs_universe.py` — static TWSE+OTC seed + `set_rs_universe(symbols)` escape hatch.
  - New: tests `tests/test_subscorer_rs_percentile.py`, `tests/test_subscorer_vcp_pivot.py`.
  - Update: `tests/test_subscorers_layout.py` (16 → 14 deferred count, registered count check).
- **Specs**: 1 modified capability (`phase-2b-scoring-engine`).
- **Data**: `rs_percentile` requires kline data for the universe symbols + the candidate; `score_watchlist` already pre-fetches per-candidate klines via `get_kline`. The universe-wide fetch is one extra call per scoring run, cached after the first.
- **No breaking changes** to existing `Phase2BCandidate` shape — SEPA fields stay Optional.
- **End-to-end unblock**: with these two sub-scorers shipped, `oms assemble-entry-input <symbol>` works on real Phase 2B output (assuming the live market/portfolio/journal providers are also wired — those remain a separate change).
- **Risks**: RS Percentile depends on a universe definition; the seed list (5 large-caps) is too small to be statistically meaningful in production but suffices for the unit tests and the assembler's contract. The `set_rs_universe` escape hatch documents the path forward.
