# wfa-validation-engine Specification

## Purpose

定義 Walk-Forward Analysis (WFA) 驗證引擎的契約 — 將策略改動提案（status=`validating`）切成 N 個時序不重疊的 IS/OOS 窗格，以 baseline / candidate 兩組策略跑 backtest，按三條 pass 條件（Sharpe stability / performance degradation / drawdown degradation）裁定 `pass` / `fail`，原子寫 `<slug>.validation.json` 報告，並透過 `transition_proposal` 將 markdown 推進到 `approved`（連同 report 一起搬到 `PENDING_REVIEW/`）或 `rejected`（連同 report 一起搬到 `rejected/`）。提供 `uv run ohmystock validate-proposal <slug>` CLI subcommand 作為 operator 入口。SSOT 對 `docs/workflow-cheatsheet.md` §16 與 `proposals/README.md` §2。

## Requirements

### Requirement: `run_validation` public API shape

The system SHALL expose `ohmystock.validation.wfa.run_validation(proposal_path, *, strategy_name, period, param_overrides, universe, wfa_windows=5, in_sample_ratio=0.7, initial_capital, market_data_loader, dry_run=False) -> ValidationReport` as the single library entry point for walk-forward validation.

`ValidationReport` MUST be a frozen dataclass with these fields, in this order: `proposal_id: str`, `slug: str`, `validated_at: str` (ISO-8601 with `+08:00` offset), `strategy: str`, `period: dict[str, str]` (`{from, to}` ISO dates), `param_overrides: dict[str, Any]`, `effective_kwargs: dict[str, Any]`, `universe: list[str]`, `wfa_windows: list[WfaWindow]`, `baseline_oos_aggregate: dict[str, float]`, `candidate_oos_aggregate: dict[str, float]`, `candidate_is_oos_sharpe_gap_pct: float`, `deltas: dict[str, float]`, `thresholds: dict[str, float]`, `verdict: Literal["pass", "fail"]`, `failures: list[str]`.

`WfaWindow` MUST be a frozen dataclass with fields `in_sample: dict[str, str]`, `out_of_sample: dict[str, str]`, `baseline_is_metrics: dict[str, float]`, `baseline_oos_metrics: dict[str, float]`, `candidate_is_metrics: dict[str, float]`, `candidate_oos_metrics: dict[str, float]`.

Both dataclasses MUST be importable from `ohmystock.validation`.

#### Scenario: happy path returns full report
- **WHEN** `run_validation` is called with a valid `validating` proposal, `strategy_name="sma_cross"`, a 252-day period, `param_overrides={"fast": 10}`, `universe=["2330"]`, and a `market_data_loader` returning sufficient bars
- **THEN** the return value is a `ValidationReport` instance
- **AND** `report.verdict` is one of `"pass"` / `"fail"`
- **AND** `len(report.wfa_windows) == 5`
- **AND** `report.effective_kwargs["fast"] == 10` and contains the strategy's other default kwargs unchanged
- **AND** `report.validated_at` parses as an ISO-8601 datetime with `+08:00` offset

#### Scenario: dry_run skips file write and state transition
- **WHEN** `run_validation(..., dry_run=True)` is called against a `validating` proposal
- **THEN** no file is created at `<proposal_dir>/<slug>.validation.json`
- **AND** the proposal markdown's frontmatter `status` remains `validating`
- **AND** the function returns a fully-populated `ValidationReport`

---

### Requirement: Walk-forward window construction

The validator SHALL split the requested `period` into `wfa_windows` (default 5) equal-length **chunks** in chronological order. Within each chunk, the first `in_sample_ratio` (default 0.7) of the chunk's calendar days form the in-sample window; the remaining days form the out-of-sample window. Adjacent chunks MUST be temporally disjoint; an OOS window from chunk N MUST NOT overlap any window from chunk N+1.

