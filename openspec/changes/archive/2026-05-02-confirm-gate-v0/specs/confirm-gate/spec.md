## ADDED Requirements

### Requirement: PaperBroker Protocol 與 FakePaperBroker 預設實作

系統 SHALL 在 `ohmystock.paper.broker` 模組對外公開以下符號：

- `PaperBroker`：Protocol，唯一方法 `submit_market_order(symbol: str, qty: int, side: Literal["buy"], reference_price: float) -> Fill`。
- `Fill`：dataclass `(symbol: str, side: Literal["buy"], requested_qty: int, filled_qty: int, fill_price: float, fill_ts: str)`，`fill_ts` 為 ISO-8601 含 `+08:00` 偏移。
- `FakePaperBroker`：預設實作，`__init__(clock)` 接受可注入時鐘；`submit_market_order(...)` 永遠成功，`filled_qty == qty`，`fill_price == reference_price`，`fill_ts` 來自 `clock.now_iso()`。
- `BrokerError`：例外，`PaperBroker` 實作 SHALL 在 broker 層失敗時 raise；`FakePaperBroker` 預設不會 raise，但 SHALL 提供 `__init__(..., raise_on_submit: bool = False)` 旗標供測試強制失敗（raise `BrokerError`）。

#### Scenario: FakePaperBroker 正常 fill 回 Fill 物件
- **GIVEN** `FakePaperBroker(clock=FakeClock("2026-05-02T10:15:00+08:00"))`
- **WHEN** 呼叫 `broker.submit_market_order(symbol="2330", qty=2000, side="buy", reference_price=832.0)`
- **THEN** 回傳 `Fill(symbol="2330", side="buy", requested_qty=2000, filled_qty=2000, fill_price=832.0, fill_ts="2026-05-02T10:15:00+08:00")`

#### Scenario: FakePaperBroker raise_on_submit=True 拋 BrokerError
- **GIVEN** `FakePaperBroker(clock=..., raise_on_submit=True)`
- **WHEN** 呼叫 `broker.submit_market_order(...)`
- **THEN** raise `BrokerError`，message 含 `"forced failure"` 字串

---

### Requirement: confirm() 函式：將 pending_confirm entry 變成 confirmed fill

系統 SHALL 在 `ohmystock.safety.confirm_gate` 模組提供函式 `confirm(conn, *, decision_id, broker, default_capital_twd, user, clock) -> ConfirmResult`，行為如下：

1. SHALL 以 `BEGIN IMMEDIATE` 開啟交易，避免並行 confirm 競爭。
2. SHALL 查詢 `journal_entries WHERE decision_id=? AND kind='entry'`，取最新一筆。
3. 若查無資料 → ROLLBACK，raise `ConfirmGateError`，attribute `code="not_found"`。
4. 若 `payload_json.decision_status != "pending_confirm"` → ROLLBACK，raise `ConfirmGateError`，`code="not_pending"`，message 含實際的 status 字串。
5. 從 payload 取 `final_sizing_pct`、`current_price`（從 entry payload 中的快照欄位，由 `decide_entry` 寫入）。若 payload 缺欄位 → ROLLBACK，raise `ConfirmGateError`，`code="payload_invalid"`。
6. 計算 `qty = max(1000, floor(default_capital_twd * (final_sizing_pct / 100) / current_price / 1000) * 1000)`。
7. 呼叫 `broker.submit_market_order(symbol=..., qty=qty, side="buy", reference_price=current_price)`。若 raise `BrokerError` → ROLLBACK，封裝為 `ConfirmGateError(code="broker_failed", cause=e)` re-raise。
8. UPDATE 同一筆 row 的 `payload_json`：set `decision_status="confirmed"`、`actual_entry_price=fill.fill_price`、`actual_qty=fill.filled_qty`、`human_confirmed_by=user`、`human_confirmed_at=clock.now_iso()`。
9. COMMIT。回傳 `ConfirmResult(decision_id=..., fill=fill, qty=qty)`。

`ConfirmResult` SHALL 為 frozen dataclass `(decision_id: str, fill: Fill, qty: int)`。`ConfirmGateError` SHALL 為 Exception 子類，attribute `code: Literal["not_found","not_pending","payload_invalid","broker_failed"]`、可選 `cause: Exception | None`。

