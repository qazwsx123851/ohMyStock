## Purpose

Defines the canonical 21-string `event_type` registry, the per-service emitter contracts (which service emits which `event_type`, what payload fields are required, and the failure mode), the `safe_emit` helper, and the `AdminEventSerializer` JSON shape used by `/api/admin/events`. Owns the spec invariants for "every emit is best-effort and never blocks the producer".

## Requirements

### Requirement: Canonical event_type and agent constants

系統 SHALL 提供 `ohmystock.eventbus.types` 模組，匯出兩個 namespace 常數：

- `EventType`：`StrEnum`（或等效 `Final` 字串常數），成員 SHALL 完整對應 `docs/backend-eventbus.md` §3.2 的 16 個原 event_type 字串外加 5 個新 swarm 事件，共 21 個：`SCREENER_STARTED="screener_started"`、`SCREENER_COMPLETED="screener_completed"`、`PATTERN_DETECTED="pattern_detected"`、`DECIDER_THINKING="decider_thinking"`、`DECISION_MADE="decision_made"`、`AWAITING_CONFIRM="awaiting_confirm"`、`ORDER_SENT="order_sent"`、`JOURNAL_WRITTEN="journal_written"`、`JOURNAL_QUERIED="journal_queried"`、`REVIEW_NODE_STARTED="review_node_started"`、`REVIEW_COMPLETED="review_completed"`、`PROPOSAL_CREATED="proposal_created"`、`WFA_STARTED="wfa_started"`、`WFA_PASSED="wfa_passed"`、`WFA_FAILED="wfa_failed"`、`RISK_OFF_TRIGGERED="risk_off_triggered"`、`SWARM_RUN_STARTED="swarm_run_started"`、`SWARM_RUN_COMPLETED="swarm_run_completed"`、`SWARM_RUN_FAILED="swarm_run_failed"`、`SWARM_NODE_STARTED="swarm_node_started"`、`SWARM_NODE_COMPLETED="swarm_node_completed"`。
- `Agent`：`StrEnum` 或常數，成員 SHALL 包含 `SCANNER="scanner"`、`PATTERN_ANALYST="pattern_analyst"`、`DECIDER="decider"`、`TRADER="trader"`、`LIBRARIAN="librarian"`、`REVIEWER="reviewer"`、`PROPOSER="proposer"`、`VALIDATOR="validator"`、`GUARD="guard"`。

任何 emitter 在 `Event(event_type=..., agent=...)` 兩個欄位 SHALL 引用 `EventType.*` / `Agent.*`，禁止內聯字串字面量。

#### Scenario: EventType 含全部 21 個常數
- **WHEN** 執行 `from ohmystock.eventbus.types import EventType; values = {m.value for m in EventType}`
- **THEN** `values` 等於 `{"screener_started","screener_completed","pattern_detected","decider_thinking","decision_made","awaiting_confirm","order_sent","journal_written","journal_queried","review_node_started","review_completed","proposal_created","wfa_started","wfa_passed","wfa_failed","risk_off_triggered","swarm_run_started","swarm_run_completed","swarm_run_failed","swarm_node_started","swarm_node_completed"}`

#### Scenario: Agent 含全部 9 個常數
- **WHEN** 執行 `from ohmystock.eventbus.types import Agent; values = {m.value for m in Agent}`
- **THEN** `values` 等於 `{"scanner","pattern_analyst","decider","trader","librarian","reviewer","proposer","validator","guard"}`

#### Scenario: EventType 成員與字串相等
- **WHEN** 執行 `from ohmystock.eventbus.types import EventType; e = EventType.DECISION_MADE`
- **THEN** `e == "decision_made"` 為 `True`，且 `isinstance(e, str)` 為 `True`

#### Scenario: SWARM_RUN_STARTED 與字串相等
- **WHEN** 執行 `from ohmystock.eventbus.types import EventType; e = EventType.SWARM_RUN_STARTED`
- **THEN** `e == "swarm_run_started"` 為 `True`，且 `isinstance(e, str)` 為 `True`

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

---

