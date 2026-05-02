## ADDED Requirements

### Requirement: ExitDecision / ExitResult 資料類別與 evaluate_position 純函式

系統 SHALL 在 `ohmystock.exit_engine.evaluator` 模組對外公開以下符號：

- `ExitTag`：`Literal["hit_stop_loss", "hit_t1", "time_stop"]`（v0 三選一；其餘 `hit_t1_5` / `chandelier` / `thesis_invalid` / `discretionary` 為未來 change 預留，本 capability 不實作）。
- `ExitDecision`：frozen dataclass `(exit_tag: ExitTag, exit_reason: str, actual_exit_price: float, pnl_pct: float, hold_days: int)`。
- `ExitResult`：frozen dataclass `(decision_id: str, action: Literal["closed","held"], decision: ExitDecision | None)`。
- `MarketDataLookup`：Protocol，唯一方法 `get_close(symbol: str, asof: date) -> float | None`（None 代表查無資料）。

系統 SHALL 提供純函式 `evaluate_position(entry_payload: dict, close_price: float, asof_date: date) -> ExitDecision | None`，行為如下：

1. 從 `entry_payload` 取 `actual_entry_price` (float)、`stop_loss_price` (float)、`expected_holding_days` (int)、`human_confirmed_at` (ISO-8601 字串)。若任一缺欄位或值非合法數值 → raise `ValueError`（呼叫者前置檢查；orchestrator 會把這個包成 SkipResult）。
2. 計算 `entry_dt = datetime.fromisoformat(human_confirmed_at).date()`、`hold_days = (asof_date - entry_dt).days`。
3. 依以下順序檢查觸發條件：
   - 若 `close_price <= stop_loss_price` → 回 `ExitDecision("hit_stop_loss", reason=f"close {close_price} ≤ stop_loss {stop_loss_price}", actual_exit_price=close_price, pnl_pct=_pnl(close_price, actual_entry_price), hold_days=hold_days)`
   - 若 `close_price >= actual_entry_price * 1.06` → 回 `ExitDecision("hit_t1", reason=f"close {close_price} ≥ T1 {actual_entry_price * 1.06}", actual_exit_price=close_price, pnl_pct=_pnl(close_price, actual_entry_price), hold_days=hold_days)`
   - 若 `hold_days >= expected_holding_days * 2` → 回 `ExitDecision("time_stop", reason=f"hold_days {hold_days} ≥ {expected_holding_days * 2}", actual_exit_price=close_price, pnl_pct=_pnl(close_price, actual_entry_price), hold_days=hold_days)`
4. 若皆未觸發 → 回 `None`。

`_pnl(close, entry) = (close - entry) / entry * 100.0`。

#### Scenario: hit_stop_loss 觸發
- **GIVEN** `entry_payload={"actual_entry_price": 832.0, "stop_loss_price": 784.58, "expected_holding_days": 8, "human_confirmed_at": "2026-05-02T10:15:00+08:00"}`，`close_price=780.0`，`asof_date=date(2026, 5, 5)`
- **WHEN** 呼叫 `evaluate_position(...)`
- **THEN** 回 `ExitDecision(exit_tag="hit_stop_loss", actual_exit_price=780.0, pnl_pct=≈-6.25, hold_days=3)`，`exit_reason` 含字面 `"stop_loss"`

#### Scenario: hit_t1 觸發
- **GIVEN** 同 entry payload，`close_price=900.0`（≥ 832 × 1.06 = 881.92），`asof_date=date(2026, 5, 7)`
- **WHEN** 呼叫 `evaluate_position(...)`
- **THEN** 回 `ExitDecision(exit_tag="hit_t1", actual_exit_price=900.0, pnl_pct=≈8.17, hold_days=5)`

#### Scenario: time_stop 觸發
- **GIVEN** 同 entry payload (expected_holding_days=8 → time_stop @ 16 days)，`close_price=850.0`（未觸 stop 也未觸 T1），`asof_date=date(2026, 5, 22)`（hold_days=20 ≥ 16）
- **WHEN** 呼叫 `evaluate_position(...)`
- **THEN** 回 `ExitDecision(exit_tag="time_stop", actual_exit_price=850.0, pnl_pct=≈2.16, hold_days=20)`

#### Scenario: hold (未觸發任何條件)
- **GIVEN** 同 entry payload，`close_price=850.0`（未觸 stop 也未觸 T1），`asof_date=date(2026, 5, 7)`（hold_days=5 < 16）
- **WHEN** 呼叫 `evaluate_position(...)`
- **THEN** 回 `None`

#### Scenario: 同時觸發 stop + T1 → stop 優先（D5）
- **GIVEN** 假設性 close_price 同時 ≤ stop_loss 與 ≥ T1（實務上不可能，但 spec 必須 deterministic）
- **WHEN** 呼叫 `evaluate_position(...)`
- **THEN** 回 `ExitDecision(exit_tag="hit_stop_loss", ...)`（D5：downside protection 優先）

#### Scenario: payload 缺 stop_loss_price raise ValueError
- **GIVEN** `entry_payload={"actual_entry_price": 832.0, "expected_holding_days": 8, "human_confirmed_at": "..."}` （缺 `stop_loss_price`）
- **WHEN** 呼叫 `evaluate_position(...)`
- **THEN** raise `ValueError`，message 含 `"stop_loss_price"`

---

### Requirement: evaluate_open_positions orchestrator 寫入 kind=exit + 翻 entry status

系統 SHALL 在 `ohmystock.exit_engine.evaluator` 提供 `evaluate_open_positions(conn, *, market_data, asof, clock, symbol_filter=None) -> list[ExitResult]`，行為如下：