#### Scenario: confirm 成功 — UPDATE entry row 並回傳 ConfirmResult
- **GIVEN** in-memory SQLite 已跑 `init_schema(conn)` + `decide_entry(...)` 寫了一筆 `decision_id="dec_2026-05-02T10-00-00_2330"` 的 pending_confirm entry，payload `final_sizing_pct=16.5`、`current_price=832.0`
- **WHEN** 呼叫 `confirm(conn, decision_id="dec_2026-05-02T10-00-00_2330", broker=FakePaperBroker(clock=FakeClock("2026-05-02T10:15:00+08:00")), default_capital_twd=1_000_000, user="mark@local", clock=FakeClock("2026-05-02T10:15:00+08:00"))`
- **THEN** 回傳 `ConfirmResult(decision_id="dec_2026-05-02T10-00-00_2330", fill=Fill(symbol="2330", filled_qty=1000, fill_price=832.0, ...), qty=1000)`；查 `SELECT json_extract(payload_json, '$.decision_status'), json_extract(payload_json, '$.actual_entry_price'), json_extract(payload_json, '$.actual_qty'), json_extract(payload_json, '$.human_confirmed_by') FROM journal_entries WHERE decision_id=...` 結果為 `("confirmed", 832.0, 1000, "mark@local")`

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

---

### Requirement: reject() 函式：人工拒絕寫 reject_layer=human + 翻 entry status

系統 SHALL 在 `ohmystock.safety.confirm_gate` 提供函式 `reject(conn, *, decision_id, reason, user, clock) -> RejectResult`，行為如下：

1. SHALL 以 `BEGIN IMMEDIATE` 開啟交易。
2. 查 entry row（同 confirm 步驟 2）；若不存在 → raise `ConfirmGateError(code="not_found")`；若狀態非 pending_confirm → raise `ConfirmGateError(code="not_pending")`。
3. INSERT 新 `kind=reject` row：`decision_id=...`，`symbol=` entry 的 symbol，`created_at=clock.now_iso()`，`payload_json` 含 `decision_status="rejected"`、`reject_layer="human"`、`reject_reason=reason`、`rejected_by=user`、`rejected_at=clock.now_iso()`。`reason` SHALL 非空字串；空字串時 raise `ValueError`（呼叫者前置檢查）。
4. UPDATE 原 entry row 的 `payload_json` set `decision_status="rejected"`。
5. COMMIT。回傳 `RejectResult(decision_id=..., reject_row_id=...)`。

#### Scenario: reject 成功 — 新增 kind=reject row 並翻 entry status
- **GIVEN** in-memory SQLite + 一筆 pending entry `decision_id="dec_X"`
- **WHEN** 呼叫 `reject(conn, decision_id="dec_X", reason="盤勢不對", user="mark", clock=FakeClock("2026-05-02T10:20:00+08:00"))`
- **THEN** 回傳 `RejectResult(...)`；查 `SELECT COUNT(*) FROM journal_entries WHERE decision_id="dec_X" AND kind="reject"` 為 1；新 reject row 的 `json_extract(payload_json, '$.reject_layer')` 為 `"human"`；原 entry row 的 `json_extract(payload_json, '$.decision_status')` 為 `"rejected"`

#### Scenario: reject 失敗 — entry 已 confirmed raise not_pending
- **GIVEN** entry 已 confirm
- **WHEN** 呼叫 `reject(conn, decision_id="dec_X", reason="too late", ...)`
- **THEN** raise `ConfirmGateError(code="not_pending")`；DB 中無新 reject row（COUNT 不變）

#### Scenario: reject 空 reason raise ValueError
- **WHEN** 呼叫 `reject(conn, decision_id="dec_X", reason="", ...)`
- **THEN** raise `ValueError`，message 含 `"reason"`

---

### Requirement: sweep_expired() 函式：將 timeout 的 pending entry 寫 expire row

系統 SHALL 在 `ohmystock.safety.confirm_gate` 提供函式 `sweep_expired(conn, *, timeout_minutes, clock) -> list[str]`，行為如下：

1. SHALL 以 `BEGIN IMMEDIATE` 開啟交易。
2. 查 `SELECT decision_id, symbol, created_at FROM journal_entries WHERE kind='entry' AND json_extract(payload_json, '$.decision_status')='pending_confirm'` 全部 row。
3. 對每筆，計算 `created_at + timeout_minutes < clock.now()`（皆轉成 UTC 比較，避免 TZ 問題）；若是 → 處理；否則跳過。
4. 對每筆需處理的 row：INSERT `kind=expire` row，payload `decision_status="expired"`、`expire_reason="confirm timeout after <N> minutes"`、`expired_at=clock.now_iso()`；UPDATE 原 entry row 的 `payload_json` set `decision_status="expired"`。
5. COMMIT。回傳被 sweep 的 `decision_id` list（順序為 SELECT 順序）。

