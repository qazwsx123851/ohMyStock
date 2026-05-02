## Purpose

Defines the canonical 16-string `event_type` registry, the per-service emitter contracts (which service emits which `event_type`, what payload fields are required, and the failure mode), the `safe_emit` helper, and the `AdminEventSerializer` JSON shape used by `/api/admin/events`. Owns the spec invariants for "every emit is best-effort and never blocks the producer".

## Requirements

### Requirement: Canonical event_type and agent constants

系統 SHALL 提供 `ohmystock.eventbus.types` 模組，匯出兩個 namespace 常數：

- `EventType`：`StrEnum`（或等效 `Final` 字串常數），成員 SHALL 完整對應 `docs/backend-eventbus.md` §3.2 的 16 個 event_type 字串：`SCREENER_STARTED="screener_started"`、`SCREENER_COMPLETED="screener_completed"`、`PATTERN_DETECTED="pattern_detected"`、`DECIDER_THINKING="decider_thinking"`、`DECISION_MADE="decision_made"`、`AWAITING_CONFIRM="awaiting_confirm"`、`ORDER_SENT="order_sent"`、`JOURNAL_WRITTEN="journal_written"`、`JOURNAL_QUERIED="journal_queried"`、`REVIEW_NODE_STARTED="review_node_started"`、`REVIEW_COMPLETED="review_completed"`、`PROPOSAL_CREATED="proposal_created"`、`WFA_STARTED="wfa_started"`、`WFA_PASSED="wfa_passed"`、`WFA_FAILED="wfa_failed"`、`RISK_OFF_TRIGGERED="risk_off_triggered"`。
- `Agent`：`StrEnum` 或常數，成員 SHALL 包含 `SCANNER="scanner"`、`PATTERN_ANALYST="pattern_analyst"`、`DECIDER="decider"`、`TRADER="trader"`、`LIBRARIAN="librarian"`、`REVIEWER="reviewer"`、`PROPOSER="proposer"`、`VALIDATOR="validator"`、`GUARD="guard"`。

任何 emitter 在 `Event(event_type=..., agent=...)` 兩個欄位 SHALL 引用 `EventType.*` / `Agent.*`，禁止內聯字串字面量。

#### Scenario: EventType 含全部 16 個常數
- **WHEN** 執行 `from ohmystock.eventbus.types import EventType; values = {m.value for m in EventType}`
- **THEN** `values` 等於 `{"screener_started","screener_completed","pattern_detected","decider_thinking","decision_made","awaiting_confirm","order_sent","journal_written","journal_queried","review_node_started","review_completed","proposal_created","wfa_started","wfa_passed","wfa_failed","risk_off_triggered"}`

#### Scenario: Agent 含全部 9 個常數
- **WHEN** 執行 `from ohmystock.eventbus.types import Agent; values = {m.value for m in Agent}`
- **THEN** `values` 等於 `{"scanner","pattern_analyst","decider","trader","librarian","reviewer","proposer","validator","guard"}`

#### Scenario: EventType 成員與字串相等
- **WHEN** 執行 `from ohmystock.eventbus.types import EventType; e = EventType.DECISION_MADE`
- **THEN** `e == "decision_made"` 為 `True`，且 `isinstance(e, str)` 為 `True`

---

### Requirement: safe_emit helper：best-effort fire-and-forget

系統 SHALL 在 `ohmystock.eventbus` 套件對外公開 async 函式 `safe_emit(event: Event) -> None`，呼叫 `bus.emit(event)` 並 catch 全部 `Exception`（包括 `Exception` 但 SHALL 不包含 `BaseException` 子類如 `asyncio.CancelledError` 與 `KeyboardInterrupt`，以保留 cooperative cancellation）。任何被 catch 的例外 SHALL 被 swallow，不重新 raise，不寫 stderr，不寫日誌（v0；future change 可加結構化 logger）。

呼叫端 SHALL 使用 `await safe_emit(event)`（不是直接 `await bus.emit(event)`）以保證 producer path 不被 bus 端錯誤中斷。

#### Scenario: bus 正常時 emit 成功
- **GIVEN** 一個 fresh `EventBus`，subscribe 一個 queue `q`
- **WHEN** 執行 `await safe_emit(Event(event_type="decision_made", agent="decider"))`
- **THEN** `q.get_nowait()` 回傳該 Event

#### Scenario: bus.emit 拋例外時 safe_emit 吞掉
- **GIVEN** monkeypatch `bus.emit` 改成 `async def raise_boom(...): raise RuntimeError("boom")`
- **WHEN** 執行 `await safe_emit(Event(event_type="decision_made", agent="decider"))`
- **THEN** call 正常 return，無 exception 拋出

