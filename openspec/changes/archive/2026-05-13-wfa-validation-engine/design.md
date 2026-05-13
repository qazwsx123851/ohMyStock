## Context

`backtest-engine-mvp` ships a working `run_backtest(strategy, bars_by_symbol, *, period, initial_capital, ...) -> envelope` at `src/ohmystock/backtest/engine.py:101`. `compute_metrics()` returns `{sharpe, max_drawdown, win_rate, profit_factor, …}` per `src/ohmystock/backtest/metrics.py:78`. `proposal-state-machine` exposes `transition_proposal(path, new_status, *, actor, reason=None, validation_report_path=None, merged_to_version=None) -> Path`. `available_strategies()` enumerates registered strategies via `src/ohmystock/backtest/strategy/registry.py:40`. `select_bars(conn, symbol, start, end)` loads cached bars from SQLite at `src/ohmystock/data/cache.py:75`.

Strategies in this codebase are **rule-based, not parametric** — `SmaCross.__init__(fast=5, slow=20, qty=1000)` takes kwargs that are tunable, but the underlying logic is hard-coded. So the v0 validator's "candidate" is **baseline kwargs + the proposal's `--param` overrides**, NOT a learned model. That makes "walk-forward analysis" here a misnomer in the classical sense — there is no in-sample *fitting*, only in-sample *measurement*. We still compute the IS/OOS metric gap, but as a **rule-stability check**, not an over-fitting penalty in the parametric ML sense. Honest framing matters: see Decision D3.

## Goals / Non-Goals

**Goals:**
- Provide an objective gate between `validating` and `approved` proposal states, mechanizing what is currently a manual rubber-stamp.
- Pin three numeric pass conditions (Sharpe gap, baseline-relative Sharpe degradation, baseline-relative MDD degradation) directly to the cheatsheet §10 + §16.3 text so the threshold definitions don't drift.
- Keep the validator **fully deterministic** (no LLM, no network) so the same inputs reproducibly map to the same verdict.
- Write a self-describing `<slug>.validation.json` that contains everything needed for a human to audit the verdict without re-running the validator (per-window metrics, aggregates, deltas, thresholds, failures).
- Reuse `run_backtest()` verbatim; do NOT re-implement equity curves, fills, or metrics.

**Non-Goals:**
- Robust (±10% parameter perturbation) check — §16.3 row 2; deferred change.
- Golden-sample regression (`reviews/_golden/`) — §16.3 row 3 + v3-decisions #14; deferred until ≥6 months production data.
- LLM that interprets `diff_draft` and emits param overrides — keeps v0 deterministic; humans bridge intent → flags.
- Pure-rule strategies whose changes can't be expressed as kwargs (e.g. K-pattern detector edits, prompt edits) — those run via §16.0's separate prompt-eval lane.
- HTTP endpoint, EventBus event, web-admin UI button, scheduler — all explicitly deferred.
- Multi-symbol portfolio backtests with cross-symbol position sizing — the v0 validator runs one `bars_by_symbol` dict per backtest call exactly as `run_backtest` already supports; no new aggregation rules.

## Decisions

### D1: CLI-only trigger; human supplies `--param` flags
Chosen over LLM-driven diff parsing.
- **Why:** The proposal markdown's `diff_draft` is freeform markdown (`- VCP 量能 ≥ 1.5× …` / `+ VCP 量能 ≥ 1.3×`). Programmatic extraction is fragile and would need an LLM, which violates the "fully deterministic" goal. The human reading the proposal knows which strategy + kwarg the diff maps to and can type `--strategy vcp --param volume_threshold=1.3`.
- **Alternative considered:** structured frontmatter field `param_overrides: {volume_threshold: 1.3}` enforced on every proposal. Rejected — would break every existing proposal markdown + force the proposer LLM to emit valid Python kwargs, which is the brittle thing we're avoiding.
- **Future:** when an LLM-driven interpreter ships, it'd emit the same `--param` strings the human types today, so this change is forward-compatible.

