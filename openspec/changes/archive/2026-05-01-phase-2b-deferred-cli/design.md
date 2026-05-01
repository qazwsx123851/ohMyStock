## Context

`phase-2b-scoring-engine` defined the registry/dispatch contract and `_engine.py` aggregation; `phase-2b-shipped-subscorers` populated it with 6 real sub-scorers (`tech=25`, `chip=9` of a possible 100). The scoring envelope today returns 6 entries in `subscores[]`; an operator running it on `2330` cannot tell whether the missing 16 are intentionally future work or a silent bug. Meanwhile, `cli-and-config` documents 7 subcommands (`run/backtest/review/propose/screen/api/smoke-test`); five of them (`run/backtest/review/propose/screen`) currently `echo "not implemented"; exit 1`. The proposal text says "score is removed from the stub list" — re-reading `src/ohmystock/cli.py` confirms `score` is **not** currently a subcommand at all; this change therefore **adds** `score` as a new (eighth) subcommand group, and the `cli-and-config` "CLI 子命令骨架" requirement needs a small delta to bump the count from seven to eight.

This design pins down: (1) the deferred-stub package layout; (2) the registry call shape that satisfies the engine's existing dispatch contract without requiring engine changes; (3) the CLI module split (`cli.py` → `cli/` package) and how the new `score watchlist` command keeps the `ohmystock = "ohmystock.cli:main"` entry point intact; (4) the test surface that proves all 16 stubs register, dispatch, and don't accidentally pull web framework deps.

## Goals / Non-Goals

