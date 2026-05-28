## ADDED Requirements

### Requirement: pattern_detected emitter — vcp_pivot sub-scorer

`ohmystock.scoring.subscorers.vcp_pivot.vcp_pivot(ctx)` SHALL 在 sub-scorer 計算完成、`SubScoreResult` 的 `score > 0` 且 `evidence["pivot_price"] is not None` 時，發出一個 `pattern_detected` event。emit 透過 `emit_from_sync(event)` 完成，因 `vcp_pivot` 是 sync 函式。

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
- emit 透過 `emit_from_sync(event)` 進行（`run_review` 是 sync）。
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

`ohmystock.proposal.writer.write_proposal(draft, proposals_dir)` SHALL 在 `target.write_text(...)` 成功完成、return `target` 之前 emit `proposal_created`。透過 `emit_from_sync(event)`。

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

`ohmystock.validation.wfa.run_validation(...)` SHALL 在三個時點 emit event，透過 `emit_from_sync(event)`：

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

---

### Requirement: emit_from_sync helper — sync-context safe emit

`ohmystock.eventbus` package SHALL 公開 `emit_from_sync(event: Event) -> None`：

- 偵測 current thread 是否有 running asyncio event loop（`asyncio.get_running_loop()` 不 raise）：
  - 有 → `loop.create_task(safe_emit(event))`（fire-and-forget；不 await）。
  - 無（純 sync caller，例 CLI / sub-scorer） → `asyncio.run(safe_emit(event))`（阻塞直到 emit 完成）。
- 任何例外 SHALL 被 swallow（同 `safe_emit` 的 BaseException-aware 行為）。
- caller SHALL **不**期待 emit 完成的 guarantee；emit 是 best-effort。

#### Scenario: sync context 同步發 event
- **GIVEN** 純 sync 函式 + subscribe queue 經 helper
- **WHEN** call `emit_from_sync(Event(...))`
- **THEN** queue.get_nowait() 立即拿到該 event

#### Scenario: async context fire-and-forget
- **GIVEN** asyncio context + subscribe queue
- **WHEN** call `emit_from_sync(Event(...))` 後立即 `await asyncio.sleep(0)`（讓 task scheduler 跑）
- **THEN** queue 收到該 event

#### Scenario: emit 例外 SHALL 不影響 caller
- **GIVEN** monkeypatch `safe_emit` 拋 `RuntimeError`
- **WHEN** call `emit_from_sync(Event(...))`
- **THEN** call 正常 return、無例外
