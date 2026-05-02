## MODIFIED Requirements

### Requirement: confirm() 函式：將 pending_confirm entry 變成 confirmed fill

系統 SHALL 在 `ohmystock.safety.confirm_gate` 模組提供函式 `confirm(conn, *, decision_id, broker, default_capital_twd, user, auto_executed=False, clock) -> ConfirmResult`，行為如下：

1. SHALL 以 `BEGIN IMMEDIATE` 開啟交易，避免並行 confirm 競爭。
2. SHALL 查詢 `journal_entries WHERE decision_id=? AND kind='entry'`，取最新一筆。
3. 若查無資料 → ROLLBACK，raise `ConfirmGateError`，attribute `code="not_found"`。
4. 若 `payload_json.decision_status != "pending_confirm"` → ROLLBACK，raise `ConfirmGateError`，`code="not_pending"`，message 含實際的 status 字串。
5. 從 payload 取 `final_sizing_pct`、`current_price`、`atr_14_pct`（皆從 entry payload 中的快照欄位，由 `decide_entry` 寫入）。若 payload 缺欄位 → ROLLBACK，raise `ConfirmGateError`，`code="payload_invalid"`。
6. 計算 `qty = max(1000, floor(default_capital_twd * (final_sizing_pct / 100) / current_price / 1000) * 1000)`。
7. 呼叫 `broker.submit_market_order(symbol=..., qty=qty, side="buy", reference_price=current_price)`。若 raise `BrokerError` → ROLLBACK，封裝為 `ConfirmGateError(code="broker_failed", cause=e)` re-raise。
8. **計算 ATR 與 stop_loss**（v0 normal-market case，per cheatsheet §6.6）：
   - `atr_at_entry = fill.fill_price * atr_14_pct / 100.0`（percent → TWD absolute）
   - `stop_loss_price = max(fill.fill_price * 0.94, fill.fill_price - 2.0 * atr_at_entry)`
9. UPDATE 同一筆 row 的 `payload_json`：set `decision_status="confirmed"`、`actual_entry_price=fill.fill_price`、`actual_qty=fill.filled_qty`、`atr_at_entry=<computed>`、`stop_loss_price=<computed>`、`human_confirmed_by=user`、`human_confirmed_at=clock.now_iso()`、**`auto_executed=<auto_executed 參數值>`**（新增；預設 False 維持人工 confirm 既有行為）。
10. COMMIT。回傳 `ConfirmResult(decision_id=..., fill=fill, qty=qty)`。

`ConfirmResult` SHALL 為 frozen dataclass `(decision_id: str, fill: Fill, qty: int)`。`ConfirmGateError` SHALL 為 Exception 子類，attribute `code: Literal["not_found","not_pending","payload_invalid","broker_failed"]`、可選 `cause: Exception | None`。

`auto_executed: bool = False` SHALL 為 keyword-only 參數，預設 `False`。當參數為 `False` 時 step 9 寫入 `auto_executed=False`，與 `confirm-gate-v0` 既有人工流程行為一致；當參數為 `True` 時 step 9 寫入 `auto_executed=True`，供 `auto-execute` capability 標記自動成交來源。

#### Scenario: confirm 成功 — UPDATE entry row 並回傳 ConfirmResult
- **GIVEN** in-memory SQLite 已跑 `init_schema(conn)` + `decide_entry(...)` 寫了一筆 `decision_id="dec_2026-05-02T10-00-00_2330"` 的 pending_confirm entry，payload `final_sizing_pct=16.5`、`current_price=832.0`、`atr_14_pct=2.85`
- **WHEN** 呼叫 `confirm(conn, decision_id="dec_2026-05-02T10-00-00_2330", broker=FakePaperBroker(clock=FakeClock("2026-05-02T10:15:00+08:00")), default_capital_twd=1_000_000, user="mark@local", clock=FakeClock("2026-05-02T10:15:00+08:00"))`
- **THEN** 回傳 `ConfirmResult(decision_id="dec_2026-05-02T10-00-00_2330", fill=Fill(symbol="2330", filled_qty=1000, fill_price=832.0, ...), qty=1000)`；查 `SELECT json_extract(payload_json, '$.decision_status'), json_extract(payload_json, '$.actual_entry_price'), json_extract(payload_json, '$.actual_qty'), json_extract(payload_json, '$.human_confirmed_by') FROM journal_entries WHERE decision_id=...` 結果為 `("confirmed", 832.0, 1000, "mark@local")`

