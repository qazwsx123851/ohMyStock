## 1. Reorganise CLI module without behaviour change

- [x] 1.1 Convert `src/ohmystock/cli.py` to `src/ohmystock/cli/__init__.py`, preserving every existing top-level symbol (`app`, `main`, `run`, `backtest`, `review`, `propose`, `screen`, `api`, `smoke_test`) so existing imports keep working.
- [x] 1.2 Run `git grep "from ohmystock.cli import"` and `git grep "ohmystock\.cli\."` across `src/`, `tests/`, and `pyproject.toml`; verify no broken references.
- [x] 1.3 Run the existing CLI test suite (`uv run pytest tests/test_cli*.py tests/test_smoke_test*.py 2>/dev/null` plus any other CLI-related tests under `tests/`) and confirm all pass with the package layout.
- [x] 1.4 Run `uv run ohmystock --help` and `uv run ohmystock smoke-test --help` manually to verify the `console_scripts` entry still resolves.

## 2. Wire the deferred sub-package skeleton

- [x] 2.1 Create `src/ohmystock/scoring/subscorers/deferred/__init__.py` with explicit `from . import <stub>  # noqa: F401` lines for all 16 deferred stubs (alphabetical order to make diffs review-friendly).
- [x] 2.2 Edit `src/ohmystock/scoring/subscorers/__init__.py` to add `from . import deferred  # noqa: F401` after the existing real-sub-scorer imports.

## 3. Implement 16 deferred stub modules (one file per sub-scorer, ~10 lines each)

- [x] 3.1 `src/ohmystock/scoring/subscorers/deferred/kline_patterns.py` — register `("technical", "kline_patterns", 8)`; reason `"data source not implemented"`.
- [x] 3.2 `src/ohmystock/scoring/subscorers/deferred/rs_percentile.py` — register `("technical", "rs_percentile", 7)`; reason `"data source not implemented"`.
- [x] 3.3 `src/ohmystock/scoring/subscorers/deferred/broker_concentration.py` — register `("chip", "broker_concentration", 7)`; reason `"data source not implemented"`.
- [x] 3.4 `src/ohmystock/scoring/subscorers/deferred/futures_oi.py` — register `("chip", "futures_oi", 3)`; reason `"data source not implemented"`.
- [x] 3.5 `src/ohmystock/scoring/subscorers/deferred/margin_tightening.py` — register `("chip", "margin_tightening", 2)`; reason `"data source not implemented"`.
- [x] 3.6 `src/ohmystock/scoring/subscorers/deferred/tdcc_concentration.py` — register `("chip", "tdcc_concentration", 2)`; reason `"data source not implemented"`.
- [x] 3.7 `src/ohmystock/scoring/subscorers/deferred/borrow_change.py` — register `("chip", "borrow_change", 2)`; reason MUST contain `"negative-band scoring requires registry contract change"`.
- [x] 3.8 `src/ohmystock/scoring/subscorers/deferred/eps_yoy.py` — register `("fundamental", "eps_yoy", 8)`; reason `"data source not implemented"`.
- [x] 3.9 `src/ohmystock/scoring/subscorers/deferred/eps_qoq.py` — register `("fundamental", "eps_qoq", 5)`; reason `"data source not implemented"`.
- [x] 3.10 `src/ohmystock/scoring/subscorers/deferred/monthly_revenue_yoy.py` — register `("fundamental", "monthly_revenue_yoy", 6)`; reason `"data source not implemented"`.
- [x] 3.11 `src/ohmystock/scoring/subscorers/deferred/quarterly_revenue_yoy.py` — register `("fundamental", "quarterly_revenue_yoy", 3)`; reason `"data source not implemented"`.
- [x] 3.12 `src/ohmystock/scoring/subscorers/deferred/institutional_30d_holding.py` — register `("fundamental", "institutional_30d_holding", 3)`; reason `"data source not implemented"`.
- [x] 3.13 `src/ohmystock/scoring/subscorers/deferred/analyst_target_upgrades.py` — register `("sentiment", "analyst_target_upgrades", 3)`; reason `"data source not implemented"`.
- [x] 3.14 `src/ohmystock/scoring/subscorers/deferred/sue.py` — register `("sentiment", "sue", 3)`; reason `"data source not implemented"`.
- [x] 3.15 `src/ohmystock/scoring/subscorers/deferred/important_announcements.py` — register `("sentiment", "important_announcements", 2)`; reason `"data source not implemented"`.
- [x] 3.16 `src/ohmystock/scoring/subscorers/deferred/search_heat.py` — register `("sentiment", "search_heat", 2)`; reason MUST contain `"negative-band scoring requires registry contract change"`.

## 4. Verify deferred-stub registration end-to-end

- [x] 4.1 Write `tests/test_deferred_stubs.py` — parametrize over the 16 deferred names; each case asserts `dispatch(name, ctx).status == "skipped"`, `points == 0`, `max_points` matches the registered cap, `evidence["reason"]` is non-empty, `error_message is None`.
- [x] 4.2 In the same file, add one test asserting `dispatch("borrow_change", ctx).evidence["reason"]` and `dispatch("search_heat", ctx).evidence["reason"]` both contain `"negative-band scoring requires registry contract change"`.
- [x] 4.3 Add an assertion in `test_deferred_stubs.py` that `list_subscorers()` after fresh import contains all 22 names (6 real + 16 deferred) with their expected `(category, max_points)` tuples.
- [x] 4.4 Run `uv run pytest tests/test_deferred_stubs.py -q` and confirm all parametrized cases pass.

## 5. Extend the subscorer-layout test to cover the deferred package