### D2: Sibling-file validation report (`proposals/<slug>.validation.json`)
Lives directly next to `proposals/<slug>.md`, NOT in `proposals/<slug>/validation.json` or a separate dir.
- **Why:** `proposal-state-machine` requires the caller to pass `validation_report_path` to the `validating → approved` edge. Sibling-file convention means the markdown frontmatter `validation_report_path: <slug>.validation.json` is a stable relative path that resolves correctly even after the markdown moves to `PENDING_REVIEW/`.
- **Caveat:** `transition_proposal` itself does NOT move the report file; it only moves the markdown. **The validator MUST place the report at the proposal's *current* location BEFORE calling `transition_proposal`**, then move the report after the transition completes so it remains a sibling.
- **Mitigation:** after `transition_proposal()` returns the new path, the validator runs `report_path.rename(new_path.parent / report_path.name)` so markdown and report stay co-located.

### D3: Walk-forward windows = rolling, non-overlapping OOS
`N = 5` windows, `in_sample_ratio = 0.7` by default. Total period split into 5 equal-length **chunks**; for each chunk:
- In-sample = `0.7 × chunk_length` days at the start
- Out-of-sample = the remaining `0.3 × chunk_length` days
- Adjacent chunks are temporally disjoint (no overlap between OOS windows; IS windows from window N+1 do NOT include window N's OOS — only chunk N's own IS prefix).

Aggregate OOS metric = pooled equity curve across all 5 OOS windows (concatenated chronologically, normalised to a single equity series per window starting from `initial_capital`, then arithmetic-mean of per-window Sharpe + max-abs of per-window `|max_drawdown|`).

- **Why this layout:** Avoids the "expanding window" complexity of classical WFA (mostly meaningful for parametric models being re-fit). Disjoint chunks with fixed IS/OOS proportion are easier to explain, reproduce, and pin in tests.
- **IS/OOS Sharpe gap** is computed per window as `abs(IS_sharpe - OOS_sharpe) / max(abs(IS_sharpe), eps)`, then **averaged** across the 5 windows for the threshold check. Per-window values land in the report so a human can spot a single bad window.

### D4: Three numeric pass conditions, evaluated in declared order
Failures accumulate (not short-circuit) so the report lists every failed threshold, not just the first:
1. `mean(per_window candidate IS-OOS Sharpe gap) < 0.30` → "over-fitting check"
2. `candidate aggregate OOS Sharpe ≥ baseline aggregate OOS Sharpe × 0.95` → "performance degradation check"
3. `abs(candidate aggregate OOS max_drawdown) ≤ abs(baseline aggregate OOS max_drawdown) × 1.20` → "drawdown degradation check"
- `verdict = "pass"` iff all three OK. Otherwise `verdict = "fail"`; `failures: list[str]` lists each failing line in declared order with the actual + threshold numbers.

### D5: Bars loader is injected (`market_data_loader` parameter)
`run_validation(...)` takes `market_data_loader: Callable[[str, str, str], list[BarRow]]` (signature `(symbol, start, end) -> [BarRow]`). The CLI builds the default factory from `get_connection() + select_bars`. Tests inject a synthetic in-memory loader.
- **Why:** keeps the library importable in tests without spinning up SQLite/disposition cache/fetchers, mirroring the `_REVIEWS_ROOT_FACTORY` test-seam pattern shipped in `admin-reviews-endpoints`.

### D6: CLI exit codes
- `0` — verdict=pass, state transitioned, report written
- `1` — verdict=fail, state transitioned to rejected, report written (NOT a CLI error; the validator did its job — the proposal failed the gate). User scripts can grep `verdict` from the JSON if they need to branch.
- `2` — input error (unknown strategy, period inverted, bars missing, proposal status != "validating", proposal file not found, `WfaValidationError` of any flavor). The proposal state is NOT changed.
- `--dry-run` always exits `0` (or `2` on input error); the run still computes metrics and prints the would-be verdict to stdout.