For each window the validator SHALL run `run_backtest` four times: baseline on IS, baseline on OOS, candidate on IS, candidate on OOS — and store the four `compute_metrics` payloads (filtered to `{sharpe, max_drawdown, win_rate}`) on the corresponding `WfaWindow`.

Each per-window backtest MUST start fresh with `initial_capital`; portfolio state MUST NOT carry across windows.

#### Scenario: 5 disjoint windows over a 250-day period
- **WHEN** `period = {"from": "2025-01-02", "to": "2025-12-30"}` (250 trading days) and `wfa_windows=5`, `in_sample_ratio=0.7`
- **THEN** `report.wfa_windows` has length 5
- **AND** for every pair `(i, j)` with `j > i`, `report.wfa_windows[i].out_of_sample.to < report.wfa_windows[j].in_sample.from`
- **AND** within each window, `in_sample.to < out_of_sample.from`

#### Scenario: period_too_short refuses degenerate input
- **WHEN** `run_validation` is called with `period` shorter than `wfa_windows * 5` days
- **THEN** `WfaValidationError("period_too_short")` is raised
- **AND** no backtest call is made
- **AND** no file is written

---

### Requirement: Three pass conditions, evaluated in declared order

The validator SHALL compute three pass conditions in this exact order and record the result of each on the report's `failures` list (only failing conditions appear there):

1. **Sharpe stability (over-fitting check):** `mean(candidate.IS_oos_sharpe_gap across windows) < 0.30` where per-window gap = `abs(IS - OOS) / max(abs(IS), 1e-9)`.
2. **Performance degradation:** `candidate_oos_aggregate.sharpe >= baseline_oos_aggregate.sharpe * 0.95`.
3. **Drawdown degradation:** `abs(candidate_oos_aggregate.max_drawdown) <= abs(baseline_oos_aggregate.max_drawdown) * 1.20`.

`verdict` SHALL be `"pass"` iff all three conditions hold; otherwise `"fail"`. `failures` SHALL contain one human-readable line per failed condition in the order above, naming the actual value, the threshold, and a slug like `"sharpe_gap"`, `"sharpe_degradation"`, `"drawdown_degradation"`.

`thresholds` SHALL record the constants used: `{sharpe_gap_max: 0.30, sharpe_relative_min: 0.95, drawdown_relative_max: 1.20}`.

#### Scenario: all three OK → verdict pass, failures empty
- **WHEN** the candidate's mean Sharpe gap is `0.18`, candidate OOS Sharpe is `1.05 × baseline OOS Sharpe`, and candidate `|MDD|` is `0.90 × baseline |MDD|`
- **THEN** `report.verdict == "pass"`
- **AND** `report.failures == []`

#### Scenario: Sharpe gap fail surfaces in failures
- **WHEN** the candidate's mean Sharpe gap is `0.42`, the other two conditions hold
- **THEN** `report.verdict == "fail"`
- **AND** `report.failures` has length 1
- **AND** `report.failures[0]` contains the substring `sharpe_gap`
- **AND** `report.failures[0]` contains both `0.42` (or its rounded form) and `0.30`

#### Scenario: multiple failures appear in declared order
- **WHEN** all three pass conditions fail
- **THEN** `report.failures` has length 3
- **AND** `report.failures[0]` references `sharpe_gap`
- **AND** `report.failures[1]` references `sharpe_degradation`
- **AND** `report.failures[2]` references `drawdown_degradation`

---

### Requirement: Validation report on disk

When `dry_run=False`, the validator SHALL write `<proposal_dir>/<slug>.validation.json` containing the JSON serialisation of `ValidationReport`. The write MUST be atomic: create a `tempfile.NamedTemporaryFile` in the same directory with suffix `.validation.json.tmp`, write all bytes, `flush()` + `os.fsync(fd)`, then `os.replace(tmp_path, target_path)`. Mid-write process kill MUST leave either the previous file or no file — never a half-written one.

The serialised JSON MUST be `json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=False)`. Dataclass field order from the public API requirement MUST be preserved (no alphabetic sort) so the report reads top-down as `metadata → windows → aggregates → thresholds → verdict → failures`.

