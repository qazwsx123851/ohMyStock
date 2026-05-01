## Why

`phase-2b-shipped-subscorers` shipped 6 real sub-scorers covering 34 of 100 score points (`tech=25`, `chip=9`); the remaining 66 points belong to sub-scorers whose data sources (broker concentration, futures OI, TDCC, EPS, monthly revenue, news, analyst targets, search heat, RS percentile, K-line patterns) are **not yet implemented**. Without explicit registrations for those 16 sub-scorers, the score envelope silently misses them and an operator cannot see "is this a real 30 score, or a 30 score because data is missing?". This change registers all 16 as **deferred-stubs** that emit `status="skipped"` (zero points, but visible in the envelope), and ships the `ohmystock score watchlist` CLI subcommand so a daily Phase 2B run is finally invocable from the shell — closing the Phase 2B engine surface ahead of the LLM Decider work in Phase 3.

## What Changes

- Add 16 deferred-stub sub-scorers, each registered via `@register_subscorer(category, name, max_points)` and returning a `SubScoreResult` with `status="skipped"`, `points=0`, and `evidence={"reason": "data source not implemented"}`. Files live under `src/ohmystock/scoring/subscorers/deferred/` (one file per stub) so the layout requirement from `phase-2b-scoring-engine` extends naturally:
  - **Technical (2 stubs, 15 points):** `kline_patterns` (8), `rs_percentile` (7).
  - **Chip (5 stubs, 13 points net):** `broker_concentration` (7), `futures_oi` (3), `margin_tightening` (2), `tdcc_concentration` (2), `borrow_change` (max_points 2 — see Out of Scope on negative bands).
  - **Fundamental (5 stubs, 25 points):** `eps_yoy` (8), `eps_qoq` (5), `monthly_revenue_yoy` (6), `quarterly_revenue_yoy` (3), `institutional_30d_holding` (3).
  - **Sentiment (4 stubs, 10 points net):** `analyst_target_upgrades` (3), `sue` (3), `important_announcements` (2), `search_heat` (max_points 2 — see Out of Scope on negative bands).
- Each stub MUST be a one-liner pure function (no data fetch, no exceptions) so registration is the only behavior under test. A single parametric test `tests/test_deferred_stubs.py` SHALL drive every deferred stub through `dispatch(...)` and assert `status="skipped"`, `points=0`, `max_points` matches registration, and `evidence["reason"]` is set.
- Replace the `score` subcommand stub (currently part of the five `not implemented` typer commands; see `cli-and-config` capability "CLI 子命令骨架") with a real `ohmystock score watchlist` Typer command group: `score watchlist --asof <YYYY-MM-DD> --symbols 2330,2317,...` SHALL call `score_watchlist(...)` and print one CSV row per candidate (`symbol,final_score,classification,risk_off_applied,tech,chip,fund,sent`) sorted by `final_score` descending; `--top-n` and `--json` flags SHALL be accepted; on `ok=False` the command SHALL print `error: <code> <message>` to stderr and exit 1. The pre-existing `screen` subcommand stub remains as a stub (separate concern: universe screening, not scoring).
- **BREAKING (CLI surface only — no consumer yet):** The `cli-and-config` capability requirement "CLI 子命令骨架" is **MODIFIED** so that `score` is no longer in the "five stubs" list and is instead documented as a real subcommand group with its own behavior requirement. Total subcommand count stays at 7.
- Reverse-import isolation guard updated to assert that adding 16 stubs does not pull `fastapi`/`uvicorn`/`starlette` into the `ohmystock.scoring` import graph.
- `tests/test_subscorers_layout.py` extended to assert each deferred stub file matches its sub-scorer name.

