## 1. EventBus 事件擴充

- [x] 1.1 在 `src/ohmystock/eventbus/types.py` 的 `EventType` 加入 5 個新成員：`SWARM_RUN_STARTED` / `SWARM_RUN_COMPLETED` / `SWARM_RUN_FAILED` / `SWARM_NODE_STARTED` / `SWARM_NODE_COMPLETED`
- [x] 1.2 在 `tests/test_eventbus_types.py` 擴充「全部 21 個 EventType 成員」斷言

## 2. swarm 套件骨架

- [x] 2.1 建立 `src/ohmystock/swarm_runs/__init__.py` 公開 `PRESETS` / `get_preset` / `PresetSpec`（task group 4 將擴充加入 `run_swarm` / `SwarmRunResult` / `SwarmRunnerError`）
- [x] 2.2 寫 `src/ohmystock/swarm_runs/presets.py`：`PresetSpec` (frozen pydantic, `extra="forbid"`)、`PRESETS` dict 含 `phase5-review` 一個 entry、`get_preset(name)` helper
- [x] 2.3 寫 `tests/swarm_runs/test_presets.py` 對應 spec swarm-runs §「PresetSpec 與 preset registry」3 個 scenario

## 3. swarm storage 層

- [x] 3.1 寫 `src/ohmystock/swarm_runs/storage.py`：`init_schema(conn)` idempotent CREATE TABLE + index、`SwarmRunRowDict` TypedDict、`insert_run(conn, row)` / `select_recent(conn, limit)` / `select_by_id(conn, id)` 三 helper
- [x] 3.2 寫 `tests/swarm_runs/test_storage.py` 對應 spec swarm-runs §「swarm_runs SQLite 表 schema」3 個 scenario + 額外 round-trip / select_recent ordering tests（共 6 個）
- [x] 3.3 在 `src/ohmystock/api/app.py` 的 `_lifespan` 內依「backtest_storage.init_schema → swarm_runs_storage.init_schema → memory_init_schema」順序加 swarm 一行

## 4. swarm runner 主邏輯

- [x] 4.1 寫 `src/ohmystock/swarm_runs/runner.py`：`SwarmRunResult` (frozen dataclass)、`SwarmRunnerError(Exception)`、`run_swarm(...)` async function
- [x] 4.2 在 `run_swarm` 內：preset / params 驗證 → API key 檢查 → emit `swarm_run_started` → emit first-node started → 呼叫 `run_review` → 回來後依序 emit 剩餘 4 節點 started/completed → insert row → emit `swarm_run_completed`
- [x] 4.3 在 `run_swarm` 內失敗路徑：catch `Exception`（**不**含 `BaseException`），用 `_infer_failed_node` 走檔案存在順序判斷失敗節點，insert `status="failed"` row + emit `swarm_run_failed`，return `SwarmRunResult(status="failed", ...)` 不重新 raise
- [x] 4.4 寫 `tests/swarm_runs/test_runner.py` 對應 spec swarm-runs §「run_swarm」5 個 scenario（happy path 12 events / 中途失敗 / fail-fast / 未知 preset / invalid params），mock `run_review` 與 spy queue
- [x] 4.5 寫 `tests/test_eventbus_emitter_swarm.py` 對應 spec eventbus-emitters § Swarm runner emitter 主要場景 — bus 拋例外不影響主流程（其他 3 場景由 test_runner 涵蓋）

## 5. /api/admin/swarm/* 4 個 endpoint

- [x] 5.1 寫 `src/ohmystock/api/routes/swarm.py`：APIRouter prefix `/api/admin/swarm`、`Depends(require_admin)` 套全部 4 endpoint、宣告 `_INVALID_NAME_TOKENS` 常數鏡像 admin-proposals 的 path-traversal 防禦
- [x] 5.2 實作 `GET /presets`：直接序列化 `PRESETS.values()`、回 `{items: [...]}`
- [x] 5.3 實作 `POST /runs`：`SwarmRunRequest` pydantic model (`extra="forbid"`)、handler `await run_swarm(...)`、`SwarmRunnerError` 依 prefix 對應 envelope code (`missing_api_key:` → 422 / `invalid_params:` → 400 / `unknown_preset:` → 400 / 其他 → 422 `swarm_runner_failed`)、成功回 `SwarmRunRow`（result_json parsed）
- [x] 5.4 實作 `GET /runs?limit=N`：clamp 1..100、`limit < 1` → 400、不洩 `params_json`/`result_json`，呼叫 `select_recent` 後 map 成 5-key summary
- [x] 5.5 實作 `GET /runs/{id:path}`：path-traversal validate (BEFORE I/O)、`select_by_id` → 404 `not_found` 若 None、否則 parse `params_json`/`result_json` 回 7-key SwarmRunRow
- [x] 5.6 在 `src/ohmystock/api/app.py` 的 `create_app()` 內 include swarm router
- [x] 5.7 寫 `tests/api/test_admin_swarm_endpoints.py` 對應 spec swarm-runs 4 個 endpoint requirement 的全部 14 個 scenario（含 auth 401、path-traversal 400、limit clamp、404、未知 preset、缺 API key 422、extra 欄位拒絕等）

## 6. web-admin api.ts helper

- [x] 6.1 在 `web-admin/src/lib/api.ts` 加 `SwarmPreset` / `SwarmRunRequest` / `SwarmRunSummary` / `SwarmRunRow` 4 個 TypeScript type
- [x] 6.2 加 `listSwarmPresets()` / `runSwarm(body)` / `listSwarmRuns(limit?)` / `getSwarmRun(id)` 4 個 helper（沿用既有 `apiFetch` 與 envelope 解包）

