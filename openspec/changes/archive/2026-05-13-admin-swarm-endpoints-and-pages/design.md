## Context

`/swarm` 與 `/swarm/:preset/:runId` 在 web-admin shell 從一開始就被當 stub 預留。Phase 5 復盤 pipeline 已 ship 且能跑完 5-node 流程（`run_review` → `data_loader` / `attributor` / `aggregator` / `critic` / `proposer`），但目前唯一的觸發路徑是 CLI (`uv run ohmystock review --from ... --to ...`)，admin 沒有觀察介面。

此 change 不引入新 orchestration 機制 — 直接抄 `backtest_jobs` 的成功模式（sync 執行、整段塞 SQLite row、failure 也存 row 標 `status="failed"`），把 `run_review` 包成「preset」抽象，留出 v0+1 / v0+2 加 decider / screener preset 的 seam。

**Stakeholders**: Mark (sole user)；無其他 reviewer / 合規角色。

## Goals / Non-Goals

**Goals:**

- 讓 admin 能從 `/swarm` 點 preset 卡片觸發一次完整 Phase 5 復盤
- 讓 admin 能從 `/swarm/:preset/:runId` 看到 5 個節點的 sequential 執行進度（透過 SSE patch）與最終 output
- 失敗的 run 必落 row（`status="failed"` + `error.code` / `error.message`），detail 頁能呈現失敗節點與錯誤訊息
- 為「未來加 decider / screener preset」留下乾淨 seam：preset registry + preset-aware DAG renderer

**Non-Goals:**

- **不**做 async / queue / background worker；request 本身就會跑完整段 review（與 `POST /api/admin/backtest/run` 的 sync 模式一致）
- **不**做取消 / 暫停 / 中途重跑單一節點 — failure 後只能重發新 `POST /runs`
- **不**做 WebSocket 雙向；維持既有 admin SSE single-direction
- **不**改 `run_review` 內部行為；不改 review pipeline spec
- **不**自動觸發復盤（cron、月底自動跑）— 仍由人按按鈕
- **不**為 v0+1 / v0+2 的 decider / screener preset 預先建 schema；只留 `preset` 欄位 + registry 模式

## Decisions

### D1: Preset registry 用 hardcode dict（v0），不引 YAML config

v0 只有 1 個 preset (`phase5-review`)。`presets.py` 用 `PRESETS: dict[str, PresetSpec]` 寫死，`PresetSpec` 是 frozen pydantic（含 `name` / `title` / `description` / `nodes: list[str]` / `params_schema: dict`）。

**Rejected alternative**: YAML config 檔（`src/ohmystock/swarm_runs/presets/*.yaml`）。reasons — v0 1 個 preset 不需要 dynamic load，YAML 反而要多寫 schema validation；v0+N 加新 preset 時再轉 YAML 也來得及。

**Naming note**: 後端模組命名為 `swarm_runs` 而非 `swarm`，因為 `src/ohmystock/swarm/` 已被 Phase 2B Swarm Input Assembler 佔用（`build_entry_decision_input` 公開函式）。`swarm_runs` 名稱對應 SQL 表 `swarm_runs` 與 API path `/api/admin/swarm/runs/*`；URL `/swarm/*` 與 API namespace `/api/admin/swarm/*` 不受影響。

### D2: Sync 執行模式（與 backtest_jobs 一致），不引入 queue

`POST /api/admin/swarm/runs` 的 request handler 直接 `await run_swarm(...)` 跑完整段 Phase 5，return 含完整 `result_json` 的 row。預期單次跑時間 30s–5min（取決於 LLM 回應）。

**Rationale**:
- 與 `backtest` endpoint 行為一致，admin 端已有 spinner / loading 顯示模式可直接套用
- SSE 既有 `/api/admin/events` 仍能在 request 進行中 push `swarm_node_*` event 給開著 detail 頁的 client；只是 list 頁的「Run」按鈕本身會等到全部跑完才解 spinner
- 避免新增 worker process / asyncio.Task 生命週期管理 / queue 滿/空 邏輯

**Trade-off**: 長 LLM call 期間 HTTP connection 會佔住 — 但 admin 是單一用戶 localhost / Cloudflare Tunnel，並發為 1，不是問題。

**Rejected alternative**: BackgroundTasks / Celery / asyncio.create_task。Reason — 個人專案無多人並發，sync 路徑最少抽象。

### D3: SSE 沿用既有 `/api/admin/events`，不開新 channel

`swarm_run_started` / `swarm_run_completed` / `swarm_run_failed` / `swarm_node_started` / `swarm_node_completed` 5 個 event 直接 emit 到既有 `bus`，admin SSE subscriber 收到後 client 端依 `event.event_type.startsWith("swarm_") && event.payload.run_id === currentRunId` filter。