#### Scenario: CancelledError 不被吞掉
- **GIVEN** monkeypatch `bus.emit` 改成 `async def raise_cancel(...): raise asyncio.CancelledError()`
- **WHEN** 執行 `await safe_emit(Event(event_type="decision_made", agent="decider"))`
- **THEN** raise `asyncio.CancelledError`

---

### Requirement: AdminEventSerializer.serialize 回傳 admin JSON 形狀

系統 SHALL 在 `ohmystock.eventbus.serializers` 模組提供 `class AdminEventSerializer`，含 `@staticmethod serialize(event: Event) -> dict[str, Any]`。回傳 dict SHALL 含以下 5 個 key（順序不做要求；values 對應 `Event` 同名欄位，`timestamp` 以 `event.timestamp.isoformat()` 序列化）：`event_id`、`timestamp`、`event_type`、`agent`、`payload`。`payload` SHALL 為原始 dict reference（不深拷貝）。Serializer **不**做欄位 mask、不做欄位過濾。

#### Scenario: 完整 5 欄位序列化
- **GIVEN** `event = Event(event_type="decision_made", agent="decider", payload={"symbol":"2330","confidence":0.72})`
- **WHEN** 執行 `out = AdminEventSerializer.serialize(event)`
- **THEN** `out.keys() == {"event_id","timestamp","event_type","agent","payload"}`、`out["event_type"] == "decision_made"`、`out["agent"] == "decider"`、`out["payload"]["symbol"] == "2330"`

#### Scenario: timestamp 為 ISO-8601 含 +08:00
- **GIVEN** `event = Event(event_type="decision_made", agent="decider")` 預設 `datetime.now(TPE)`
- **WHEN** 執行 `out = AdminEventSerializer.serialize(event)`
- **THEN** `out["timestamp"]` 為字串、含子字串 `"+08:00"`、能 round-trip 經 `datetime.fromisoformat(out["timestamp"])` 還原

#### Scenario: payload 不被 mask
- **GIVEN** `event = Event(event_type="decision_made", agent="decider", payload={"symbol":"2330","reasoning":"突破 20MA + 量能 1.5x"})`
- **WHEN** 執行 `out = AdminEventSerializer.serialize(event)`
- **THEN** `out["payload"]["reasoning"]` 完整保留原始字串、`out["payload"]["symbol"] == "2330"`（無 `masked_symbol` / 無欄位 strip）

---

### Requirement: Screener emitter — screener_started + screener_completed

`ohmystock.screener` 的 main entry point（將 universe 縮成 candidate list 的函式）SHALL 在以下兩個時點 `await safe_emit(...)`：

- 進入函式並解析出 `universe_size` 後 → `Event(event_type=EventType.SCREENER_STARTED, agent=Agent.SCANNER, payload={"universe_size": int})`
- 函式 success 路徑 return 前 → `Event(event_type=EventType.SCREENER_COMPLETED, agent=Agent.SCANNER, payload={"candidate_count": int, "symbols": list[str]})`，`symbols` 為過濾完的最終 candidate symbol list（v0 不截斷）

任何例外路徑 SHALL **不**發 `screener_completed`。

#### Scenario: 成功路徑發出 started + completed
- **GIVEN** 一個 fresh `EventBus`，subscribe 一個 spy queue
- **WHEN** 呼叫 screener，universe 200 檔，最後通過 5 檔 candidate
- **THEN** spy queue 至少含兩個 events，第一個 `event_type="screener_started"`、`payload["universe_size"]==200`；第二個 `event_type="screener_completed"`、`payload["candidate_count"]==5`、`payload["symbols"]` 為 5 個元素的 list

#### Scenario: 例外路徑只發 started
- **GIVEN** screener 內部因下游 raise → 中斷
- **WHEN** 呼叫 screener
- **THEN** spy queue 含 `screener_started`，**不**含 `screener_completed`

#### Scenario: 無 subscriber 時 screener 仍正常完成
- **GIVEN** module-level `bus` 無 subscriber
- **WHEN** 呼叫 screener
- **THEN** screener 回傳值與 wiring 前一致，無 exception 拋出

---

### Requirement: Decider emitter — decider_thinking + decision_made

`ohmystock.decider.orchestrator.decide_entry()` SHALL 在以下兩個時點 `await safe_emit(...)`：