## 7. /swarm 頁

- [x] 7.1 寫 `web-admin/src/pages/SwarmPage.tsx`：header + responsive 1/2/3-col card grid + `useQuery(['swarm-presets'], listSwarmPresets)` + 每 card 含 title / description / 5 顆 node `<Badge variant="outline">` + `[Run...]` button
- [x] 7.2 處理 loading（3 skeleton card h-[180px]）/ error（destructive Card + retry）/ empty（中性提示）3 態
- [x] 7.3 點 `[Run...]` 開 `<RunSwarmDialog>`（state 控制）

## 8. <RunSwarmDialog>

- [x] 8.1 寫 `web-admin/src/components/run-swarm-dialog.tsx`：controlled `<Dialog>` props `{open, onOpenChange, preset}` + `<DialogTitle>` + `<DialogDescription>`
- [x] 8.2 表單 5 欄（每欄 `<label htmlFor>`）：period_from/period_to (date)、limit_trades (number, optional)、dry_run (Checkbox defaultChecked + AlertTriangle)、force (Checkbox)
- [x] 8.3 Submit handler：呼 `runSwarm(...)`、loading 顯示 `Loader2 motion-reduce:animate-none`、成功 toast + invalidate `['swarm-runs']` + `onOpenChange(false)` + navigate `/swarm/<preset>/<run_id>`
- [x] 8.4 失敗：保留 dialog + 底部 `role="alert" aria-live="polite"` 紅字 `{code}: {message}`
- [x] 8.5 form values（period_from / period_to / limit_trades）persist 到 `localStorage['ohmystock.admin.lastSwarm']`，`dry_run`/`force` 永遠 reset 預設

## 9. /swarm/:preset/:runId 頁

- [x] 9.1 寫 `web-admin/src/pages/SwarmRunPage.tsx`：`useParams` 取 preset/runId、`useQuery(['swarm-run', runId], () => getSwarmRun(runId))`
- [x] 9.2 Header：返回連結 + `<h1>` preset.title + runId + status `<Badge>` (`completed` secondary / `failed` destructive)
- [x] 9.3 Meta 區：created_at / elapsed_ms / 若有 `result.review_id` 顯示 `<Link to="/reviews/...">`
- [x] 9.4 Vertical stepper：5 row × 4 狀態（done/running/failed/queued）對應 4 個 Lucide icon (CheckCircle2/Loader2/XCircle/Circle) + 文字標籤 + `aria-hidden="true"` icons + `motion-reduce:animate-none` Loader2；每 row 是 `<button>` 帶 `aria-expanded`/`aria-controls` + `focus-visible:ring-2`，click/Enter/Space 展開 `<pre>` 顯示 `result.node_outputs[node]`，failed node 額外顯示 `result.error.message`
- [x] 9.5 SSE patch：透過既有 `useLiveFeedStore` (mounted globally via `useAdminEvents`) filter `event_type.startsWith("swarm_") && payload.run_id === runId`，patch local stepper state（不 refetch）；stepper 容器 `aria-live="polite"`
- [x] 9.6 處理 404（empty state「找不到 run」+ 返回連結，**不**用 destructive Card）/ error（destructive Card + retry）/ loading（header skeleton + 5 row skeleton）3 態

## 10. 路由 wiring 與 stubs 清理

- [x] 10.1 在 `web-admin/src/router.tsx` 將 `/swarm` route 從 `stubs.SwarmPage` 換成新 `SwarmPage`（從 `@/pages/SwarmPage` 直接 import）
- [x] 10.2 將 `/swarm/:preset/:runId` route 從 `stubs.SwarmRunPage` 換成新 `SwarmRunPage`（從 `@/pages/SwarmRunPage` 直接 import）
- [x] 10.3 從 `web-admin/src/pages/stubs.tsx` 移除 `SwarmPage` 與 `SwarmRunPage` 兩個 export 行（保留 `ChatPage`/`ChatSessionPage`/`SessionsPage` 不動）

## 11. 整合測試 + 手動 smoke

- [x] 11.1 跑 `uv run pytest tests/swarm_runs/ tests/api/test_admin_swarm_endpoints.py tests/test_eventbus_emitter_swarm.py tests/test_eventbus_types.py` — 34 passed
- [x] 11.2 跑 `npx tsc --noEmit -p tsconfig.app.json`（web-admin）— exit 0；`npx vitest run` — 227 passed
- [ ] 11.3 啟 backend (`uv run ohmystock api`) + frontend (`cd web-admin && npm run dev`)，手動驗（**deferred**：live smoke 需要 dev 環境，預定下個 session 由人工執行）：
  - 進 `/swarm` 看到 phase5-review card
  - 點 Run、勾 dry_run、填一段近期區間、Submit
  - 跳轉 `/swarm/phase5-review/swr_xxx`、看到 5 個節點 done、Badge=completed
  - SSE 即時更新測試（dry_run 跑很快，可改用真 review 觀察 stepper running → done 切換）
  - 故意把 `ANTHROPIC_API_KEY` 改錯重跑，detail 頁看到 status=failed、failed_node 標記正確
- [ ] 11.4 確認 `swarm_runs` 表內有對應 row、`reviews/manual-...-to-...` 資料夾（dry_run=false 時）已產出（**deferred** with 11.3）

附帶：完整 1292 個 backend pytest（排除 3 個預先存在的 env-leak 失敗 test_api_auth + test_settings_admin_token）全綠；`openspec validate admin-swarm-endpoints-and-pages --strict` 通過。
