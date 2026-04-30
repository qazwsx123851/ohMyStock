## 1. 套件骨架與型別

- [x] 1.1 建立 `src/ohmystock/sepa/__init__.py`，re-export `evaluate_trend_template`、`classify_stage`、`is_stage_4_reject`、`TrendTemplateResult`、`ConditionOutcome`、`StageResult`、`InsufficientHistoryError`，並設 `__all__`
- [x] 1.2 建立 `src/ohmystock/sepa/types.py`：`@dataclass(frozen=True)` 定義 `ConditionOutcome(name: str, passed: bool | None, detail: str)`、`TrendTemplateResult(passed: bool, conditions: dict[str, ConditionOutcome], rs_percentile: float | None)`、`StageResult(stage: Literal[1,2,3,4], reason: str)`
- [x] 1.3 在 `types.py` 定義 `class InsufficientHistoryError(ValueError): pass`
- [x] 1.4 在 `types.py` / 模組常數區定義 `MIN_HISTORY = 252`、`MA200_SLOPE_WINDOW = 20`、`STAGE_3_RANGE_THRESHOLD = 0.20`、`RS_THRESHOLD = 65.0`、`HIGH_52W_DISCOUNT = 0.75`、`LOW_52W_PREMIUM = 1.30`

## 2. Trend Template — 共用內部 helper

- [x] 2.1 在 `src/ohmystock/sepa/trend_template.py` 建立 module docstring + `from ohmystock.indicators.core import sma` + `from ohmystock.data.sources.base import BarRow` + 對 `types.py` 的相對 import
- [x] 2.2 實作 `_validate_history(bars)`：`len(bars) < MIN_HISTORY` 即 raise `InsufficientHistoryError(f"need {MIN_HISTORY} bars, got {len(bars)}")`
- [x] 2.3 實作 `_compute_ma_stack(closes)` 內部 helper：回傳 `(ma50, ma150, ma200)` 三個 list，呼叫 `sma(closes, n)` 取得；保留 `None` 慣例
- [x] 2.4 實作 `_ma200_rising(ma200_series, window=MA200_SLOPE_WINDOW)`：檢查 `bars[-1]` 對應的 ma200 是否為非降序（`all(ma200[i] >= ma200[i-1])` 對最近 `window` 步），回傳 `(passed: bool, detail: str)`，detail 在失敗時指出哪一步斷掉

## 3. Trend Template — 8 個條件求值

- [x] 3.1 實作 `evaluate_trend_template(bars: list[BarRow], rs_percentile: float | None) -> TrendTemplateResult`：先呼叫 `_validate_history`；抽出 `closes = [b["c"] for b in bars]`、`last_close = closes[-1]`；呼叫 `_compute_ma_stack`
- [x] 3.2 評 c1：`last_close > ma50[-1]` → `ConditionOutcome("close > MA50", ..., f"close={last_close}, MA50={ma50[-1]}")`
- [x] 3.3 評 c2/c3/c4/c5：依 spec 定義組 `ConditionOutcome`，`detail` 帶當下數值
- [x] 3.4 評 c6：呼叫 `_ma200_rising(ma200)`；用其 `(passed, detail)` 組 `ConditionOutcome("MA200 monotonically non-decreasing for last 20 sessions", ...)`
- [x] 3.5 評 c7：`high_52w = max(b["h"] for b in bars[-252:])`；`passed = last_close >= high_52w * HIGH_52W_DISCOUNT`；detail 帶 `last_close`、`high_52w`、距高百分比
- [x] 3.6 評 c8：`low_52w = min(b["l"] for b in bars[-252:])`；若 `rs_percentile is None` → `ConditionOutcome("close ≥ 52W low × 1.30 AND RS Percentile ≥ 65", passed=None, detail="rs_percentile not provided")`；否則同時檢查 `last_close >= low_52w * LOW_52W_PREMIUM` 與 `rs_percentile >= RS_THRESHOLD`，detail 帶兩個分量
- [x] 3.7 組 `conditions = {"c1": ..., "c2": ..., ..., "c8": ...}`；`overall_passed = all(o.passed is True for o in conditions.values())`（注意 None → False）
- [x] 3.8 回傳 `TrendTemplateResult(passed=overall_passed, conditions=conditions, rs_percentile=rs_percentile)`

## 4. Stage classification

- [x] 4.1 在 `src/ohmystock/sepa/stage.py` 建立 module docstring + 同樣的 import 集
- [x] 4.2 實作 `_is_stage_4(last_close, ma50, ma150, ma200, ma200_series) -> tuple[bool, str]`：判斷 `ma50 < ma150 < ma200` AND `last_close < ma50` AND **NOT** `_ma200_rising(ma200_series)[0]`；回傳 `(matched, reason_string)`，reason 在 matched=True 時列出三個 clauses
- [x] 4.3 實作 `_is_stage_2_or_3(last_close, ma50, ma150, ma200, ma200_series, bars) -> tuple[Literal[2, 3, None], str]`：先檢查 `last_close > ma50 > ma150 > ma200` AND `_ma200_rising(...)[0]`；不通過回 `(None, "")`；通過則計算最近 30 bar 的 `range_pct = (max(h) - min(l)) / last_close`，`> STAGE_3_RANGE_THRESHOLD` → `(3, ...)`、否則 `(2, ...)`
- [x] 4.4 實作 `classify_stage(bars: list[BarRow]) -> StageResult`：先 `_validate_history`；組 `(ma50, ma150, ma200)`；先試 `_is_stage_4`，命中 → `StageResult(4, reason)`；否則試 `_is_stage_2_or_3`；都不命中 → `StageResult(1, "no Stage 2/3/4 pattern")`
- [x] 4.5 實作 `is_stage_4_reject(bars: list[BarRow]) -> bool`：`return classify_stage(bars).stage == 4`

