## MODIFIED Requirements

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

## ADDED Requirements

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