**Out of scope (explicitly deferred to later changes):**
- Real implementations of any of the 16 stubs — each one ships in the change that lands its underlying data source (e.g., `broker_concentration` waits on the broker-trades data skill).
- Negative-band sub-scorers (`borrow_change` ranges `-3..+2`, `search_heat` ranges `-2..+2`). The `max_points` registry contract from `phase-2b-scoring-engine` is non-negative and `dispatch` clamps `points` to `[0, max_points]`. To avoid lying about the cap or reshaping the registry under a stub, both are registered with `max_points=2` (the upper bound) and the negative-penalty behavior is treated as a separate change once the data source exists. This is documented in `evidence["reason"]` for the two stubs.
- Catalyst correction (`+5` / `-10`), monthly-revenue bonus (`+5`), and any aggregation logic outside the existing `_engine.py` envelope — those land alongside the catalyst data source in a future change.
- WFA / SEPA golden-sample calibration of point bands.
- The other four stub subcommands (`run`, `backtest`, `review`, `propose`) — they remain as `not implemented` stubs and will be filled by their respective Phase changes.

## Capabilities

### New Capabilities
_(None — this change extends two existing capabilities.)_

### Modified Capabilities
- `phase-2b-scoring-engine`: ADDS one Requirement covering all 16 deferred-stub sub-scorers (registered with category + max_points, returning `status="skipped"`, deterministic `evidence`), and extends the existing sub-scorer file-layout requirement so deferred stubs live under `subscorers/deferred/`.
- `cli-and-config`: MODIFIES the "CLI 子命令骨架" requirement so `score` is removed from the stub list, and ADDS a new Requirement defining `ohmystock score watchlist` behavior (flags, output format, exit codes, error path).

## Impact

- **New code:**
  - `src/ohmystock/scoring/subscorers/deferred/__init__.py` — package marker; imports each deferred stub module to trigger registration.
  - `src/ohmystock/scoring/subscorers/deferred/kline_patterns.py`, `rs_percentile.py`, `broker_concentration.py`, `futures_oi.py`, `margin_tightening.py`, `tdcc_concentration.py`, `borrow_change.py`, `eps_yoy.py`, `eps_qoq.py`, `monthly_revenue_yoy.py`, `quarterly_revenue_yoy.py`, `institutional_30d_holding.py`, `analyst_target_upgrades.py`, `sue.py`, `important_announcements.py`, `search_heat.py` — 16 files.
  - `src/ohmystock/cli/__init__.py` (re-export) and split of `src/ohmystock/cli.py` → `src/ohmystock/cli/_app.py` + `src/ohmystock/cli/_score.py` so the new `score` subcommand group can live in its own module without bloating `cli.py`. The `pyproject.toml` `console_scripts` entry stays `ohmystock = "ohmystock.cli:main"`.
  - `tests/test_deferred_stubs.py` — single parametric test exercising all 16 stubs through `dispatch`.
  - `tests/test_cli_score_watchlist.py` — Typer `CliRunner` test covering success path (CSV + `--json`), `--top-n`, validation error → exit 1.
- **Edited code:**
  - `src/ohmystock/scoring/subscorers/__init__.py` — add `from . import deferred  # noqa: F401`.
  - `src/ohmystock/scoring/__init__.py` — no behavior change; layout test extension only.
  - `tests/test_subscorers_layout.py` — extend to cover deferred package.
  - `tests/test_scoring_reverse_import.py` — extend forbidden-import set assertion to cover the deferred package.
- **Deleted code:** none.
- **Code consumed (no edits):**
  - `ohmystock.scoring.registry.register_subscorer`, `dispatch`.
  - `ohmystock.scoring.models.SubScoreResult`.
  - `ohmystock.scoring.score_watchlist` (engine entry point).
  - `typer` (already a transitive dep via existing CLI).
- **DB / migrations:** none.
- **Docs:** `docs/workflow-cheatsheet.md` §6.1 already lists all 22 sub-scorers (6 real + 16 deferred); no update needed. `docs/tools-contracts.md` does not cover CLI; no update needed.
- **Risk:** the layout split of `cli.py` → `cli/` package is a low-risk move because the public `main()` entry point stays in `ohmystock.cli` (the package's `__init__.py`); existing tests asserting `ohmystock --help` and `ohmystock smoke-test` continue to pass without touching `pyproject.toml`.