## 5. 測試 — Trend Template

- [x] 5.1 建立 `tests/test_sepa_trend_template.py`，加 `_make_ramp_bars(n=252, start=100.0, end=200.0)` helper 製造 monotonic ramp（OHLC 都用同個值 + 微 1% 振幅）；加 `_make_decline_bars`、`_make_flat_bars`
- [x] 5.2 加 spec scenario 1 對應測試「All eight conditions pass on a synthetic Stage-2 ramp」：`evaluate_trend_template(_make_ramp_bars(), rs_percentile=80)` → `result.passed is True`、`set(result.conditions.keys()) == {"c1".."c8"}`、所有 `passed is True`
- [x] 5.3 加 c6-fails 測試：構造 ramp 但在 `bars[-2]` 的 ma200 故意比 `bars[-3]` 略低（用 closes 序列拼出來）→ `result.conditions["c6"].passed is False`、`result.passed is False`
- [x] 5.4 加 c7-fails 測試：ramp 但 `bars[-1]["c"]` 偏低（< 52w_high * 0.75）→ `result.conditions["c7"].passed is False`
- [x] 5.5 加 rs-percentile-None 測試：`evaluate_trend_template(ramp, rs_percentile=None)` → `result.conditions["c8"].passed is None`、其他條件保持 True/False（無 None）、`result.passed is False`
- [x] 5.6 加 history 錯誤測試：`evaluate_trend_template(ramp[:251], 80)` raise `InsufficientHistoryError`、`evaluate_trend_template([], 80)` 同樣 raise；`pytest.raises` 比對訊息含 "251" 與 "252"
- [x] 5.7 加 52W window 測試：構造 300 bar，前 50 bar 內塞 `h=500` 的尖峰，最近 252 bar max h = 200，當前 close=180 → c7 應對 200 計算（passed=True）而非對 500（會 fail）
- [x] 5.8 加 immutability 測試：`with pytest.raises(dataclasses.FrozenInstanceError): result.passed = True`

## 6. 測試 — Stage classification

- [x] 6.1 建立 `tests/test_sepa_stage.py` 並 import 步驟 5.1 的 fixture helpers（或抽到 `tests/conftest.py`）
- [x] 6.2 加 Stage-2 ramp 測試：`classify_stage(_make_ramp_bars())` → `result.stage == 2`、`"Stage 2" in result.reason`
- [x] 6.3 加 Stage-4 decline 測試：構造 200→100 的下跌 ramp 使 `MA50<MA150<MA200` 且 MA200 過去 20 步遞減 → `result.stage == 4`，reason 內含 "MA50<MA150<MA200" 等三 clauses 關鍵字
- [x] 6.4 加 Stage-3 高波動測試：先用 ramp 取得 Stage-2 mean-stack，再把最後 30 bar 改成 high 200 / low 150（range ~ 25%）→ `result.stage == 3`
- [x] 6.5 加 Stage-1 flat 測試：`_make_flat_bars(n=252, value=100, jitter=2)` → `result.stage == 1`
- [x] 6.6 加 `is_stage_4_reject` 三組測試：Stage 4 → True、Stage 2 → False、Stage 1 → False
- [x] 6.7 加 false-positive 防呆測試：構造 mean-stack 反向但 MA200 仍 monotonic rising 的 fixture（深拉回但長期上升）→ `result.stage != 4`、`is_stage_4_reject(bars) is False`
- [x] 6.8 加 history 錯誤測試：`classify_stage(bars[:251])` 與 `is_stage_4_reject(bars[:251])` 都 raise `InsufficientHistoryError`
- [x] 6.9 加 immutability 測試：`with pytest.raises(dataclasses.FrozenInstanceError): result.stage = 1`

## 7. 收尾

- [x] 7.1 執行 `uv run pytest tests/test_sepa_trend_template.py tests/test_sepa_stage.py -v` 全綠
- [x] 7.2 執行 `uv run pytest -q` 確認既有 30+ 測試無 regression
- [x] 7.3 在 `src/ohmystock/sepa/__init__.py` 與兩個模組頂端 docstring 標註 `Spec: openspec/changes/sepa-trend-template-and-stage/specs/{sepa-trend-template,sepa-stage-classification}/spec.md`
- [x] 7.4 commit：`feat(sepa): trend template (8 conds) + stage 1/2/3/4 classifier with hard-reject helper`
