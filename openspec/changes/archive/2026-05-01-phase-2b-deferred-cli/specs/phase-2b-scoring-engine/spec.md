## MODIFIED Requirements

### Requirement: Sub-scorer file layout under `subscorers/` package

The package `ohmystock.scoring` SHALL contain a sub-package `ohmystock.scoring.subscorers` with one Python module per registered sub-scorer. Each module SHALL define exactly one function decorated with `@register_subscorer(...)`. The package's `__init__.py` SHALL explicitly import each sub-scorer module so that registration happens at package import time. Deferred-stub sub-scorers SHALL live in a nested sub-package `ohmystock.scoring.subscorers.deferred` with the same one-file-per-sub-scorer rule, and `subscorers/__init__.py` SHALL import the `deferred` sub-package (`from . import deferred  # noqa: F401`). The top-level `ohmystock/scoring/__init__.py` SHALL import `ohmystock.scoring.subscorers` (replacing the prior `_placeholder` import). Sub-scorer modules — including those under `deferred/` — MUST NOT import `fastapi`, `uvicorn`, `starlette`, or any I/O-performing module beyond `ohmystock.indicators`, `ohmystock.scoring.context`, `ohmystock.scoring.models`, and `ohmystock.scoring.registry`.

#### Scenario: Subscorers package is importable
- **WHEN** `import ohmystock.scoring.subscorers` runs
- **THEN** the import succeeds without `ImportError` and `list_subscorers()` includes every sub-scorer registered in this change

#### Scenario: Sub-scorer modules are pure
- **WHEN** any module under `ohmystock/scoring/subscorers/*.py` or `ohmystock/scoring/subscorers/deferred/*.py` is imported
- **THEN** it does not pull `fastapi`, `uvicorn`, or `starlette` into `sys.modules`

#### Scenario: Deferred sub-package is importable and auto-loaded
- **WHEN** `import ohmystock.scoring` runs from a fresh interpreter
- **THEN** `ohmystock.scoring.subscorers.deferred` is in `sys.modules` and `list_subscorers()` includes the names of all 16 deferred stubs registered in this change

#### Scenario: One file per deferred stub
- **WHEN** the directory `src/ohmystock/scoring/subscorers/deferred/` is enumerated
- **THEN** every `.py` file other than `__init__.py` corresponds 1-to-1 with a sub-scorer name registered from the `deferred` sub-package (file `<name>.py` ↔ registered name `<name>`)

---

## ADDED Requirements

### Requirement: Deferred-stub sub-scorers register with `status="skipped"`

The system SHALL register 16 deferred-stub sub-scorers under `ohmystock.scoring.subscorers.deferred`, each as a pure `(ScoringContext) -> SubScoreResult` function decorated with `@register_subscorer(category, name, max_points)`. Every deferred stub SHALL return a `SubScoreResult` with `status="skipped"`, `points=0`, `evidence={"reason": <non-empty str>}`, and `error_message=None`. The 16 stubs and their `(category, name, max_points)` registrations SHALL be exactly:

- **technical:** `kline_patterns` (8), `rs_percentile` (7).
- **chip:** `broker_concentration` (7), `futures_oi` (3), `margin_tightening` (2), `tdcc_concentration` (2), `borrow_change` (2).
- **fundamental:** `eps_yoy` (8), `eps_qoq` (5), `monthly_revenue_yoy` (6), `quarterly_revenue_yoy` (3), `institutional_30d_holding` (3).
- **sentiment:** `analyst_target_upgrades` (3), `sue` (3), `important_announcements` (2), `search_heat` (2).

Stubs MUST NOT raise, MUST NOT perform I/O, and MUST NOT inspect `ScoringContext` fields beyond what is necessary to construct the return value (which is none). The `evidence["reason"]` value SHALL be `"data source not implemented"` for stubs whose data source is simply absent, and SHALL include the substring `"negative-band scoring requires registry contract change"` for `borrow_change` and `search_heat` (whose documented bands extend below zero — `borrow_change`: `-3..+2`; `search_heat`: `-2..+2` — and whose registered `max_points=2` only covers the positive-band ceiling).

#### Scenario: All 16 deferred stubs are registered
- **WHEN** `import ohmystock.scoring` runs from a fresh interpreter and `list_subscorers()` is called
- **THEN** the result contains exactly these 16 deferred names with the listed `(name, category, max_points)` tuples: `("kline_patterns", "technical", 8)`, `("rs_percentile", "technical", 7)`, `("broker_concentration", "chip", 7)`, `("futures_oi", "chip", 3)`, `("margin_tightening", "chip", 2)`, `("tdcc_concentration", "chip", 2)`, `("borrow_change", "chip", 2)`, `("eps_yoy", "fundamental", 8)`, `("eps_qoq", "fundamental", 5)`, `("monthly_revenue_yoy", "fundamental", 6)`, `("quarterly_revenue_yoy", "fundamental", 3)`, `("institutional_30d_holding", "fundamental", 3)`, `("analyst_target_upgrades", "sentiment", 3)`, `("sue", "sentiment", 3)`, `("important_announcements", "sentiment", 2)`, `("search_heat", "sentiment", 2)`

#### Scenario: dispatch on any deferred stub returns skipped + zero points
- **GIVEN** a fresh registry with the deferred sub-package imported and any constructed `ScoringContext`
- **WHEN** `dispatch(<deferred_name>, ctx)` is called for any of the 16 deferred names
- **THEN** the returned `SubScoreResult` has `status == "skipped"`, `points == 0`, `max_points` equal to the registered cap, `evidence["reason"]` is a non-empty string, and `error_message is None`

#### Scenario: Negative-band stubs annotate the registry-contract gap
- **WHEN** `dispatch("borrow_change", ctx)` or `dispatch("search_heat", ctx)` is called
- **THEN** the returned `SubScoreResult.evidence["reason"]` contains the substring `"negative-band scoring requires registry contract change"`

#### Scenario: Deferred stubs do not raise
- **WHEN** any deferred stub is dispatched with a `ScoringContext` whose `bars`, `three_major`, and `margin_short` are all empty lists
- **THEN** dispatch completes without raising and the result has `status == "skipped"` (NOT `"error"`)

#### Scenario: Engine envelope includes deferred stubs in subscores
- **WHEN** `score_watchlist("2026-04-30", ["2330"])` is called and all data fetchers return `ok=True`
- **THEN** the returned envelope's `data["candidates"][0]["subscores"]` contains exactly 22 entries (6 real + 16 deferred); the 16 deferred entries have `status == "skipped"` and contribute 0 to all category subtotals

#### Scenario: Deferred stubs respect category-cap aggregation
- **WHEN** the engine aggregates final score and the 16 deferred stubs are present alongside the 6 real sub-scorers
- **THEN** the four category subtotals are computed only from `status == "scored"` entries; the deferred stubs (all `status == "skipped"`) MUST NOT contribute even their 0 points to any subtotal sum, and `final_score` equals the sum of real sub-scorer points (capped per category)