#### Scenario: confirm 成功 — atr_at_entry 與 stop_loss_price 已計算填入
- **GIVEN** 同前 GIVEN（`fill.fill_price=832.0`、`atr_14_pct=2.85`）
- **WHEN** confirm 成功
- **THEN** 查 `SELECT json_extract(payload_json, '$.atr_at_entry'), json_extract(payload_json, '$.stop_loss_price') FROM journal_entries WHERE kind='entry'` 結果接近 `(23.712, 784.576)`（atr=832×2.85/100=23.712；stop=max(832×0.94, 832-2×23.712)=max(782.08, 784.576)=784.576）

#### Scenario: confirm 失敗 — payload 缺 atr_14_pct raise payload_invalid
- **GIVEN** entry payload 缺 `atr_14_pct` 欄位
- **WHEN** 呼叫 `confirm(...)`
- **THEN** raise `ConfirmGateError`，`exc.code == "payload_invalid"`，message 含 `"atr_14_pct"`；DB 中該 entry 仍為 pending_confirm

#### Scenario: confirm 失敗 — decision_id 不存在 raise not_found
- **WHEN** 呼叫 `confirm(conn, decision_id="dec_does_not_exist", ...)`
- **THEN** raise `ConfirmGateError`，`exc.code == "not_found"`；DB 無新增 row（RowCount 不變）

#### Scenario: confirm 失敗 — entry 已 confirmed raise not_pending
- **GIVEN** 一筆 entry 已被 confirm（status=confirmed）
- **WHEN** 對同一 decision_id 再次呼叫 `confirm(...)`
- **THEN** raise `ConfirmGateError`，`exc.code == "not_pending"`，message 含 `"confirmed"`

#### Scenario: confirm 失敗 — broker raise BrokerError 全部 rollback
- **GIVEN** pending entry 存在，broker = `FakePaperBroker(raise_on_submit=True)`
- **WHEN** 呼叫 `confirm(...)`
- **THEN** raise `ConfirmGateError`，`exc.code == "broker_failed"`，`exc.cause` 為 `BrokerError` 實例；DB 中該 entry 的 payload 仍為 `decision_status="pending_confirm"`（UPDATE 已 rollback）

#### Scenario: qty 計算 — 16.5% × 1M / 832 取整千股 = 1000
- **GIVEN** payload `final_sizing_pct=16.5`、`current_price=832.0`、`default_capital_twd=1_000_000`
- **WHEN** confirm 成功
- **THEN** `ConfirmResult.qty == 1000`（floor(165000/832/1000)*1000 = floor(0.198)*1000 = 0，再 max 1000）

#### Scenario: qty 計算 — 16.5% × 1M / 100 取整千股 = 1000
- **GIVEN** payload `final_sizing_pct=16.5`、`current_price=100.0`、`default_capital_twd=1_000_000`
- **WHEN** confirm 成功
- **THEN** `ConfirmResult.qty == 1000`（floor(165000/100/1000)*1000 = 1*1000 = 1000）

#### Scenario: qty 計算 — 25% × 1M / 50 取整千股 = 5000
- **GIVEN** payload `final_sizing_pct=25.0`、`current_price=50.0`、`default_capital_twd=1_000_000`
- **WHEN** confirm 成功
- **THEN** `ConfirmResult.qty == 5000`

#### Scenario: 預設 auto_executed 參數寫入 False
- **GIVEN** pending entry，呼叫 `confirm(...)` 不傳 `auto_executed` 參數
- **WHEN** confirm 成功
- **THEN** 查 `SELECT json_extract(payload_json, '$.auto_executed') FROM journal_entries WHERE kind='entry'` 為 `0`（SQLite 把 JSON `false` 存為 `0`）

#### Scenario: auto_executed=True 寫入 True
- **GIVEN** pending entry，呼叫 `confirm(..., auto_executed=True, user="auto", ...)`
- **WHEN** confirm 成功
- **THEN** 查 `SELECT json_extract(payload_json, '$.auto_executed'), json_extract(payload_json, '$.human_confirmed_by') FROM journal_entries WHERE kind='entry'` 為 `(1, "auto")`
