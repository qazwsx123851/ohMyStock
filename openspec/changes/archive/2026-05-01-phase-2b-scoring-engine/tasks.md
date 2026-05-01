## 1. Package skeleton

- [x] 1.1 Create `src/ohmystock/scoring/__init__.py` (empty for now — re-exports come in 7.2) and confirm `ohmystock.scoring` imports cleanly via `python -c "import ohmystock.scoring"`
- [x] 1.2 Add `tests/test_scoring_reverse_import.py` — subprocess test that imports `ohmystock.scoring` and asserts `fastapi` / `uvicorn` / `starlette` are NOT in `sys.modules`. Run; expect PASS even at this stage (skeleton is empty)

## 2. Pydantic models (TDD: tests first)

- [x] 2.1 Write `tests/test_scoring_models.py` covering: `SubScoreResult` valid construction; `category` literal rejects `"other"`; `status` literal rejects `"bogus"`; `evidence` defaults to `{}`; `error_message` defaults to `None`; `Phase2BCandidate` valid construction with empty `subscores`; `classification` literal rejects `"blue"`; `subscores` accepts a list of `SubScoreResult`. Run; expect FAIL (module missing)
- [x] 2.2 Create `src/ohmystock/scoring/models.py` with `SubScoreResult` and `Phase2BCandidate` Pydantic v2 models per spec Requirement 3. Use `Literal[...]` for `category` / `status` / `classification`. Run `pytest tests/test_scoring_models.py -v`; expect PASS

## 3. ScoringContext dataclass

- [x] 3.1 Write `tests/test_scoring_context.py` — construct a `ScoringContext` with literal `bars=[]`, `three_major=[]`, `margin_short=[]`; assert frozen (mutating raises `dataclasses.FrozenInstanceError`); assert fields `asof_date`, `symbol`, `bars`, `three_major`, `margin_short` exist with the right types. Run; expect FAIL
- [x] 3.2 Create `src/ohmystock/scoring/context.py` with `@dataclass(frozen=True) class ScoringContext` containing `asof_date: str`, `symbol: str`, `bars: list[dict]`, `three_major: list[dict]`, `margin_short: list[dict]`. Run `pytest tests/test_scoring_context.py -v`; expect PASS

## 4. Sub-scorer registry (TDD)