**Goals:**
- Every one of the 22 sub-scorers documented in `docs/workflow-cheatsheet.md` §6.1 is registered after `import ohmystock.scoring`. The 6 real ones run their logic; the 16 deferred ones return `status="skipped"` deterministically.
- A single CLI invocation `ohmystock score watchlist --asof YYYY-MM-DD --symbols 2330,2317` produces a sorted CSV (or JSON with `--json`) by piping through `score_watchlist(...)` with no other code path.
- `cli.py` is reorganized into a `cli/` package without breaking `ohmystock --help`, `ohmystock smoke-test`, the `console_scripts` entry, or any existing CLI test.
- Reverse-import isolation: `import ohmystock.scoring` does not pull `fastapi`/`uvicorn`/`starlette`/`anthropic` (the existing guard's forbidden set) even after the deferred package loads.
- Adding a 17th deferred stub later is purely additive: drop a file in `subscorers/deferred/`, list it in `__init__.py`, layout test verifies it — no edits to engine, registry, or aggregator.

**Non-Goals:**
- No real data fetching for any of the 16 stubs. They are stubs precisely because their data sources are not implemented.
- No support for negative-band sub-scorers (`borrow_change`, `search_heat`). The registry's `max_points` is non-negative and `dispatch` clamps to `[0, max_points]`. Reshaping the registry to allow signed bands is a separate change.
- No catalyst correction (`±5/-10`), monthly-revenue bonus (`+5`), or any aggregation logic outside the engine envelope.
- No change to the existing 6 real sub-scorers, the engine, or the registry's public API.
- No new `pyproject.toml` deps. `typer` is already pulled in by the existing CLI.
- No upgrade to the four other stub subcommands (`run`/`backtest`/`review`/`propose`); they stay as `not implemented` exit-1 stubs.

## Decisions

### D1 — Deferred stubs live in `subscorers/deferred/` (one file per stub), not in a single `_deferred.py`

**Decision:** 16 separate files under `src/ohmystock/scoring/subscorers/deferred/`, each ~10 lines, each registering exactly one sub-scorer.

**Why:** The shipped-subscorers change established "one file per sub-scorer" as the layout invariant (`tests/test_subscorers_layout.py` enforces it). Putting 16 stubs into one file would force a different layout for stubs vs real, which (a) leaks stub-vs-real classification into the file structure (noise an LLM agent has to learn), (b) breaks the layout test's regex, and (c) makes the future "promote stub X to real" diff noisier than necessary (move file out of `deferred/`, replace body, vs delete one block from a megafile and create a new file). Cost is 16 small files, but each is ~10 lines and they form a single import block.

**Alternative considered:** A single `subscorers/_deferred.py` with 16 `register_subscorer` calls. Rejected — see above.

**Alternative considered:** Driving deferred stubs from a YAML/JSON manifest at module load time. Rejected — silent registration via reflection violates the project's "explicit imports = explicit ownership" preference (the existing `subscorers/__init__.py` already imports each real sub-scorer module by name; deferred stubs follow suit).

### D2 — `subscorers/deferred/__init__.py` explicitly imports each stub module by name

**Decision:** No auto-discovery via `pkgutil.walk_packages` or filesystem glob. The `__init__.py` lists 16 explicit `from . import kline_patterns  # noqa: F401` lines.

**Why:** Matches the pattern in `subscorers/__init__.py` for the 6 real sub-scorers. Auto-discovery would silently swallow registration failures (e.g., a typo in `@register_subscorer` decorator args) and make the import graph harder for LLM agents to reason about. The cost is one line of bookkeeping per stub, which is worth it for the explicit failure mode: if a file exists but isn't listed, `tests/test_subscorers_layout.py` (extended) catches it.

### D3 — Stub function body is uniform: returns `SubScoreResult(name, category, points=0, max_points, status="skipped", evidence={"reason": "data source not implemented"})`

**Decision:** Every stub has the same shape — only the `name`, `category`, and `max_points` differ. The body is verbatim.

**Why:** The dispatch contract from `phase-2b-scoring-engine` requires the function to return a `SubScoreResult`; `dispatch` then overwrites `name`, `category`, `max_points` from registry metadata and clamps `points`. So the stub *could* return `SubScoreResult(name="", category="technical", points=0, max_points=0, status="skipped", evidence={...})` and dispatch would correct it. We pass the real values anyway because (a) it makes the file readable in isolation, (b) it lets a unit test exercise the stub directly without going through dispatch, (c) it documents intent. The `evidence["reason"]` string is the same for all 16; future real implementations will replace it with structured evidence.

**Alternative considered:** A `make_skipped(name, category, max_points)` factory in `deferred/__init__.py` so each stub file is one line. Rejected — adds a layer of indirection that an LLM agent must trace through, for a savings of ~5 lines per file. Net negative for readability.

### D4 — Negative-band sub-scorers (`borrow_change`, `search_heat`) register with `max_points=2` and document the gap in `evidence["reason"]`

**Decision:** Both ship with `max_points=2` (the upper bound of their documented bands `-3..+2` and `-2..+2`); `evidence["reason"]` reads `"data source not implemented; negative-band scoring requires registry contract change"`.

**Why:** The existing registry contract (`phase-2b-scoring-engine` Requirement "Sub-scorer registry contract") clamps `points` to `[0, max_points]` with non-negative `max_points`. Allowing signed `max_points` or a separate `min_points` field is a registry reshape and breaks the existing dispatch test ("dispatch clamps negative points to zero"). That work belongs in a future change that lands the data source. Today, registering `max_points=2` (a) doesn't lie about what the cap will be on the positive side, (b) keeps `dispatch`'s clamp behavior unchanged, (c) flags the gap explicitly via `evidence` so a reader sees it. The cost is that the stub under-counts the negative-penalty side — but a stub returning `points=0` already under-counts everything, so this is consistent.

**Alternative considered:** Skip these two stubs entirely and only register 14. Rejected — the operator-visibility motivation (proposal "Why") wants *all* missing scorers visible in the envelope, not just the easy ones.

**Alternative considered:** Register with `max_points=5` (`abs(-3)+2`) so the cap matches the total band width. Rejected — that's not a meaningful cap (no positive-only configuration ever scores 5), and dispatch's clamp would silently allow `points=5` in the future, which would be wrong.

### D5 — `cli.py` becomes a `cli/` package with `__init__.py` re-exporting `main`, `app`, and the existing seven command callables

**Decision:** Convert `src/ohmystock/cli.py` to `src/ohmystock/cli/__init__.py`. Keep `main()`, the root `app = typer.Typer(...)`, and the seven existing commands here (no behavior change). Add `src/ohmystock/cli/_score.py` defining the new `score` subcommand group (`score_app = typer.Typer()`); `__init__.py` does `from ._score import score_app; app.add_typer(score_app, name="score")`.

**Why:** Three constraints: (1) `pyproject.toml` `[project.scripts]` is `ohmystock = "ohmystock.cli:main"` and we don't want to touch it; (2) every existing test imports `from ohmystock.cli import app` or runs `ohmystock --help`; (3) the new `score` group has its own option types, output formatting, and JSON/CSV branching that would bloat `cli.py` from ~140 lines to ~250+. A package with two files keeps each under ~150 lines and isolates the new feature.

**Alternative considered:** Add `score_app` inline in `cli.py`. Rejected — file-size growth, and harder to test the score command in isolation (the unit test would import the whole CLI module).

**Alternative considered:** Make `score` a flat `@app.command("score-watchlist")` instead of a Typer group. Rejected — the proposal commits to `ohmystock score watchlist ...` and a future `ohmystock score backtest-window` etc. is plausible enough that the group shape future-proofs naming.

### D6 — `score watchlist` output is CSV-by-default, JSON behind `--json`; sort by `final_score` descending; tie-broken by `symbol` ascending

**Decision:** Default output is CSV with header `symbol,final_score,classification,risk_off_applied,tech,chip,fund,sent`. With `--json`, the command prints the full envelope `{"ok": True, "elapsed_ms": ..., "data": {...}, "error": null}` (i.e., the raw return of `score_watchlist`). Rows are sorted by `final_score` descending, ties broken by `symbol` ascending. `--top-n` clamps the output to the first N rows after sorting.

**Why:** CSV is the smallest useful operator format — pipeable into `column -t -s,` or `awk` without parsing. The 8 fields are the operator-visible decision inputs (subtotals + classification + risk-off flag). JSON is offered for downstream tooling (e.g., a future `web-admin` dashboard pulling the envelope directly). Sort order is deterministic — necessary for `--top-n` correctness and for snapshot-style tests. Tie-break by `symbol` is the cheapest stable rule.

**Alternative considered:** Markdown table by default. Rejected — operators pipe to grep more often than they paste into chat; CSV wins on shell ergonomics.

**Alternative considered:** `--format csv|json|table`. Rejected — premature; two flags are simpler than an enum and we can grow the third later.

### D7 — Validation/internal errors from `score_watchlist` map to exit code 1; `error.code` and `error.message` print to stderr; stdout stays empty on the error path

**Decision:** When the engine returns `{"ok": False, "error": {...}}`, print `error: <code>: <message>` to stderr and `raise typer.Exit(1)`. Stdout is silent so a caller doing `ohmystock score watchlist ... > out.csv` doesn't get a half-written file on error.

**Why:** Standard Unix discipline (errors to stderr, exit 1, no partial stdout). The five existing stub commands also `exit 1` on the `not implemented` path, so this is consistent. The exact error code (`INVALID_INPUT`, `INTERNAL_ERROR`, etc.) is already defined by the engine's envelope contract — the CLI just renders it.

### D8 — Test surface: one parametric test for all 16 stubs, one CliRunner test for the score command, plus extensions to layout/reverse-import guards

**Decision:** Four test files touched:
- **NEW** `tests/test_deferred_stubs.py` — parametrized over `list_subscorers()` filtered to the 16 deferred names. Asserts `dispatch(name, ctx)` returns `status="skipped"`, `points=0`, `max_points` matches registration, `evidence["reason"]` is set.
- **NEW** `tests/test_cli_score_watchlist.py` — uses `typer.testing.CliRunner`. Three cases: (a) success with CSV output (header + ≥1 row, mocking `score_watchlist`), (b) `--json` echoes envelope verbatim, (c) `--asof` with bad format → stderr contains `INVALID_INPUT`, exit 1.
- **EDIT** `tests/test_subscorers_layout.py` — extend the existing layout assertion to also walk `subscorers/deferred/` and require one file per registered deferred stub (matching `name`).
- **EDIT** `tests/test_scoring_reverse_import.py` — verify by reading the test before editing whether the existing assertion already catches the deferred package; only extend if it currently checks specific symbols rather than the post-import `sys.modules` set.

**Why:** Parametrization keeps the deferred-stub coverage as one test case per stub without 16 hand-written test functions. CliRunner is the canonical way to test typer commands. Reusing the existing layout/reverse-import guards (rather than adding new ones) keeps the test count flat per sub-scorer added later.

## Risks / Trade-offs

- **[Risk]** Splitting `cli.py` into a package may break a hidden import path like `from ohmystock.cli import smoke_test` (function reference). → **Mitigation:** keep all existing function names in `cli/__init__.py` and re-export them; before merging, grep for `from ohmystock.cli import` across the repo and tests, fix any references.
- **[Risk]** Negative-band stubs (`borrow_change`, `search_heat`) registered with `max_points=2` will under-report their potential contribution by up to 3 points (borrow) and 2 points (heat). → **Mitigation:** documented in `evidence["reason"]`; the proposal flags it as out-of-scope; no operator decision today depends on these scorers being non-zero (they're stubs); replacing them is a single-file diff once the registry contract is reshaped.
- **[Risk]** A future stub addition (17th deferred sub-scorer) might forget to update `subscorers/deferred/__init__.py` and silently fail to register. → **Mitigation:** the extended `tests/test_subscorers_layout.py` walks the directory and asserts every `.py` file under `deferred/` (except `__init__.py`) corresponds to a registered name — file-without-registration trips the test.
- **[Risk]** `--json` output of the engine envelope leaks internal field names (`elapsed_ms`, full subscore evidence dicts) that may not be stable. → **Mitigation:** the engine envelope is *already* the contract; `score_watchlist`'s envelope shape is locked by `phase-2b-scoring-engine` Requirement "score_watchlist returns a standard envelope". `--json` re-emits the same shape — consumers depend on the engine contract, not the CLI.
- **[Trade-off]** Defaulting CSV without a `--format` enum means future operators wanting Markdown have to pipe through external tools or wait for a follow-up change. Worth it for now (YAGNI on the third format).
- **[Trade-off]** Fixed `evidence["reason"] = "data source not implemented"` is the same string for all 16 stubs. A future-real implementation will replace it with structured evidence (e.g., `{"window_days": 5, "broker_top1_share": 0.18}`). The shared placeholder string is easy to grep for during the promote-to-real diff.