`timeout_minutes` SHALL 為正 int；非正值 raise `ValueError`。空 list 為合法回傳值（無 pending row 或無過期 row）。

#### Scenario: sweep 將過期 row 變成 expired
- **GIVEN** pending entry `created_at="2026-05-02T10:00:00+08:00"`，`clock.now() == "2026-05-02T10:35:00+08:00"`，`timeout_minutes=30`
- **WHEN** 呼叫 `sweep_expired(conn, timeout_minutes=30, clock=FakeClock("2026-05-02T10:35:00+08:00"))`
- **THEN** 回傳 `["<該 decision_id>"]`；DB 中該 decision_id 的 entry row `decision_status="expired"`；新 `kind=expire` row 存在，payload `expire_reason="confirm timeout after 30 minutes"`

#### Scenario: sweep 不影響未過期的 pending row
- **GIVEN** pending entry `created_at="2026-05-02T10:00:00+08:00"`，`clock.now() == "2026-05-02T10:25:00+08:00"`，`timeout_minutes=30`
- **WHEN** 呼叫 `sweep_expired(...)`
- **THEN** 回傳 `[]`；entry row `decision_status` 仍為 `"pending_confirm"`；無新 expire row

#### Scenario: sweep 同時處理多筆過期 row 並 commit 一次
- **GIVEN** 三筆 pending entry，全部已過期
- **WHEN** 呼叫 `sweep_expired(...)`
- **THEN** 回傳 list 長度為 3；DB 中三筆 entry 的 status 皆為 `"expired"`；三筆 `kind=expire` row 皆存在（共 6 筆 row 變動，一次 commit）

#### Scenario: sweep timeout_minutes 非正值 raise ValueError
- **WHEN** 呼叫 `sweep_expired(conn, timeout_minutes=0, ...)` 或 `timeout_minutes=-5`
- **THEN** raise `ValueError`，message 含 `"timeout_minutes"`

---

### Requirement: list_pending() 函式：CLI --list 的查詢支援

系統 SHALL 在 `ohmystock.safety.confirm_gate` 提供函式 `list_pending(conn, *, clock, timeout_minutes) -> list[PendingEntry]`，回傳目前狀態為 `pending_confirm` 的所有 entry，包含 TTL 剩餘秒數（負值代表已過期）。

`PendingEntry` SHALL 為 frozen dataclass `(decision_id: str, symbol: str, created_at: str, age_seconds: int, ttl_seconds: int, current_price: float, final_sizing_pct: float)`。`ttl_seconds = timeout_minutes * 60 - age_seconds`。

回傳順序 SHALL 為 `created_at` 升序（最舊優先）。空 list 為合法回傳值。

#### Scenario: list_pending 回傳所有 pending entry
- **GIVEN** in-memory SQLite + 兩筆 pending entry（`created_at="10:00"` 與 `"10:10"`），`clock.now() == "10:15"`，`timeout_minutes=30`
- **WHEN** 呼叫 `list_pending(conn, clock=..., timeout_minutes=30)`
- **THEN** 回傳長度 2 list，第一個 `decision_id` 對應 10:00 那筆（最舊優先），其 `age_seconds=900`、`ttl_seconds=900`

#### Scenario: list_pending 不回傳 confirmed/rejected/expired
- **GIVEN** 一筆 confirmed、一筆 rejected、一筆 expired entry
- **WHEN** 呼叫 `list_pending(...)`
- **THEN** 回傳空 list

---

### Requirement: 模組對外 API 透過 `__init__.py` re-export

系統 SHALL 在 `src/ohmystock/safety/__init__.py` re-export 公開符號：`confirm`、`reject`、`sweep_expired`、`list_pending`、`ConfirmResult`、`RejectResult`、`PendingEntry`、`ConfirmGateError`、`Clock`、`system_clock`。

系統 SHALL 在 `src/ohmystock/paper/__init__.py` re-export：`PaperBroker`、`FakePaperBroker`、`Fill`、`BrokerError`。

#### Scenario: from ohmystock.safety import 公開符號可用
- **WHEN** 執行 `from ohmystock.safety import confirm, reject, sweep_expired, list_pending, ConfirmGateError`
- **THEN** import 成功，所有符號可呼叫 / 可實例化

#### Scenario: from ohmystock.paper import broker 公開符號可用
- **WHEN** 執行 `from ohmystock.paper import PaperBroker, FakePaperBroker, Fill, BrokerError`
- **THEN** import 成功