### D7: Report file write is atomic
`tempfile.NamedTemporaryFile(dir=proposal_path.parent, suffix=".validation.json.tmp")` + `flush` + `os.fsync` + `os.replace`. Same pattern as `proposal-state-machine`'s markdown writer. A mid-write crash leaves either the old file or no file — never a half-written `.validation.json`.

### D8: Frontmatter `validation_report_path` value is always relative, forward-slash
`f"{slug}.validation.json"` (just the filename, no directory). After `validating → approved` move, the report file ends up at `PENDING_REVIEW/<slug>.validation.json` AND the markdown's frontmatter still says `validation_report_path: <slug>.validation.json` — both files are siblings so the relative path resolves correctly.

## Risks / Trade-offs

- **[Risk] Aggregate OOS Sharpe is computed from pooled per-window equity, not a single continuous backtest** → portfolio state (`Portfolio` cash, settlement T+2 lots) doesn't carry across windows. **Mitigation:** each window starts fresh with `initial_capital` — standard WFA convention; the report's `windows[]` array exposes per-window metrics so it's auditable. Document in design + report header.
- **[Risk] Strategies that don't accept the requested `--param` kwarg raise TypeError at construction** → CLI catches `TypeError` from `strategy_cls(**overrides)` and exits 2 with `unknown_param: <key>` so the user fixes their flag. **Mitigation:** explicit guard in the CLI handler before calling the validator library.
- **[Risk] Tiny period (< 5 trading days per window) produces zero-trade backtests that yield `sharpe=0, max_drawdown=0`** which pass thresholds trivially. **Mitigation:** library refuses `(period_end - period_start).days < wfa_windows * 5` with `WfaValidationError("period_too_short")`; CLI surfaces as exit 2.
- **[Risk] Universe symbols missing from `bars_daily` cache** → bars-fetch returns empty for one symbol but not others; `run_backtest` would error. **Mitigation:** validator pre-checks every symbol's bars cover the period (>= 1 bar in each window) before invoking the engine; on miss raises `WfaValidationError("missing_bars: <symbol>")` → exit 2.
- **[Trade-off] No robust check (±10% perturbation) in v0** → a proposal that passes WFA but is fragile to a 1% threshold tweak slips through. **Accepted** for v0 because robust check doubles the runtime + report complexity and the human PR review still gates the final merge.
- **[Trade-off] No golden-sample regression** → a proposal that improves backtest metrics on the chosen universe but breaks behaviour on TWSE staples (0050/2330/0056) slips through. **Accepted** because `_golden/` set is empty in v0 per v3-decisions #14.

## Migration Plan

No schema migration. Implementation order:
1. `validation/wfa.py` library: dataclasses + pure helpers (window splitter, aggregator, threshold evaluator) — testable in isolation.
2. `validation/wfa.py` `run_validation()` orchestrator: wires baseline + candidate runs, builds report, calls `transition_proposal`.
3. `cli/_validate_proposal.py`: typer integration + exit codes.
4. CLI registration in `cli/__init__.py`.
5. Tests (library unit, CLI integration).

Rollback: revert commit; no schema, no persistent state outside report JSON files (which are sibling-of-proposal artifacts the user can `rm` if they want to invalidate).

## Open Questions

- **Q:** Should `validation.json` include the strategy's full kwargs (baseline + override) for reproducibility, or only the overrides? **Tentative answer:** both — `param_overrides` (just what differed) and `effective_kwargs` (full applied kwargs after merge). Reproducibility wins over compactness.
- **Q:** What's the canonical `--universe` default? **Tentative answer:** `2330,0050,2317` (TSMC, 0050 ETF, Hon Hai) — TWSE staples with the deepest historical bar cache. Can be overridden via CLI for any specific proposal.

Neither blocks implementation; both have defensible defaults documented above. Re-open if implementation reveals a clearer answer.