- 候選驗證通過、進入 swarm call 之前 → `Event(event_type=EventType.DECIDER_THINKING, agent=Agent.DECIDER, payload={"symbol": str, "confidence_so_far": 0.0})`
- swarm 完成、`pending_confirm` row 寫入並 commit 之後 → `Event(event_type=EventType.DECISION_MADE, agent=Agent.DECIDER, payload={"symbol": str, "confidence": float, "reasoning": str, "action": "entry"|"skip"})`：
  - `action="entry"` ⟺ pending_confirm row 已寫入 journal
  - `action="skip"` ⟺ §2.1 system override validator 拒絕 swarm 輸出，此時 SHALL 仍發出 `decision_made`，且 `confidence` / `reasoning` 取自 swarm raw output

任何 raise 的例外路徑 SHALL **不**發 `decision_made`。

#### Scenario: entry 路徑兩個 events
- **GIVEN** 一個 fresh `EventBus`、`bus.subscribe()` 拿到 spy queue
- **WHEN** 跑通 decider entry path（symbol=2330，最終寫 pending_confirm row）
- **THEN** spy queue 至少含兩 events：第一為 `decider_thinking` payload `{"symbol":"2330","confidence_so_far":0.0}`；第二為 `decision_made` payload 含 `symbol="2330"`、`action="entry"`、`confidence` 為 float、`reasoning` 為非空字串

#### Scenario: skip 路徑（validator reject）也發 decision_made
- **GIVEN** swarm 輸出被 §2.1 system override validator 拒絕
- **WHEN** 跑 decider
- **THEN** spy queue 含 `decision_made`，`payload["action"] == "skip"`

#### Scenario: 例外路徑不發 decision_made
- **GIVEN** swarm call 中途 raise
- **WHEN** 跑 decider
- **THEN** spy queue 不含 `decision_made`（只可能含 `decider_thinking`）

---

### Requirement: Confirm-gate emitter — awaiting_confirm + order_sent

`ohmystock.decider._journal_writer.write_pending_confirm()`（或等效寫入 pending_confirm row 的函式）SHALL 在 `conn.commit()` 之後 `await safe_emit(Event(event_type=EventType.AWAITING_CONFIRM, agent=Agent.TRADER, payload={"symbol": str, "timeout_at": str, "expected_price": float}))`。`timeout_at` 為 ISO-8601 字串（含 +08:00），值為 entry payload 的 `timeout_at` 欄位。`expected_price` 為 entry payload 的 `current_price` 欄位。

`ohmystock.safety.confirm_gate.confirm()` 在 broker `submit_market_order` 成功 return Fill、journal `kind=fill` row commit 之後 SHALL `await safe_emit(Event(event_type=EventType.ORDER_SENT, agent=Agent.TRADER, payload={"symbol": str, "price": float, "quantity": int, "broker_order_id": str}))`。`price=fill.fill_price`、`quantity=fill.filled_qty`、`broker_order_id=fill.fill_ts`（v0 stand-in）。

confirm 失敗路徑（`ConfirmGateError`、broker raise `BrokerError`）SHALL **不**發 `order_sent`。

#### Scenario: pending_confirm 寫入後發 awaiting_confirm
- **GIVEN** fresh bus + spy queue + decider 寫一筆 pending_confirm
- **WHEN** journal commit 完成
- **THEN** spy queue 含 `awaiting_confirm`，payload `symbol` 等於 entry 的 symbol、`timeout_at` 為含 +08:00 的 ISO 字串、`expected_price` 等於 entry payload 的 `current_price`

#### Scenario: confirm 成功後發 order_sent
- **GIVEN** 一筆 pending_confirm 已寫入、FakePaperBroker（`raise_on_submit=False`）
- **WHEN** 呼叫 `confirm(...)` 並完成 fill row commit
- **THEN** spy queue 含 `order_sent`，payload `symbol` 等於 entry symbol、`price` 為 fill.fill_price 浮點、`quantity` 為 fill.filled_qty 整數、`broker_order_id` 為 fill.fill_ts 字串

#### Scenario: broker 失敗時不發 order_sent
- **GIVEN** `FakePaperBroker(raise_on_submit=True)`
- **WHEN** 呼叫 `confirm(...)`
- **THEN** raise `ConfirmGateError`（既有行為），spy queue **不**含 `order_sent`

---

### Requirement: Journal emitter — journal_written

`ohmystock.journal` 的中央 row insertion helper（v0 codebase 中對所有 `kind=*` row commit 的單一寫入點；若目前散落多處，emit 時點 SHALL 在每處 `conn.commit()` 之後）SHALL `await safe_emit(Event(event_type=EventType.JOURNAL_WRITTEN, agent=Agent.LIBRARIAN, payload={"journal_kind": str, "symbol": str}))`，其中 `journal_kind` 為 row 的 `kind` 欄位值（`"entry" | "fill" | "exit" | "reject" | "expire" | "auto_execute_audit"` 等合法 enum 成員）、`symbol` 為 row 的 `symbol` 欄位值。

