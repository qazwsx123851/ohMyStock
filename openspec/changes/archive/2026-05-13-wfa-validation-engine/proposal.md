## Why

The Phase 5 self-improvement loop is now mechanizable end-to-end **except for the validation step**: `proposal-state-machine` accepts `transition_proposal(path, "approved", validation_report_path=...)` but **nothing actually generates the report** — the path is a human-typed string. That makes `validating → approved` a manual rubber-stamp, which is exactly what the cheatsheet §16.3 gate exists to prevent (over-fitted proposals slipping into the cheatsheet without an objective check). This change adds the missing gate: a CLI runner that takes a `validating` proposal, runs walk-forward analysis on the affected strategy with the proposal's parameter overrides, writes a `validation.json` report, and transitions the proposal state based on pass/fail.

## What Changes

- **新增 capability** `wfa-validation-engine`:
  - **CLI** — `uv run ohmystock validate-proposal <slug>` runs the full validator. Required flags: `--strategy <name>` (from `available_strategies()` registry), `--period from=YYYY-MM-DD,to=YYYY-MM-DD`, plus repeatable `--param key=value` to express the proposal's diff_draft as a kwargs override on the strategy class. Optional: `--wfa-windows N` (default 5), `--in-sample-ratio R` (default 0.7), `--universe sym1,sym2,…` (default `2330,0050,2317`), `--initial-capital N` (default `Settings().starting_equity_twd`), `--dry-run` (skip state transition + JSON write).
  - **Library** — `src/ohmystock/validation/wfa.py`:
    - `WfaWindow` dataclass: `{in_sample: {from,to}, out_of_sample: {from,to}, is_metrics: {...}, oos_metrics: {...}}`
    - `ValidationReport` dataclass: `{proposal_id, slug, validated_at, strategy, period, param_overrides, universe, wfa_windows: [...], baseline_oos_aggregate: {...}, candidate_oos_aggregate: {...}, candidate_is_oos_sharpe_gap_pct: float, deltas: {sharpe,max_drawdown,win_rate}, thresholds: {...}, verdict, failures: [str]}`
    - `run_validation(proposal_path, *, strategy_name, period, param_overrides, universe, wfa_windows=5, in_sample_ratio=0.7, initial_capital, market_data_loader, dry_run=False) -> ValidationReport`
    - `WfaValidationError` exception for input mis-shape (unknown strategy, period inverted, universe empty, bars missing for symbol).
  - **Pass/fail thresholds** (workflow-cheatsheet.md §10 + §16.3, v0 = WFA-only subset):
    1. Candidate **IS-OOS Sharpe gap** `< 30%` (`abs(IS - OOS) / max(abs(IS), eps) < 0.30`) — over-fitting guard from §16.3.
    2. Candidate **OOS aggregate Sharpe ≥ baseline OOS aggregate Sharpe × 0.95** — §10 "不退化超過 5%".
    3. Candidate **OOS aggregate `|max_drawdown|` ≤ baseline OOS aggregate `|max_drawdown|` × 1.20** — §16.3 "MDD 變化不能比原版差超過 +20% 相對值".
    - Failing any one of (1)/(2)/(3) → `verdict = "fail"`; all three pass → `verdict = "pass"`.
  - **Report sink** — writes `proposals/<slug>.validation.json` (lives **next to** the proposal markdown, not under a sub-dir; sibling-file convention so the markdown's `validation_report_path: <slug>.validation.json` frontmatter resolves trivially). Atomic write via `tempfile.NamedTemporaryFile + os.replace`. `--dry-run` skips this write.
  - **State transition** — non-dry-run runs end with:
    - `verdict == "pass"` → `transition_proposal(path, "approved", actor="wfa-validator", validation_report_path=Path("<slug>.validation.json"))`
    - `verdict == "fail"` → `transition_proposal(path, "rejected", actor="wfa-validator", reason=<one-line summary of which threshold failed>)`
    - the CLI rejects proposals whose current `status != "validating"` with exit code 2 and a clear message (validator does NOT auto-advance `pending → validating`; that intentional step stays human).

- **Intentionally deferred** (NOT in this change, separately tracked):
  - Robust-check (±10% parameter perturbation) — §16.3 row 2.
  - Golden-sample regression (`reviews/_golden/` baseline) — §16.3 row 3 + v3-decisions #14.
  - Admin endpoint (`POST /api/admin/proposals/{slug}/validate`) — Phase 4.5+ depending on EventBus events.
  - `/proposals/:slug` "Run Validation" UI button — depends on above endpoint.
  - LLM-driven diff_draft → param_overrides interpreter — keeps v0 honest; human reads the diff and supplies `--param` flags.
  - Cheatsheet baseline auto-discovery — v0 requires explicit `--strategy` + `--param` flags; the diff_draft is reference only, not parsed.

## Capabilities

### New Capabilities
- `wfa-validation-engine`: Walk-forward validation library + CLI that compares a baseline strategy against a candidate (= baseline + `--param` overrides) over N rolling windows, writes a `validation.json` report, and transitions the proposal state.

### Modified Capabilities
（無——本 change 不修改既有 `proposal-state-machine` / `backtest-engine` / `cli-and-config` 任何 requirement。新增的 CLI sub-command 是擴充而非 spec 變更;state transition 走的是現有 `transition_proposal()` 公開 API。）

## Impact

- **Code 新增:**
  - `src/ohmystock/validation/__init__.py`
  - `src/ohmystock/validation/wfa.py` — `WfaWindow`, `ValidationReport`, `WfaValidationError`, `run_validation()`, internal window-splitter + threshold-evaluator helpers.
  - `src/ohmystock/cli/_validate_proposal.py` — argparse handler + dispatch.
  - `tests/validation/test_wfa.py` — unit tests for window splitter, threshold evaluator, transition wiring, dry-run, malformed-input branches.
  - `tests/cli/test_validate_proposal_cli.py` — CLI integration tests (happy-path pass, happy-path fail, dry-run, status guard, missing strategy).
- **Code 修改:**
  - `src/ohmystock/cli/__init__.py` — register the new `validate-proposal` sub-command.
- **無:**
  - No new env vars / Settings fields.
  - No new DB schema / migration.
  - No FastAPI endpoint / web-admin route / EventBus event.
  - No LLM calls (validator is fully deterministic).
- **External deps:** none new — reuses `run_backtest()`, `available_strategies()`, `transition_proposal()`, existing market_data loader.
- **CLAUDE.md §5 SSOT 新增一列** by archive step (pattern same as prior changes).