If `<proposal_dir>/<slug>.validation.json` already exists, the validator SHALL silently overwrite it (this is a re-run; the most recent verdict is the canonical one).

#### Scenario: report written atomically
- **WHEN** `run_validation(..., dry_run=False)` completes successfully
- **THEN** `<proposal_dir>/<slug>.validation.json` exists and parses as JSON
- **AND** no `*.validation.json.tmp` files remain in the directory
- **AND** the file's top-level keys appear in declared dataclass order (verifiable by `list(json.loads(text).keys())[:5] == ["proposal_id", "slug", "validated_at", "strategy", "period"]`)

#### Scenario: re-run overwrites existing report
- **WHEN** `run_validation` runs twice against the same proposal with different `param_overrides`
- **THEN** the second run replaces the first file's contents
- **AND** the second run's `validated_at` is strictly later than the first

---

### Requirement: Proposal state transition

When `dry_run=False`, after the report file is on disk, the validator SHALL call `transition_proposal` from `ohmystock.proposal`:

- `verdict == "pass"` → `transition_proposal(proposal_path, "approved", actor="wfa-validator", validation_report_path=Path(f"{slug}.validation.json"))`
- `verdict == "fail"` → `transition_proposal(proposal_path, "rejected", actor="wfa-validator", reason=<one-line summary>)` where `<one-line summary>` SHALL be `"; ".join(failures)` truncated to 200 chars.

After `transition_proposal` returns the new path, the validator SHALL move the report file to remain a sibling: if `new_path.parent != proposal_path.parent`, `report_path.rename(new_path.parent / report_path.name)`. The move MUST happen even if it crosses directory boundaries (e.g. root → `PENDING_REVIEW/`).

The validator SHALL refuse to call `transition_proposal` if the proposal's current `status` (read from frontmatter) is not exactly `"validating"`. In that case it MUST raise `WfaValidationError("status_not_validating: actual=<current>")` BEFORE running any backtest.

#### Scenario: pass transitions validating → approved with report path
- **WHEN** `run_validation` produces `verdict == "pass"` on a `validating` proposal
- **THEN** the proposal markdown's frontmatter `status` becomes `approved`
- **AND** the frontmatter has `validation_report_path: <slug>.validation.json`
- **AND** the markdown file has moved to `<proposals_root>/PENDING_REVIEW/`
- **AND** the report JSON has moved to `<proposals_root>/PENDING_REVIEW/<slug>.validation.json` (sibling)

#### Scenario: fail transitions validating → rejected with reason
- **WHEN** `run_validation` produces `verdict == "fail"` with `failures` containing `"sharpe_degradation: 0.83 < 0.95"`
- **THEN** the proposal markdown's frontmatter `status` becomes `rejected`
- **AND** the rejected_reason in frontmatter contains the substring `sharpe_degradation`
- **AND** the markdown file has moved to `<proposals_root>/rejected/`
- **AND** the report JSON has moved to `<proposals_root>/rejected/<slug>.validation.json`

#### Scenario: non-validating status refuses to run
- **WHEN** `run_validation` is called against a proposal whose frontmatter `status` is `pending`
- **THEN** `WfaValidationError` is raised before any backtest call
- **AND** the error message contains both `status_not_validating` and `pending`
- **AND** no file is written and no transition happens

---

### Requirement: Bars loader injection

`run_validation` SHALL accept a `market_data_loader: Callable[[str, str, str], list[BarRow]]` parameter and use it as the **only** source of bar data. The validator MUST NOT directly import or call `select_bars`, `get_connection`, or any cache module — all bar I/O routes through the injected callable.

The callable is invoked as `market_data_loader(symbol, period_start, period_end)` and is expected to return bars within `[period_start, period_end]` inclusive, ascending by `ts`. The validator MAY pre-fetch per-symbol over the full requested period and slice in-memory per window for performance.