1. 查 `SELECT decision_id, symbol, payload_json FROM journal_entries WHERE kind='entry' AND json_extract(payload_json, '$.decision_status')='confirmed'`。若 `symbol_filter` 非 None，加 `AND symbol=?`。
2. 對每筆 row：
   - 解析 `payload_json` 為 dict。
   - 呼叫 `market_data.get_close(symbol, asof)`；若回 None → 收集到 `failed_lookups: list[str]`，**不**寫入 / 不評估。
   - 呼叫 `evaluate_position(payload, close_price, asof)`。若 raise `ValueError` → 收集到 `payload_errors: list[str]`，跳過。
   - 若 `evaluate_position` 回 None → 收集 `ExitResult(decision_id, action="held", decision=None)`，繼續。
   - 若回 `ExitDecision` → 開 `BEGIN IMMEDIATE`：
     - INSERT `kind=exit` row，payload 含 `exit_tag`, `exit_reason`, `actual_exit_price`, `pnl_pct`, `hold_days`, `exited_at=clock.now_iso()`, `close_price_evaluated=close_price`。
     - UPDATE entry row 的 `payload_json` set `decision_status="closed"`。
     - COMMIT。
     - 收集 `ExitResult(decision_id, action="closed", decision=...)`。
3. 若 `failed_lookups` 非空 → raise `ExitEngineError(code="market_data_unavailable", failed_symbols=...)`，**所有已寫入的 commits 不 rollback**（per-position transaction 已 commit；後續 symbol 跳過）。
4. 回 `list[ExitResult]` （順序為 SELECT 順序）。

`ExitEngineError` SHALL 為 Exception 子類，attribute `code: Literal["market_data_unavailable"]`、`failed_symbols: list[str]`。

#### Scenario: 一筆 confirmed entry hit T1 → 寫 kind=exit + entry status=closed
- **GIVEN** in-memory SQLite 有一筆 `decision_id="dec_X"`、`symbol="2330"` 的 confirmed entry，`actual_entry_price=832.0`，`stop_loss_price=784.58`，`expected_holding_days=8`，`human_confirmed_at="2026-05-02T10:15:00+08:00"`；`market_data.get_close("2330", date(2026,5,7)) == 900.0`
- **WHEN** 呼叫 `evaluate_open_positions(conn, market_data=..., asof=date(2026,5,7), clock=FakeClock("2026-05-07T13:30:00+08:00"))`
- **THEN** 回傳 list 長度 1，元素 `action="closed"`、`decision.exit_tag="hit_t1"`；DB 中 `decision_id="dec_X"` 的 entry row `decision_status="closed"`；新增一筆 `kind=exit` row `decision_id="dec_X"`、`symbol="2330"`，payload `exit_tag="hit_t1"`、`actual_exit_price=900.0`、`exited_at="2026-05-07T13:30:00+08:00"`

#### Scenario: 一筆 confirmed entry 未觸發任何條件 → 不寫入，回 action=held
- **GIVEN** 同前 entry，`market_data.get_close(...) == 850.0`，`asof=date(2026,5,5)`（hold_days=3）
- **WHEN** 呼叫 `evaluate_open_positions(...)`
- **THEN** 回傳 list 長度 1，元素 `action="held"`；DB 中無新 row，entry status 仍為 `"confirmed"`

#### Scenario: 兩筆 entry，一筆 hit T1、一筆 held
- **GIVEN** 兩筆 confirmed entry (`dec_A` for `2330`, `dec_B` for `2317`)，市場 lookup 回 `2330=900, 2317=850`，`asof=date(2026,5,7)`
- **WHEN** 呼叫 `evaluate_open_positions(...)`
- **THEN** 回傳 list 長度 2；`dec_A` 為 closed (hit_t1)；`dec_B` 為 held；DB 中只有 `dec_A` 多了 `kind=exit` row

#### Scenario: market_data lookup 失敗 → raise ExitEngineError 並列出失敗 symbol
- **GIVEN** 兩筆 confirmed entry，`market_data.get_close("2317", ...)` 回 None
- **WHEN** 呼叫 `evaluate_open_positions(...)`
- **THEN** raise `ExitEngineError`，`exc.code == "market_data_unavailable"`，`exc.failed_symbols == ["2317"]`；其他可成功評估的 symbol（如 2330）已 commit（不 rollback）

#### Scenario: 已 closed 的 entry 不再被評估
- **GIVEN** 一筆 `decision_status="closed"` 的 entry
- **WHEN** 呼叫 `evaluate_open_positions(...)`
- **THEN** 回傳 list 長度 0；DB 無變動

#### Scenario: symbol_filter 限定單一 symbol
- **GIVEN** 兩筆 confirmed entry (2330, 2317)
- **WHEN** 呼叫 `evaluate_open_positions(conn, ..., symbol_filter="2330")`
- **THEN** 回傳 list 長度至多 1，且只含 `2330` 的結果

---

### Requirement: 模組對外 API 透過 `__init__.py` re-export

系統 SHALL 在 `src/ohmystock/exit_engine/__init__.py` re-export 公開符號：`evaluate_position`、`evaluate_open_positions`、`ExitDecision`、`ExitResult`、`ExitTag`、`ExitEngineError`、`MarketDataLookup`。

#### Scenario: from ohmystock.exit_engine import 公開符號可用
- **WHEN** 執行 `from ohmystock.exit_engine import evaluate_position, evaluate_open_positions, ExitDecision, ExitResult, ExitEngineError, MarketDataLookup`
- **THEN** import 成功，所有符號可呼叫 / 可實例化