**Rationale**:
- `AdminEventSerializer` 黑箱透傳 payload，零改動
- `backtest_jobs` 雖然沒做 SSE patch（一次 sync 完），但 swarm 因為節點多需要中途回饋
- 既有 React app 已有 `useEventStream` hook 可直接 reuse

### D4: 失敗 run 仍存 row（`status="failed"` + 完整 error）

抄 `backtest_jobs` 的「row always exists」契約。`run_swarm` 內部 try/except 包整段 `run_review` 呼叫；任何 exception → emit `swarm_run_failed` + INSERT row with `status="failed"` + `result_json={"error": {"code": "...", "message": "..."}, "failed_node": "..." | null, "completed_nodes": ["data_loader", ...]}`。

`failed_node` 從 runner 內部 `_current_node` 變數讀（每進入新節點時更新）；不靠 event stream 推斷，避免 SSE 與 row 之間的時序競態。

### D5: Run id 格式 `swr_<12hex>`，**不**重用 review pipeline 的 `manual-<from>-to-<to>` 格式

理由：
- swarm runs 預期會比 review pipeline 跑得頻繁（admin 隨時想試一段就試），同 period 重跑會撞 `manual-...` ID
- 與 `backtest_jobs` 一致（用 short uuid hex），detail page URL 可保持簡潔

`run_review(...)` 內部會用自己的 `review_id` 在 `reviews/` 下建資料夾；swarm `result_json` 內存的是 `review_id` 字串供前端 cross-link 到 `/reviews/:reviewId`。

### D6: DAG viewer v0 用 vertical stepper，不畫真 graph

Phase 5 是 sequential，5 個節點直線排列，沒必要載 d3/elkjs/cytoscape。v0+N 真有 DAG preset（如 decider swarm 含並行子節點）才需要：

```
1. data_loader   ✓ done   123ms
2. attributor    ⟳ running
3. aggregator    · queued
4. critic        · queued
5. proposer      · queued
```

每 row click 展開 `<pre>` 顯示對應節點 output（從 `result_json.node_outputs[node_name]` 拿；schema 同 review pipeline 落檔的 6 個 file 內容做 inline 嵌入）。

### D7: 路由設計 — `/swarm/:preset/:runId` 而非 `/swarm/runs/:runId`

理由：與 `docs/web-admin-page-designs.md` 一致；`preset` 段未來可用來分流 viewer renderer（Phase 5 用 stepper、decider swarm 用真 DAG）。

對 backend：`GET /api/admin/swarm/runs/{id}` 不含 `:preset`（id 全域 unique）；前端從 row 的 `preset` 欄位 redirect 即可。`/swarm/:preset/:runId` 進頁時 fetch by id，若 row.preset !== url.preset → redirect 到正確的 `/swarm/<row.preset>/<id>`。

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| Sync 執行 5min 內 HTTP connection 斷線 → client 看不到 final row | SSE detail 頁仍會收到 `swarm_run_completed`，重新 fetch by id 即可；list 頁的 spinner 卡死 → 加 timeout 提示「請至 detail 頁查看」 |
| LLM API key 缺失 → `run_swarm` 在 `attributor` 節點才炸 | runner 啟動時 fail-fast：在 emit `swarm_run_started` 前先 `Settings().anthropic_api_key` 檢查；缺則 422 `invalid_input: anthropic_api_key not set` 不入 row |
| 同一 review period 重複跑 → `reviews/<review_id>/` 衝突 | 沿用 `run_review` 既有的 `force` 參數；preset_schema 暴露 `force: bool` 讓 UI 勾 |
| SSE event 順序錯亂（client 比 server 慢 reconnect 拿不到中段 event） | DAG viewer SHALL 同時 (a) 用 SSE patch 即時更新、(b) 在 detail 頁 mount 時 fetch by id 拿到「目前已完成的節點集合」當 baseline — 缺 event 不影響最終態正確 |
| Preset registry hardcode v0+1 加 preset 時要改 5 個 file | 接受 — v0+1 加 decider / screener preset 時本來就要改 endpoint / page renderer，順手改 registry 不增成本 |
| Phase 5 復盤實際跑時 LLM cost ~USD 0.5–2 一次，admin 隨手點會燒錢 | UI 在 RunDialog 標醒目「LLM 估算成本約 USD $X.X」（讀 `dry_run` 模式預估），且 `dry_run=true` 為勾選預設 |

## Migration Plan

無 migration — 純新增功能，`swarm_runs` 表 idempotent 創建。Rollback：移除 router include + 刪表（`DROP TABLE swarm_runs`）即可；review pipeline 與 reviews/ 目錄不受影響。

## Open Questions

- **無**。所有 v0 行為與 deferred 範圍已在 proposal 與本文件講清楚，剩下都是實作細節。