### Requirement: Swarm runner emitter — swarm_run_started + swarm_node_started/completed + swarm_run_completed/failed

`ohmystock.swarm_runs.runner.run_swarm(...)` SHALL 在以下時點 `await safe_emit(...)`：

1. 進入 `run_swarm`、preset / params 驗證通過、`Settings().anthropic_api_key` 檢查通過、即將開始第 1 個節點之前 → `Event(event_type=EventType.SWARM_RUN_STARTED, agent=Agent.REVIEWER, payload={"run_id": str, "preset": str, "nodes": list[str], "params": dict})`，`run_id` 格式 `"swr_<12hex>"`、`nodes` 為 preset 的節點順序 list、`params` 為 caller 傳入的原始 dict。
2. 對每個節點 `n` 執行**前** → `Event(event_type=EventType.SWARM_NODE_STARTED, agent=Agent.REVIEWER, payload={"run_id": str, "preset": str, "node": str})`。
3. 對每個節點 `n` 成功執行**後** → `Event(event_type=EventType.SWARM_NODE_COMPLETED, agent=Agent.REVIEWER, payload={"run_id": str, "preset": str, "node": str, "elapsed_ms": int})`。
4. 全部節點成功跑完、row commit **之後** → `Event(event_type=EventType.SWARM_RUN_COMPLETED, agent=Agent.REVIEWER, payload={"run_id": str, "preset": str, "elapsed_ms": int})`，`elapsed_ms` 為 step 1 開始到全部節點完成的累計毫秒。
5. 任何節點 raise `Exception` 被 catch 之後、failed row commit **之後** → `Event(event_type=EventType.SWARM_RUN_FAILED, agent=Agent.REVIEWER, payload={"run_id": str, "preset": str, "failed_node": str, "error": {"code": str, "message": str}})`。

失敗路徑 SHALL **不**再發 `SWARM_RUN_COMPLETED`；失敗節點之後的節點 SHALL **不**發 `SWARM_NODE_STARTED` / `SWARM_NODE_COMPLETED`。

`Settings().anthropic_api_key` 缺失導致 fail-fast 拋 `SwarmRunnerError("missing_api_key:...")` 路徑 SHALL **不**發任何 swarm event（已在 step 1 之前判斷）。同理，未知 preset 與 invalid params 路徑 SHALL **不**發任何 event。

#### Scenario: 完整 happy path 發 12 個 event
- **GIVEN** fresh bus + spy queue + valid params + `run_review` mock 立即成功
- **WHEN** 呼叫 `await run_swarm("phase5-review", {...有效 params}, ...)`
- **THEN** spy queue 依序含：`swarm_run_started` (1) → `swarm_node_started`/`swarm_node_completed` 配對 5 組共 10 個 → `swarm_run_completed` (1)，總計 12 個 event
- **AND** 所有 event 的 `payload["run_id"]` 為同一字串、`payload["preset"] == "phase5-review"`

#### Scenario: 中途失敗只發到失敗節點
- **GIVEN** `run_review` mock 在 `aggregator` 節點 raise `RuntimeError("boom")`
- **WHEN** 呼叫 `await run_swarm(...)`
- **THEN** spy queue 含 `swarm_run_started`、`data_loader started/completed`、`attributor started/completed`、`aggregator started`，後接 `swarm_run_failed`（payload `failed_node="aggregator"`）
- **AND** spy queue **不**含 `aggregator completed`、**不**含 `critic`/`proposer` 任何 event、**不**含 `swarm_run_completed`

#### Scenario: fail-fast 路徑不發 event
- **GIVEN** `Settings().anthropic_api_key` 為空
- **WHEN** 呼叫 `await run_swarm(...)` 拋 `SwarmRunnerError("missing_api_key:...")`
- **THEN** spy queue **不**含任何 `swarm_*` event

#### Scenario: bus.emit raise 不影響 runner 主流程
- **GIVEN** monkeypatch `bus.emit` 永遠 raise `RuntimeError`，`run_review` mock 成功
- **WHEN** 呼叫 `await run_swarm(...)` 走 happy path
- **THEN** `run_swarm` SHALL 正常 return `SwarmRunResult(status="completed", ...)`、swarm_runs 表 SHALL 含一筆 `status="completed"` row