- [x] 5.1 Edit `tests/test_subscorers_layout.py` to also walk `src/ohmystock/scoring/subscorers/deferred/`; assert every `<name>.py` (excluding `__init__.py`) has a corresponding registered sub-scorer name from the deferred sub-package, and vice versa.
- [x] 5.2 Run `uv run pytest tests/test_subscorers_layout.py -q`; confirm pass.

## 6. Confirm reverse-import isolation still holds

- [x] 6.1 Read `tests/test_scoring_reverse_import.py`; if its assertion checks `sys.modules` after `import ohmystock.scoring`, no edit needed (the deferred sub-package is automatically covered). If it lists individual sub-scorer modules by name, extend it to include the 16 deferred files.
- [x] 6.2 Run `uv run pytest tests/test_scoring_reverse_import.py -q`; confirm `fastapi`/`uvicorn`/`starlette` still absent from `sys.modules` after `import ohmystock.scoring`.

## 7. Implement `score watchlist` CLI subcommand

- [x] 7.1 Create `src/ohmystock/cli/_score.py`: define `score_app = typer.Typer(help="...")`; implement `@score_app.command("watchlist")` accepting `--asof: str` (required), `--symbols: str` (required), `--top-n: int = None`, `--json: bool = False` (with `--no-json`).
- [x] 7.2 Inside `watchlist(...)`, parse `--symbols` (split on `,`, strip whitespace, drop empty items), call `ohmystock.scoring.score_watchlist(asof_date=asof, candidates=symbols, top_n=top_n)`, and branch on `env["ok"]`.
- [x] 7.3 On `ok=True` + `--no-json`: sort `env["data"]["candidates"]` by `(-final_score, symbol)`, apply `top_n` truncation **after** sort (in case engine didn't already), print CSV header + one row per candidate; format `risk_off_applied` as lowercase `true`/`false`; `final_score` and subtotals as `repr(float)` (e.g., `78.0`).
- [x] 7.4 On `ok=True` + `--json`: print `json.dumps(env, ensure_ascii=False)` to stdout, no extra processing.
- [x] 7.5 On `ok=False`: print `error: <code>: <message>` to **stderr** (use `typer.echo(..., err=True)`); leave stdout empty; `raise typer.Exit(1)`.
- [x] 7.6 In `src/ohmystock/cli/__init__.py`, after the existing command definitions: `from ._score import score_app; app.add_typer(score_app, name="score", help="Phase 2B scoring 子命令")`.

## 8. Test the score CLI subcommand

- [x] 8.1 Create `tests/test_cli_score_watchlist.py`. Set up `from typer.testing import CliRunner; from ohmystock.cli import app; runner = CliRunner()` (newer typer drops `mix_stderr` — stderr is separated by default).
- [x] 8.2 Test `--help`: `runner.invoke(app, ["score", "watchlist", "--help"])` exits 0; stdout contains `--asof`, `--symbols`, `--top-n`, `--json`.
- [x] 8.3 Test CSV success path: monkeypatch `ohmystock.cli._score.score_watchlist` to return a deterministic envelope with one candidate; assert exit 0, stdout first line is the header, second line matches expected row format including `true/false` lowercase.
- [x] 8.4 Test `--json` success path: monkeypatch returns same envelope; assert `json.loads(stdout) == envelope`.
- [x] 8.5 Test `--top-n` truncation: monkeypatch returns two candidates with different `final_score`; invoke with `--top-n 1`; assert only the higher-scored row appears.
- [x] 8.6 Test sort + tie-break: monkeypatch returns three candidates with two ties at the top score (`2317`, `2330`) and one lower (`1101`); assert stdout row order is `2317`, `2330`, `1101`.
- [x] 8.7 Test validation error path: invoke with `--asof 2026/04/30 --symbols 2330` (no monkeypatch — let real `score_watchlist` reject); assert exit 1, stderr contains `INVALID_INPUT`, stdout is empty.
- [x] 8.8 Test missing required flags: `runner.invoke(app, ["score", "watchlist"])` exits non-zero; stderr mentions `--asof` or `--symbols`.
- [x] 8.9 Run `uv run pytest tests/test_cli_score_watchlist.py -q`; confirm all 8 cases pass.

## 9. Confirm root help and existing CLI behaviour intact

- [x] 9.1 Run `uv run ohmystock --help`; confirm output lists exactly 8 commands (`run`, `backtest`, `review`, `propose`, `screen`, `api`, `smoke-test`, `score`).
- [x] 9.2 Run `uv run ohmystock score --help`; confirm exit 0, output contains `watchlist`, no `not implemented` text.
- [x] 9.3 Run `uv run ohmystock run` (and the other four stubs); confirm exit 1, stdout contains `not implemented` (existing behaviour unchanged).

## 10. Final validation and archive readiness

- [x] 10.1 Run `uv run pytest -q` (full suite); confirm green and no regressions in pre-existing tests. (337 passed, including the updated `test_full_max_score_with_real_subscorers` assertion that 22 sub-scorers now appear in the envelope, of which 6 are scored and 16 are skipped.)
- [x] 10.2 Run `openspec validate phase-2b-deferred-cli`; confirm valid.
- [x] 10.3 Run `openspec status --change phase-2b-deferred-cli`; confirm all artifacts marked `done`.
- [x] 10.4 Manual smoke check: `uv run ohmystock score watchlist --asof 2026-04-30 --symbols 2330,2317,1101 --top-n 3 --json` emits a valid JSON envelope to stdout. (Verified: `ok=True`, 3 candidates, 22 subscores per candidate.)
- [ ] 10.5 Commit with message `feat(scoring): phase 2B deferred sub-scorer stubs + score watchlist CLI`; do **not** archive yet — archive happens in `/opsx:archive` after manual review.
