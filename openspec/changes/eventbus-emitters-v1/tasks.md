# tasks

## 1. PUBLIC_WHITELIST 補 5 個 swarm 條目

- [ ] 1.1 在 `src/ohmystock/eventbus/serializers.py` 的 `PUBLIC_WHITELIST` dict 加 5 個 key：`swarm_run_started`、`swarm_run_completed`、`swarm_run_failed`、`swarm_node_started`、`swarm_node_completed`。fields per proposal §"What Changes".
- [ ] 1.2 新增 `tests/test_eventbus_public_mask_swarm.py` parametrised over 5 個新 event_type，丟最大 payload（包 DENYLIST），斷言輸出 == whitelist 投影。

## 2. pattern_detected emitter（vcp_pivot）

- [ ] 2.1 在 `src/ohmystock/scoring/subscorers/vcp_pivot.py` 的 `vcp_pivot()` 函式末端，當 `score > 0` 且 `pivot_price is not None` 時 emit `pattern_detected`。
- [ ] 2.2 `vcp_pivot` 是同步函式 — 透過 task 7 的 `emit_from_sync` helper 完成。
- [ ] 2.3 test：subscribe 一條 queue、跑 `vcp_pivot(ctx_with_strong_vcp)`、assert queue 收到 `pattern_detected` event。
- [ ] 2.4 test：`vcp_pivot(ctx_with_no_match)` 不發 event（score == 0）。

## 3. journal_queried emitter（journal route）

- [ ] 3.1 在 `src/ohmystock/api/routes/journal.py` 的 `list_journal_entries` route handler 內，SELECT 完拿到 rows 之後 emit `journal_queried`。
- [ ] 3.2 test：subscribe、call route via TestClient with `?kind=entry`、assert queue 收到 `journal_queried` event。

## 4. review_node_started + review_completed emitters（review pipeline）

- [ ] 4.1 在 `src/ohmystock/review/pipeline.py` 的 `run_review`，5 個 node 開跑前各 emit `review_node_started`（`node_index` 0..4）。
- [ ] 4.2 `upsert_index_entry` 之後 emit `review_completed`，`payload["proposals_created_count"]` 為 proposer 寫出的 markdown 檔數。
- [ ] 4.3 `dry_run=True` SHALL 不發任何 review event（dry-run 保持靜默）。
- [ ] 4.4 test：mock LLM `run_review` happy path、assert queue 依序收到 5 個 `review_node_started` + 1 個 `review_completed`。
- [ ] 4.5 test：`dry_run=True` SHALL 不發任何 review event。

## 5. proposal_created emitter（proposal writer）

- [ ] 5.1 在 `src/ohmystock/proposal/writer.py` 的 `write_proposal()` 內 `target.write_text(...)` 之後（return target 之前），emit `proposal_created`。
- [ ] 5.2 write 失敗（disk full / permission / 99 collisions）SHALL 已在 raise 之前 short-circuit，不會發 event。
- [ ] 5.3 test：subscribe、`write_proposal(valid_draft, tmp_path)`、assert queue 收到 `proposal_created` event。

## 6. wfa_started / wfa_passed / wfa_failed emitters（WFA validator）

- [ ] 6.1 在 `src/ohmystock/validation/wfa.py` 的 `run_validation()` 內，`raw_windows = _split_windows(...)` 成功之後、進入 `for window in raw_windows` 之前 emit `wfa_started`。
- [ ] 6.2 happy path：`_transition_after_verdict(...)` 之後，根據 `verdict` 分支：
  - `verdict == "pass"` → emit `wfa_passed`，payload `{"proposal_id": proposal_id}`。
  - `verdict == "fail"` → emit `wfa_failed`，payload `{"proposal_id": proposal_id, "failure_reason": ";".join(failures)}`（admin 看完整原因；public mask 因 `failure_reason ∈ DENYLIST_FIELDS` 與 `wfa_failed` 白名單只列 `proposal_id` 而 drop）。
- [ ] 6.3 `WfaValidationError` (e.g. `status_not_validating`、`invalid_universe`、`missing_bars`) raise 之前 SHALL **不**發 `wfa_started`（fail-fast at frontmatter parse / universe check）；若 `wfa_started` 已發、後續 raise SHALL **不**補發 `wfa_failed`（這是 validator 內部錯誤，不是 WFA verdict）。
- [ ] 6.4 test：mock strategy + 1-window WFA → verdict=pass → assert sequence `wfa_started → wfa_passed`。
- [ ] 6.5 test：強制 candidate Sharpe < baseline 使 verdict=fail → assert sequence `wfa_started → wfa_failed`，`failure_reason` 含 join 過的 failures list。
- [ ] 6.6 test：傳入空 universe → raise `WfaValidationError`，queue 收到 0 event。

## 7. 共用 sync-to-async emit helper

- [ ] 7.1 在 `src/ohmystock/eventbus/__init__.py` 新增 `emit_from_sync(event: Event) -> None`：偵測 running event loop；有 loop → `loop.create_task(safe_emit(event))`；無 loop → `asyncio.run(safe_emit(event))`。封裝給 sync 呼叫端（`vcp_pivot`、`run_review`、`write_proposal`、`run_validation`）統一使用。
- [ ] 7.2 export `emit_from_sync` 與 `safe_emit` 從 `ohmystock.eventbus` package。
- [ ] 7.3 test：`emit_from_sync` 在 sync context 跑、在 asyncio context 跑、emit 拋例外 — 三種情境皆不影響 caller。

## 8. SSOT 維護

- [ ] 8.1 修改 `docs/backend-eventbus.md` §3.2 v0 wiring-status 註記，改為 "21 of 21 event_types emitted as of `eventbus-emitters-v1`"。
- [ ] 8.2 改 `openspec/specs/eventbus-emitters/spec.md`（archive 後）：把 8 個新 emitter requirement 合入；改 `openspec/specs/eventbus-public-mask/spec.md`：把 5 個新 swarm 白名單合入完整 21-key 表。

## 9. 驗證

- [ ] 9.1 `uv run pytest -q tests/test_eventbus*` 全綠。
- [ ] 9.2 啟動 backend、`curl /api/admin/events`、跑一輪 review、肉眼確認 SSE 順序。
- [ ] 9.3 同時對 `/api/public/events`，assert public 端 payload 為 whitelist 投影、無 DENYLIST 欄位。