#### Scenario: 寫一筆 entry → 發 journal_written
- **GIVEN** fresh bus + spy queue
- **WHEN** decider 寫一筆 `kind=entry` row 並 commit
- **THEN** spy queue 含 `journal_written`，payload `journal_kind="entry"`、`symbol` 對應 row 的 symbol

#### Scenario: 寫一筆 exit → 也發 journal_written
- **GIVEN** fresh bus + spy queue
- **WHEN** exit_engine 寫一筆 `kind=exit` row 並 commit
- **THEN** spy queue 含 `journal_written`，payload `journal_kind="exit"`、`symbol` 對應 row 的 symbol

#### Scenario: row commit 失敗 → 不發
- **GIVEN** journal insert 因 unique constraint conflict raise
- **WHEN** 嘗試寫 row
- **THEN** spy queue **不**含對應 `journal_written`

---

### Requirement: Auto-execute emitter — risk_off_triggered

`ohmystock.safety.auto_execute.try_auto_execute()` SHALL 在 audit row 寫入並 commit 之後（且 `outcome` 不是 `"pass"` 也不是 `"sizing_clamped_then_pass"`）`await safe_emit(Event(event_type=EventType.RISK_OFF_TRIGGERED, agent=Agent.GUARD, payload={"reason_category": str, "severity": "warn"|"halt"}))`：

| outcome | severity |
|---|---|
| `flag_off` | `warn` |
| `low_confidence` | `warn` |
| `live_broker` | `halt` |
| `notional_limit` | `halt` |
| `daily_limit` | `halt` |
| `loss_lockout` | `halt` |

`reason_category` 為原始 outcome 字串。

`pass` 與 `sizing_clamped_then_pass` SHALL **不**發 `risk_off_triggered`。

#### Scenario: low_confidence breaker 觸發
- **GIVEN** auto_execute settings 開啟、entry payload `llm_confidence=0.5` < threshold 0.7
- **WHEN** 呼叫 `try_auto_execute`
- **THEN** spy queue 含 `risk_off_triggered`，payload `reason_category="low_confidence"`、`severity="warn"`

#### Scenario: notional_limit breaker 觸發
- **GIVEN** entry payload notional 超過配額
- **WHEN** 呼叫 `try_auto_execute`
- **THEN** spy queue 含 `risk_off_triggered`，payload `reason_category="notional_limit"`、`severity="halt"`

#### Scenario: pass 路徑不發 risk_off_triggered
- **GIVEN** 全部 breaker 通過、無 sizing clamp
- **WHEN** 呼叫 `try_auto_execute` 並完成 confirm
- **THEN** spy queue **不**含 `risk_off_triggered`（但仍可能含 `journal_written` 對應 audit row）

#### Scenario: sizing_clamped_then_pass 不發 risk_off_triggered
- **GIVEN** sizing 偏離超過 30%、其他 breaker 通過
- **WHEN** 呼叫 `try_auto_execute`
- **THEN** spy queue **不**含 `risk_off_triggered`

---

### Requirement: Producer paths 對 bus 失敗 best-effort 容錯

對本 capability 範圍內所有 emitter（screener / decider / confirm-gate / journal / auto_execute），若 `safe_emit` 內部因任何原因（`bus.emit` raise、queue 滿被 drop）而 emit 失敗或 drop，producer SHALL：

- 完成原本的主要寫入路徑（DB row commit、broker fill 等）
- return / raise 的值與 emit 成功時一致
- 不將 bus 端錯誤回填給 caller

#### Scenario: bus.emit raise 不影響 confirm 主流程
- **GIVEN** monkeypatch 將 `bus.emit` 改成永遠 raise `RuntimeError`，FakePaperBroker 正常
- **WHEN** 呼叫 `confirm(...)` 走 happy path
- **THEN** confirm 正常 return `ConfirmResult`，journal `kind=fill` row 已寫入 DB

#### Scenario: 無 subscriber 時 decider 仍寫 pending_confirm
- **GIVEN** module-level `bus` 無 subscriber、decider 跑 entry path
- **WHEN** 呼叫 `decide_entry(...)`
- **THEN** journal 內出現 `kind=entry` 的 pending_confirm row，decider return 值與 wiring 前測試斷言一致

#### Scenario: queue 滿被 drop 不影響 auto_execute
- **GIVEN** 一個 spy queue 已滿（`maxsize=1`、預先塞一個 dummy event）
- **WHEN** 呼叫 `try_auto_execute(...)` 觸發 `low_confidence` breaker
- **THEN** auto_execute 正常 return `AutoExecuteResult(outcome="low_confidence", ...)`，audit row 已寫入 DB