---

### Requirement: pattern_detected emitter — vcp_pivot sub-scorer

`ohmystock.scoring.subscorers.vcp_pivot.vcp_pivot(ctx)` SHALL 在 sub-scorer 計算完成、`SubScoreResult` 的 `score > 0` 且 `evidence["pivot_price"] is not None` 時，發出一個 `pattern_detected` event。emit 透過 `safe_emit_sync(event)` 完成，因 `vcp_pivot` 是 sync 函式。

- `event.event_type == EventType.PATTERN_DETECTED`
- `event.agent == Agent.PATTERN_ANALYST`
- `event.payload == {"symbol": ctx.symbol, "pattern": "VCP", "score": float(result.score)}`
- `score == 0` 或 `pivot_price is None` 時 SHALL **不**發 event（避免 noise）。

#### Scenario: 有效 VCP 命中發 event
- **GIVEN** `ctx_with_strong_vcp` 使 sub-scorer 回 `SubScoreResult(score=6.0, evidence={"pivot_price": 100.5, ...})`
- **WHEN** subscribe queue + 跑 `vcp_pivot(ctx_with_strong_vcp)`
- **THEN** queue 收到 1 個 event，`event.event_type == "pattern_detected"`、`event.agent == "pattern_analyst"`、`event.payload == {"symbol": ctx.symbol, "pattern": "VCP", "score": 6.0}`

#### Scenario: 無命中 SHALL 不發 event
- **GIVEN** `ctx_with_no_match` 使 sub-scorer 回 `SubScoreResult(score=0.0, evidence={})`
- **WHEN** subscribe queue + 跑 `vcp_pivot(ctx_with_no_match)`
- **THEN** queue 0 event

---

### Requirement: journal_queried emitter — journal route SELECT

`ohmystock.api.routes.journal.list_journal_entries(...)` 在執行 `journal_entries` 表 SELECT 並回拿 rows 之後，SHALL `await safe_emit(Event(event_type=EventType.JOURNAL_QUERIED, agent=Agent.LIBRARIAN, payload={"query": query_repr, "result_count": len(rows)}))`。

- `query_repr` SHALL 為 request query 參數的字串化表示（例：`"kind=entry&symbol=2330"`）；無 filter 時 SHALL 為 `"all"`。
- emit SHALL 在 response envelope 寫出之前完成。
- DB 查詢失敗（例 `sqlite3.OperationalError`）路徑 SHALL **不**發 event。

#### Scenario: 含 filter 的查詢發 event
- **GIVEN** TestClient subscribe `/api/admin/events` + 已存 3 筆 `kind=entry` rows
- **WHEN** TestClient call `GET /api/admin/journal?kind=entry`
- **THEN** SSE 收到 `journal_queried` event，`payload["result_count"] == 3`、`payload["query"]` 含子字串 `"kind=entry"`

#### Scenario: 無 filter 的查詢 query_repr == "all"
- **GIVEN** TestClient subscribe `/api/admin/events`
- **WHEN** TestClient call `GET /api/admin/journal`
- **THEN** SSE 收到 `journal_queried` event，`payload["query"] == "all"`

---

### Requirement: review_node_started + review_completed emitters — Phase 5 pipeline

`ohmystock.review.pipeline.run_review(...)` 在 `dry_run is False` 的條件下，SHALL 在 5 個節點各自開跑前 emit `review_node_started`，並在 `upsert_index_entry(...)` 成功之後 emit `review_completed`。

- node 順序固定為 `["data_loader","attributor","aggregator","critic","proposer"]`。
- `review_node_started` payload: `{"review_id": review_id, "node_name": <node>, "node_index": <0..4>}`。`node_index` SHALL 為 0-based。
- `review_completed` payload: `{"review_id": review_id, "proposals_created_count": len(proposer_result.written_paths)}`。
- emit 透過 `safe_emit_sync(event)` 進行（`run_review` 是 sync）。
- `dry_run is True` 路徑 SHALL **不**發任何 review event。