#### Scenario: tests inject a synthetic loader
- **WHEN** a test calls `run_validation(..., market_data_loader=lambda sym, s, e: synthetic_bars[sym])`
- **THEN** no SQLite connection is opened by `ohmystock.validation.wfa`
- **AND** the synthetic bars drive the backtest

#### Scenario: missing bars surface as WfaValidationError
- **WHEN** `market_data_loader(symbol, period_start, period_end)` returns an empty list for any symbol in `universe`
- **THEN** `WfaValidationError("missing_bars: <symbol>")` is raised
- **AND** no backtest is invoked

---

### Requirement: CLI `validate-proposal` subcommand

The system SHALL register `uv run ohmystock validate-proposal <slug>` as a subcommand on the existing Typer app at `ohmystock.cli`. The handler SHALL:

1. Resolve `<slug>` against `Settings().proposals_dir` (probing the 4 sub-locations root / `PENDING_REVIEW/` / `merged/` / `rejected/` in that order, mirroring the admin endpoint's resolution). Missing slug → exit 2 with message `proposal not found: <slug>`.
2. Read frontmatter; if `status != "validating"`, exit 2 with message `proposal status must be 'validating', got '<actual>'`. Do NOT call the validator library.
3. Parse `--strategy`, `--period`, `--param key=value` (repeatable), `--wfa-windows`, `--in-sample-ratio`, `--universe`, `--initial-capital`, `--dry-run` flags. Defaults: `wfa_windows=5`, `in_sample_ratio=0.7`, `universe="2330,0050,2317"`, `initial_capital=Settings().starting_equity_twd`, `dry_run=False`. `--strategy` and `--period` are required.
4. Coerce each `--param key=value` literal via `ast.literal_eval` on the value side, so `--param fast=10` yields `int(10)` and `--param qty=1000.5` yields `float(1000.5)`. Malformed literals → exit 2 with `unparseable_param: <key>=<raw>`.
5. Look up the strategy class via `available_strategies()`; if `--strategy` is not registered → exit 2 with `unknown_strategy: <name>`.
6. Construct the candidate strategy as `strategy_cls(**default_kwargs | overrides)`; if construction raises `TypeError` → exit 2 with `unknown_param: <key>` (the param the user passed is not a kwarg of the strategy class).
7. Build `market_data_loader` from `get_connection() + select_bars` (default factory) and call `run_validation(...)`.
8. On `WfaValidationError`, exit 2 with the error's `args[0]`.
9. After `run_validation` returns, print a one-line summary to stdout: `verdict=pass slug=<slug> sharpe_delta=<+/-N%> mdd_delta=<+/-N%>` (or the failure summary on fail). Exit code matches the verdict mapping in D6 (pass→0, fail→1).

#### Scenario: happy path prints summary and exits 0
- **WHEN** a developer runs `uv run ohmystock validate-proposal 2026-04-30-vcp --strategy sma_cross --period from=2025-01-02,to=2025-12-30 --param fast=10`
- **AND** the proposal is `validating` and verdict computes to `pass`
- **THEN** stdout contains `verdict=pass slug=2026-04-30-vcp`
- **AND** the process exits with code 0

#### Scenario: status guard short-circuits
- **WHEN** the proposal's status is `pending`
- **THEN** stdout contains `proposal status must be 'validating'`
- **AND** the process exits with code 2
- **AND** no backtest runs

#### Scenario: unknown strategy reports a clear error
- **WHEN** the user passes `--strategy made_up_name`
- **THEN** stdout (or stderr) contains `unknown_strategy: made_up_name`
- **AND** the process exits with code 2

#### Scenario: dry-run prints would-be verdict without transitioning
- **WHEN** the user passes `--dry-run` against a `validating` proposal
- **THEN** the process exits with code 0 (regardless of would-be verdict)
- **AND** no `.validation.json` file is written
- **AND** the proposal status remains `validating`
- **AND** stdout contains `dry_run=true` and the would-be `verdict=...`
