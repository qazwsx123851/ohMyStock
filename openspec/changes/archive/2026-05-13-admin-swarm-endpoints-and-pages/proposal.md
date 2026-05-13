## Why

Phase 5 復盤 pipeline (`src/ohmystock/review/pipeline.py`) 已能跑完 5-node sequential，但 admin 沒有 UI 入口可觀察「哪個節點正在跑、跑到哪一步、輸出長什麼樣」。`/swarm` 與 `/swarm/:preset/:runId` 在 web-admin shell 仍是 stub；`docs/web-admin-page-designs.md` 早已替這兩頁定下視覺契約。把它們補齊，後續加 decider / screener swarm preset 才有共用 viewer 可掛。

選擇 **薄包裝（thin wrapper）** 而非新 orchestrator：v0 只支援 1 個 preset (`phase5-review`)，內部直接呼叫 `run_review(...)`，新增 `swarm_runs` table + 5 個 SSE event 即足以驅動 DAG viewer。維持 sync 模式（與 `backtest_jobs` 一致），不引入 queue。

## What Changes

- **新增** `swarm_runs` SQLite 表（id PK / preset / status enum / params_json / result_json / elapsed_ms / created_at）— 結構直接抄 `backtest_jobs` 的成功模式
- **新增** `src/ohmystock/swarm_runs/` 套件：`presets.py`（hardcode `PHASE5_REVIEW` preset 描述：name/description/node 順序/期望 input schema）+ `runner.py`（`run_swarm(preset_name, params, db_conn, ...) -> SwarmRunResult` 薄包裝 `run_review`，emit 5 個 SSE event，失敗時 `status="failed"` + 完整 `error.code/message` 回 row 內）
- **新增** 4 個 admin endpoints (Bearer auth + `{ok,data,error}` envelope，重用既有 `require_admin` / `to_success` / `map_exception_to_envelope`)：
  - `GET /api/admin/swarm/presets` — registry-driven，v0 只回 `[{name:"phase5-review", title, description, nodes:[...], params_schema:{...}}]`
  - `POST /api/admin/swarm/runs` — sync 跑、return run row（含完整 result_json）
  - `GET /api/admin/swarm/runs?limit=N` — `created_at DESC`，clamp 1..100，**不**洩 `result_json`
  - `GET /api/admin/swarm/runs/{id}` — 含 `result_json`，404 → `not_found`
- **新增** 5 個 EventBus event_type：`SWARM_RUN_STARTED` / `SWARM_RUN_COMPLETED` / `SWARM_RUN_FAILED` / `SWARM_NODE_STARTED` / `SWARM_NODE_COMPLETED`，agent 統一用 `Agent.REVIEWER`（v0 唯一 preset 是復盤），payload 含 `run_id` + `preset` + `node` (node-level events)
- **新增** web-admin `/swarm` 頁取代 stub：preset cards grid（v0 1 張卡）+ 「Run」按鈕觸發 `<RunSwarmDialog>`（Phase 5 preset 需 `period.from` / `period.to` / 可選 `limit_trades` / `dry_run` 4 個欄位）
- **新增** web-admin `/swarm/:preset/:runId` 頁取代 stub：header (preset title + status badge) + DAG node list（5 個節點 vertical stepper：queued / running / done / failed 4 態 + 紅漲綠跌不適用此處，以 Lucide icon + neutral colour 表示）+ 每 node click 展開 `<pre>` JSON output（從 `result_json` 取對應 file content；failed node 顯示 error.code/message）+ SSE 即時 patch（subscribe `/api/admin/events` filter `swarm_*` event_type by `run_id`）
- 重用 `src/ohmystock/review/pipeline.py` — **不**新增 orchestrator、**不**改 review pipeline 內部行為
- 重用 `src/ohmystock/api/sse.py`（既有 admin SSE channel）— 不開新 endpoint

**Intentionally deferred**: 第 2 個 preset（decider / screener）/ async / queue 模式 / 取消執行 / 中途暫停 / 重跑同 run_id / WebSocket 雙向 / proposer 自動觸發 / cron schedule / `/swarm/runs/:id/rerun` / preset YAML config / per-node 重跑

## Capabilities

### New Capabilities

- `swarm-runs`: SQLite 表 schema、`swarm.runner.run_swarm` 薄包裝行為、preset registry、4 個 admin endpoint 契約
- `web-admin-swarm-pages`: `/swarm` 與 `/swarm/:preset/:runId` 兩頁的視覺契約、SSE patch 行為、failure 顯示

### Modified Capabilities

- `eventbus-emitters`: 在 `EventType` 加入 5 個新成員 (`SWARM_RUN_STARTED` / `SWARM_RUN_COMPLETED` / `SWARM_RUN_FAILED` / `SWARM_NODE_STARTED` / `SWARM_NODE_COMPLETED`)，含對應 emitter 契約（誰在哪個時點 emit、payload 必填欄位、失敗路徑不發 `*_completed`）

## Impact

- **Affected code**:
  - 新檔: `src/ohmystock/swarm_runs/{__init__,presets,runner,storage}.py`（**注意**：`src/ohmystock/swarm/` 已被 Phase 2B Swarm Input Assembler 佔用，故此 change 用 `swarm_runs/` 名稱避免衝突；URL `/swarm/*` 與 API `/api/admin/swarm/*` 不變）
  - 新檔: `src/ohmystock/api/routes/swarm.py`
  - 修改: `src/ohmystock/eventbus/types.py`（加 5 個 enum 成員）
  - 修改: `src/ohmystock/api/app.py`（include swarm router + `swarm_storage.init_schema` 進 `_lifespan`）
  - 新檔: `web-admin/src/pages/SwarmPage.tsx`、`web-admin/src/pages/SwarmRunPage.tsx`、`web-admin/src/components/run-swarm-dialog.tsx`
  - 修改: `web-admin/src/main.tsx`（route 從 `stubs.tsx` 換到實檔）、`web-admin/src/pages/stubs.tsx`（移除 `SwarmPage` / `SwarmRunPage` 兩個 export）
  - 修改: `web-admin/src/lib/api.ts`（加 `listSwarmPresets` / `runSwarm` / `listSwarmRuns` / `getSwarmRun` + 對應型別）
- **APIs**: 4 個新 GET/POST endpoint 全在 `/api/admin/swarm/*`，沿用既有 Bearer auth 與 envelope 慣例
- **DB**: 新增 `swarm_runs` 表 — idempotent `init_schema` 在 `_lifespan` 中執行
- **EventBus**: 5 個新 event_type，沿用 `safe_emit` 容錯模式；`AdminEventSerializer` 不需改（黑箱透傳 payload）
- **Dependencies**: 無新套件
- **CLAUDE.md §5**: archive 後新增 1 row 記錄 `swarm-runs` + `web-admin-swarm-pages` SSOT