- [x] 4.1 Write `tests/test_scoring_registry.py` covering: registration via decorator adds to `list_subscorers()`; duplicate name raises `ValueError("already registered: <name>")`; `dispatch(name, ctx)` invokes the registered function; `dispatch` overwrites `name` / `category` / `max_points` from registry metadata; `dispatch` clamps `points` to `[0, max_points]` (negative → 0, over-max → max_points); `list_subscorers()` returns entries sorted alphabetically by `name`; `_reset_registry()` clears state; missing-name `dispatch` raises `KeyError`. Use `_reset_registry()` in a `pytest.fixture(autouse=True)` for the test module. Run; expect FAIL
- [x] 4.2 Create `src/ohmystock/scoring/registry.py` with module-level `_REGISTRY: dict[str, tuple[Callable, str, float]]`, `register_subscorer(category, name, max_points)` decorator, `dispatch(name, ctx)`, `list_subscorers()`, and `_reset_registry()`. `dispatch` MUST construct a new `SubScoreResult` (do not mutate the function's return) with overwritten metadata and clamped points. Run `pytest tests/test_scoring_registry.py -v`; expect PASS

## 5. Engine: validation + envelope (TDD)

- [x] 5.1 Write `tests/test_scoring_engine_validation.py` covering each `INVALID_INPUT` scenario from spec Requirement 2: `asof_date` wrong format, `asof_date` not parseable, empty `candidates`, malformed candidate symbol, `top_n=True` (bool guard), `top_n=0`, `risk_off_resolver` not callable. Each asserts envelope shape `{"ok": False, "data": None, "error": {"code": "INVALID_INPUT", "message": <contains keyword>, "retriable": False}}` and `elapsed_ms >= 0`. Run; expect FAIL
- [x] 5.2 Create `src/ohmystock/scoring/_engine.py` with `score_watchlist(asof_date, candidates, *, risk_off_resolver=lambda: False, top_n=None, _conn=None, _today=None)` skeleton: error codes (`INVALID_INPUT`, `DATA_UNAVAILABLE`, `INTERNAL_ERROR`), `_validate_inputs(...)` helper, `_success_envelope(...)` and `_error_envelope(...)` helpers (mirror style of `data/market_data.py`). For now the success path returns `data={"candidates": []}`. Run `pytest tests/test_scoring_engine_validation.py -v`; expect PASS

## 6. Engine: context loading + dispatch + aggregation (TDD)

- [x] 6.1 Write `tests/test_scoring_engine_aggregate.py` covering: registered sub-scorers (mocked via `_reset_registry()` + ad-hoc decorator) producing `tech=30, chip=20, fund=15, sent=5` ⇒ `final_score == 70`; `tech=50` ⇒ `tech_subtotal == 40`; `chip` summing to `-3` ⇒ `chip_subtotal == 0`; mix of `scored`/`skipped`/`error` ⇒ only `scored` counts; sub-scorer raising `RuntimeError("boom")` ⇒ `SubScoreResult(status="error", points=0, error_message contains "boom")` is in `subscores`; `risk_off_resolver()` invoked exactly once for 5 candidates; resolver `True` + score `70` ⇒ `final_score == 50`, `risk_off_applied == True`, `classification == "yellow"`; resolver `False` + `70` ⇒ `green`; resolver `True` + `30` ⇒ `red`; tie-break sort `["2330", "2317"]` both at `60` places `2317` first; `top_n=2` truncates after sort; `top_n=None` returns all. Use mocks (`unittest.mock.patch`) on `get_kline` / `get_three_major_investors` / `get_margin_short` to return synthetic `ok=True` envelopes. Run; expect FAIL
- [x] 6.2 Implement context loading in `_engine.py`: for each candidate, call `get_kline(symbol, period="1d", bars=250, end_date=asof_date, _conn=_conn, _today=_today)`, `get_three_major_investors(symbol, days=30, end_date=asof_date, _conn=_conn, _today=_today)`, `get_margin_short(symbol, days=30, end_date=asof_date, _conn=_conn, _today=_today)`. On `ok=False` use empty list for that source. Build `ScoringContext`
- [x] 6.3 Implement dispatch + aggregation in `_engine.py`: iterate `list_subscorers()`, call `dispatch(name, ctx)` wrapped in `try/except` (sub-scorer exceptions → `SubScoreResult(status="error", points=0, error_message=str(exc))`); group by category; per-category `subtotal = max(0, min(cap, sum(scored points)))` with caps `{technical:40, chip:25, fundamental:25, sentiment:10}`; `final_score = min(100, sum_of_subtotals)`
- [x] 6.4 Implement Risk-Off + classification + sort + truncation in `_engine.py`: call `risk_off_resolver()` once before the per-candidate loop; cap `final_score` to 50 when on; classify `green/yellow/red` per Requirement 6; sort `(−final_score, symbol)`; truncate to `top_n` if given. Wrap the entire body in `try/except Exception` translating to `INTERNAL_ERROR`. Run `pytest tests/test_scoring_engine_aggregate.py -v`; expect PASS

## 7. Placeholder sub-scorer + package re-exports

- [x] 7.1 Create `src/ohmystock/scoring/_placeholder.py` defining `_always_zero_placeholder(ctx) -> SubScoreResult` registered via `@register_subscorer("technical", "_always_zero_placeholder", 0)` returning `SubScoreResult(name="_always_zero_placeholder", category="technical", points=0, max_points=0, status="scored", evidence={"placeholder": True})`
- [x] 7.2 Update `src/ohmystock/scoring/__init__.py` to re-export `score_watchlist`, `Phase2BCandidate`, `SubScoreResult`, and import `_placeholder` after `registry` so registration runs at import time. Order matters: `from .models import ...` → `from .registry import ...` → `from . import _placeholder` → `from ._engine import score_watchlist`
- [x] 7.3 Write `tests/test_scoring_placeholder.py` — `import ohmystock.scoring`; assert `("_always_zero_placeholder", "technical", 0)` is in `list_subscorers()`; assert `dispatch("_always_zero_placeholder", ctx).evidence == {"placeholder": True}`. Run; expect PASS

## 8. End-to-end engine test with real placeholder

- [x] 8.1 Write `tests/test_scoring_engine_e2e.py` — patch `get_kline` / `get_three_major_investors` / `get_margin_short` to return `ok=True` envelopes; call `score_watchlist("2026-04-30", ["2330"])`; assert `ok=True`, `data["candidates"]` length 1, `subscores` contains the placeholder entry, `final_score == 0`, `classification == "red"`, `risk_off_applied == False`. Run; expect PASS

## 9. Reverse-import + final validation

- [x] 9.1 Re-run `tests/test_scoring_reverse_import.py` after all implementation lands. Run; expect PASS
- [x] 9.2 Run full scoring suite: `pytest tests/test_scoring_*.py -v` — expect all green
- [x] 9.3 Run full repo suite: `pytest` — no regressions in pre-existing tests
- [x] 9.4 Run `openspec validate change phase-2b-scoring-engine --strict` — clean