#### Scenario: happy path 發 6 個 event
- **GIVEN** mock 5 個 node 全成功、subscribe queue
- **WHEN** 呼叫 `run_review(..., dry_run=False)`
- **THEN** queue 依序收到 6 個 event：5 個 `review_node_started`（`node_index` 0..4、`node_name` 依序為 data_loader → proposer）+ 1 個 `review_completed`，`payload["review_id"]` 全部相同

#### Scenario: dry_run 路徑 SHALL 不發 event
- **GIVEN** subscribe queue
- **WHEN** 呼叫 `run_review(..., dry_run=True)`
- **THEN** queue 0 個 review event

---

### Requirement: proposal_created emitter — write_proposal

`ohmystock.proposal.writer.write_proposal(draft, proposals_dir)` SHALL 在 `target.write_text(...)` 成功完成、return `target` 之前 emit `proposal_created`。透過 `safe_emit_sync(event)`。

- `event.event_type == EventType.PROPOSAL_CREATED`
- `event.agent == Agent.PROPOSER`
- `event.payload == {"proposal_id": proposal_id, "priority": draft.priority, "target_section": draft.target_section}`，`proposal_id` 為 `target.stem`
- write 失敗（disk full / permission / collision overflow）SHALL 已 raise，不執行到 emit。

#### Scenario: write 成功發 event
- **GIVEN** `draft = ProposalDraft(priority="medium", target_section="§6.4", ...)`、subscribe queue
- **WHEN** `write_proposal(draft, tmp_path)`
- **THEN** queue 收到 `proposal_created` event，`payload == {"proposal_id": <target.stem>, "priority": "medium", "target_section": "§6.4"}`

---

### Requirement: wfa_started / wfa_passed / wfa_failed emitters — WFA validator

`ohmystock.validation.wfa.run_validation(...)` SHALL 在三個時點 emit event，透過 `safe_emit_sync(event)`：

1. `raw_windows = _split_windows(...)` 成功之後、進入 `for window in raw_windows` 之前 → `Event(event_type=EventType.WFA_STARTED, agent=Agent.VALIDATOR, payload={"proposal_id": proposal_id})`。
2. `_transition_after_verdict(...)` 完成、且 `verdict == "pass"` → `Event(event_type=EventType.WFA_PASSED, agent=Agent.VALIDATOR, payload={"proposal_id": proposal_id})`。
3. `_transition_after_verdict(...)` 完成、且 `verdict == "fail"` → `Event(event_type=EventType.WFA_FAILED, agent=Agent.VALIDATOR, payload={"proposal_id": proposal_id, "failure_reason": ";".join(failures)})`。

`WfaValidationError` 在 `wfa_started` emit 之前 raise（例：`status_not_validating`、`invalid_universe`、`missing_bars`、`strategy_introspection_failed`）SHALL **不**發任何 event。`wfa_started` 已發後再 raise SHALL **不**補發 `wfa_failed`（內部錯誤非 verdict）。

`dry_run=True` 路徑 SHALL **照常** emit（validation 是 gate，不是 trial）。

#### Scenario: verdict=pass 流程
- **GIVEN** mock strategy 使 OOS Sharpe > baseline、subscribe queue
- **WHEN** `run_validation(proposal_path, ...)` 結束
- **THEN** queue 依序收到 `wfa_started` 與 `wfa_passed` 各 1 個，`payload["proposal_id"]` 相同

#### Scenario: verdict=fail 流程
- **GIVEN** mock strategy 使 OOS Sharpe < baseline 觸發 `sharpe_below_baseline` failure、subscribe queue
- **WHEN** `run_validation(proposal_path, ...)` 結束
- **THEN** queue 依序收到 `wfa_started` 與 `wfa_failed`，`wfa_failed.payload["failure_reason"]` 含子字串 `"sharpe_below_baseline"`

#### Scenario: 空 universe 不發 event
- **GIVEN** subscribe queue
- **WHEN** `run_validation(proposal_path, universe=[], ...)` raise `WfaValidationError("invalid_universe: ...")`
- **THEN** queue 0 event

