# web-admin 使用者情境測試規格（後台 Operator Journey）

> **目的**：把 `docs/user-scenarios.md` 的 operator 動線，落成可驗收 / 可 1:1 轉 E2E 測試碼的情境規格。
> **範圍**：web-admin 後台全頁（Tier 0–4）。公網 web-public 不在此檔。
> **角色**：Mark（唯一 admin）。
> **撰寫依據**：實讀 `web-admin/src/pages/*`、`web-admin/src/components/*`、`src/ohmystock/api/routes/*`、對應 service 層（confirm_gate / proposal / memory）。本檔以**實作現況**為準，文件預期與實作的偏離單獨標註。
> **本輪只出規格，不寫測試碼**。
> **最後更新**：2026-06-07

---

## 圖例

| 標記 | 意義 |
|---|---|
| `[可測]` | 功能已實作，**現在就能測** |
| `[BLOCKED]` | **功能未實作**；GWT 寫的是「日後實作的驗收標準」，非當前可跑 |
| `[偏離]` | doc-vs-impl 偏離（`user-scenarios.md` 與實作不一致） |
| `P0/P1/P2` | 優先序（P0 = 碰錢/不可逆，最優先） |

每個情境格式：`ID 標題｜優先序｜頁面/路由｜endpoint｜來源§` → 前置條件 → 一至多條 Given/When/Then。GWT 的 Then 即為斷言點。

---

## 0. 總覽矩陣

| ID | 情境 | 頁面 | 優先序 | 狀態 |
|---|---|---|---|---|
| **Tier 0 — 核心交易動作（Confirm Gate）** | | | | |
| CG-01 | confirm 進場決策 | /paper | P0 | [可測] |
| CG-02 | reject 決策 | /paper | P0 | [可測] |
| CG-03 | sweep 過期決策 | /paper | P0 | [可測] |
| CG-04 | 鍵盤快捷 y/n/sweep | /paper | P1 | [可測] |
| CG-05 | 待確認佇列載入/空/倒數 | /paper | P1 | [可測] |
| CG-06 | SSE 即時刷新 | /paper | P2 | [可測] |
| CG-B1 | confirm 二次輸入張數 | /paper | P1 | [可測]（已實作） |
| CG-B2 | reject 自訂原因 | /paper | P1 | [可測]（已實作） |
| **Tier 1 — 提案狀態機** | | | | |
| PR-01 | pending → validating | /proposals/:slug | P1 | [可測] |
| PR-02 | validate（dry-run/pass/fail） | /proposals/:slug | P0 | [可測] |
| PR-03 | approve → merged | /proposals/:slug | P0 | [可測] |
| PR-04 | reject 路徑 | /proposals/:slug | P1 | [可測] |
| PR-05 | 終態守恆（merged/rejected 無 action） | /proposals/:slug | P1 | [可測] |
| PR-06 | 非法轉移 / 缺欄位錯誤 | /proposals/:slug | P1 | [可測] |
| PR-B1 | Re-validate 按鈕 | /proposals/:slug | P2 | [可測]（已實作） |
| **Tier 2 — 觸發長任務** | | | | |
| SW-01 | swarm 觸發 → 導向 DAG | /swarm | P1 | [可測] |
| SW-02 | swarm 節點 SSE 進度 | /swarm/:preset/:runId | P2 | [可測] |
| BT-01 | backtest 提交 → 列表刷新 | /backtest | P1 | [可測] |
| BT-02 | backtest 結果頁 | /backtest/:jobId | P2 | [可測] |
| BT-03 | backtest 表單驗證 / 錯誤 | /backtest | P1 | [可測] |
| SC-01 | screener 觸發 → 就地結果 | /market | P1 | [可測] |
| SC-02 | screener pattern SSE flash | /market | P2 | [可測] |
| **Tier 3 — 讀取面** | | | | |
| DB-01 | Dashboard KPI 四卡 | / | P1 | [可測] |
| DB-02 | LiveFeed SSE | / | P2 | [可測] |
| DB-B1 | risk gate 三色燈 | / | P0 | [可測]（已實作） |
| DB-B2 | 月度熔斷 banner | / | P0 | [可測]（已實作） |
| DB-B3 | LLM 成本進度條變色 | / | P2 | [可測]（已實作） |
| AU-01 | 多選 kind filter（回歸鎖定） | /audit | P1 | [可測] |
| AU-02 | 空結果 / 錯誤 / 分頁 | /audit | P2 | [可測] |
| AU-03 | status badge 推斷 | /audit | P2 | [可測] |
| PP-01 | 距停損%/距T1% 計算（回歸鎖定） | /paper/positions | P1 | [可測] |
| PP-02 | 紅漲綠跌 + 方向 icon | /paper/positions | P2 | [可測] |
| PP-03 | detail toggle / 空持倉 / 缺值 | /paper/positions | P2 | [可測] |
| **Tier 4 — 設定與記憶** | | | | |
| ST-01 | Settings 唯讀載入 | /settings | P2 | [可測] |
| ST-02 | API key badge（不洩漏明文） | /settings | P1 | [可測] |
| ST-03 | Safety 視覺分化 | /settings | P1 | [可測] |
| ST-04 | Breaker 格式化 | /settings | P2 | [可測] |
| ST-B1 | Shioaji/FinMind 連線測試 | /settings | P1 | [可測]（已實作） |
| ST-B2 | 剩餘額度 / 模型分布 | /settings | P2 | [可測]（已實作） |
| ME-01 | 瀏覽 + kind/tag filter | /memory | P2 | [可測] |
| ME-02 | FTS5 搜尋(BM25) | /memory | P2 | [可測] |
| ME-03 | 搜尋語法錯誤 | /memory | P2 | [可測] |
| ME-04 | 分頁 / 展開 / 空結果 | /memory | P2 | [可測] |
| ME-B1 | 寫入個人偏好 | /memory | P1 | [可測]（已實作） |
| **跨頁** | | | | |
| GATE-01 | 未授權導向 /login | 全部 | P0 | [可測]（smoke 已有） |
| GATE-02 | 全頁載入無 console error | 全部 | P1 | [可測]（smoke 已有） |

---

## 0.1 doc-vs-impl 落差總表（roadmap 用）

> 這些是 `user-scenarios.md` 寫了、但實作沒做或做得不同的點。每筆要嘛補實作、要嘛改文件。

| # | 主題 | user-scenarios.md | 實作現況 | 建議 |
|---|---|---|---|---|
| D1 | Confirm Gate 路由 | §2 在 `/decisions` | 內嵌在 `/paper`（PaperOverviewPage），無 `/decisions` 路由 | 已改文件（user-scenarios.md 路由同步為 `/paper`）|
| D2 | confirm 二次輸入張數 | §2「觸發 ConfirmDialog 二次輸入張數」 | 已補 ConfirmDialog + override_qty（伺服器 clamp） | 已實作（CG-B1 done）|
| D3 | reject 自訂原因 | §2「寫進 reject reason」 | 已補 reject reason dialog（CG-B2 done） | 已實作 |
| D4 | Dashboard risk gate 三色燈 | §1/§8 風險面板 | 已補 5 條件三色燈（顯示用，接法 A） | 已實作（DB-B1 done）|
| D5 | Dashboard 月度熔斷 banner | §1/§8 紅色 banner | 已補 banner（顯示用） | 已實作（DB-B2 done）|
| D6 | Dashboard 成本進度條 | §1「≥80% 橘色進度條」 | 已補進度條（≥80% 橘） | 已實作（DB-B3 done）|
| D7 | proposal 驗證後人工確認 | §6 看完 WFA 報告才點 merge/reject | validate 改為人工模式：報告產出後停在 validating，人工 Approve/Reject | 已實作（proposal-manual-verdict）|
| D8 | proposal Re-validate 按鈕 | §6「[Re-validate] 換參數重跑」 | Run Validation 已帶上次參數重驗；rejected 後端不可重驗 | 現況已滿足（PR-B1 done），文件對齊 |
| D9 | Settings 連線測試 | §9「點連線測試」 | 已補 test-connection endpoint + 按鈕 | 已實作（ST-B1 done）|
| D10 | Settings 剩餘額度/模型分布 | §9/§10 | 已補 budget 區塊（唯讀） | 已實作（ST-B2 done）|
| D11 | Memory 寫入偏好 | §10「在 /memory 寫入偏好」 | 已補寫入表單 + endpoint | 已實作（ME-B1 done）|

---

## Tier 0 — 核心交易動作（Confirm Gate）

> 全部位於 `/paper`（PaperOverviewPage）。[偏離] 文件說的 `/decisions` 不存在（D1）。
> 後端：`src/ohmystock/api/routes/confirm_gate.py`、service `src/ohmystock/safety/confirm_gate.py`。
> 成功回應一律 envelope `{ ok: true, data: {...} }`；錯誤 `{ ok: false, error: { code, message } }`。

### CG-01 confirm 進場決策｜`P0`｜/paper｜`POST /api/admin/confirm-gate/confirm`｜§2 [可測]

**前置**：seed 一筆 `kind=entry` 且 `decision_status=pending_confirm` 的決策（payload 含 `final_sizing_pct`、`current_price`、`atr_14_pct`），GET pending 回傳該筆。

- **Given** 待確認佇列有一筆 `decision_id=d1`
  **When** 點該卡 `[確認]`
  **Then** 送出 `POST /confirm` body `{ decision_id:"d1", user:"mark" }`（**無張數 dialog**）
  **And** 成功回 200 `data:{ decision_id, fill:{ fill_price, filled_qty, fill_ts }, qty }`
  **And** refetch 後該卡從佇列消失、持倉表 +1、`decisions_made`/`entries_filled` 統計更新
  **And** DB：該 entry 行 `decision_status → confirmed`、寫入 `actual_entry_price`/`actual_qty`/`stop_loss_price`/`human_confirmed_by`/`human_confirmed_at`、`auto_executed=false`
  **And** 發 `EventType.ORDER_SENT`（payload 含 symbol/price/quantity/broker_order_id）
  **And** confirm **不新增** journal 行（只更新既有 entry 行）

- **Given** `decision_id` 不存在
  **When** confirm
  **Then** 404 `error.code=not_found`

- **Given** 決策已非 pending_confirm（已 confirmed/rejected/expired）
  **When** confirm
  **Then** 409 `error.code=not_pending`

- **Given** payload 缺 `final_sizing_pct`/`current_price`/`atr_14_pct`
  **When** confirm
  **Then** 409 `error.code=payload_invalid`

- **Given** 紙本券商下單失敗
  **When** confirm
  **Then** 502 `error.code=broker_failed`；佇列卡片**不消失**（狀態仍 pending）

### CG-02 reject 決策｜`P0`｜/paper｜`POST /api/admin/confirm-gate/reject`｜§2 [可測]

**前置**：同 CG-01 的 pending 決策。

- **Given** 佇列有 `d1`
  **When** 點 `[拒絕]`
  **Then** 送 `POST /reject` body `{ decision_id:"d1", user:"mark", reason:"user_reject" }`（[偏離] reason 寫死，見 CG-B2）
  **And** 200 `data:{ decision_id, reject_row_id }`
  **And** refetch 後卡片消失
  **And** DB：新增 `kind=reject` journal 行（payload `decision_status=rejected`、`reject_layer=human`、`reject_reason`、`rejected_by`、`rejected_at`）；entry 行 `decision_status → rejected`
  **And** 發 `journal_written`（kind=reject）

- **Given** 後端收到空白 reason（理論上 UI 不會發生，但需鎖後端契約）
  **When** reject
  **Then** 400 `error.code=invalid_input`

- **Given** `d1` 已非 pending_confirm
  **When** reject
  **Then** 409 `error.code=not_pending`

### CG-03 sweep 過期決策｜`P0`｜/paper｜`POST /api/admin/confirm-gate/sweep-expired`｜§2 [可測]

**前置**：seed 兩筆 pending、其中 `d1`、`d3` 的 `created_at` 已超過 `timeout_minutes`（預設 30 分）。

- **Given** 標題列 `[sweep 過期]` 按鈕
  **When** 點擊
  **Then** 先跳 `window.confirm('確定要 sweep 所有過期的待確認單？')`
  **And** 按確定後送 `POST /sweep-expired` body `{}`
  **And** 200 `data:{ swept_decision_ids:["d1","d3"], swept_count:2, timeout_minutes }`
  **And** refetch 後過期卡片全部消失，未過期的保留
  **And** DB：每筆過期 entry 新增 `kind=expire` journal 行（payload `decision_status=expired`、`expire_reason="confirm timeout after N minutes"`、`expired_at`）；每筆發一次 `journal_written`

- **Given** window.confirm 按取消
  **When** 點擊 sweep
  **Then** 不送任何請求

- **Given** `timeout_minutes <= 0`（覆蓋值非法）
  **When** sweep
  **Then** 400 `error.code=invalid_input`

### CG-04 鍵盤快捷｜`P1`｜/paper [可測]

- **Given** focus 在某 `[data-pending-card][data-decision-id=d1]` 卡片，且 focus 不在 input/textarea/contentEditable
  **When** 按 `y`（無修飾鍵）
  **Then** 等同 CG-01 confirm(d1)

- **Given** 同上 focus
  **When** 按 `n`
  **Then** 等同 CG-02 reject(d1)

- **When** 按 `Ctrl/Cmd + Shift + E`（**不需** focus 卡片，全域）
  **Then** 等同 CG-03 sweep（含 window.confirm）

- **Given** focus 在 input/textarea
  **When** 按 `y`/`n`
  **Then** **不觸發**任何動作（不可誤觸）

- **Given** 無卡片 focus
  **When** 按 `y`/`n`
  **Then** 不觸發

### CG-05 待確認佇列載入｜`P1`｜/paper｜`GET /api/admin/confirm-gate/pending` [可測]

- **Given** 有 N 筆 pending
  **When** 進 /paper
  **Then** 佇列依 `created_at` 由早到新排序；每卡顯示 symbol（font-mono）、current_price（2 位小數）、final_sizing_pct
  **And** 每卡顯示倒數「剩餘 {remaining}s / {ttl}s」，`remaining = max(0, ttl_seconds - age_seconds)`
  **And** 倒數進度條 `remainingPct > 33%` 綠色、否則黃色

- **Given** 無 pending
  **When** 進 /paper
  **Then** 顯示「目前無待確認」空狀態，無卡片

### CG-06 SSE 即時刷新｜`P2`｜/paper [可測]

- **Given** /paper 已開
  **When** 推入 event_type ∈ `{ awaiting_confirm, order_sent, decision_made, journal_written, risk_off_triggered }`
  **Then** 觸發 invalidateAll → 重新 fetch stats/positions/pending

- **When** 推入非白名單 event_type
  **Then** 不 refetch

### CG-B1 confirm 二次輸入張數｜`P1`｜/paper｜[BLOCKED][偏離]（D2）

> **BLOCKED**：目前 confirm 直接送出、qty 由後端 sizing 決定，無 dialog。以下為補實作後的驗收標準。

- **Given** 點 `[確認]`
  **When** （實作後）跳 ConfirmDialog 顯示後端建議張數、可手動覆寫
  **Then** 送出的 body 帶使用者輸入的 qty，後端以該 qty 下單（仍受 sizing clamp 防線約束）

### CG-B2 reject 自訂原因｜`P1`｜/paper｜[可測]（D3，已實作）

- **Given** 點卡片 `[✗ 拒絕]`（或鍵盤 n）
  **When** 開啟 reject dialog、輸入非空原因、點「確認拒絕」
  **Then** 送 `reject` body `{ decision_id, user:"mark", reason }` 帶該文字，journal `reject_reason` 落該文字，成功後 dialog 關閉、卡片消失
- **Given** dialog 開啟、原因空白
  **When** 檢視「確認拒絕」按鈕
  **Then** 按鈕 disabled、不送出

---

## Tier 1 — 提案狀態機

> 頁面 `/proposals/:slug`（ProposalDetailPage）+ `transition-dialog.tsx` / `validation-dialog.tsx`。
> 後端 `src/ohmystock/api/routes/proposals.py`、state machine `src/ohmystock/proposal/state.py`。
> **狀態**：`pending → validating → approved → merged`，validating/approved 皆可 `→ rejected`。merged/rejected 為終態。

### PR-01 pending → validating｜`P1`｜`POST /api/admin/proposals/{slug}/transition` [可測]

**前置**：seed 一筆 `status=pending` 提案。

- **Given** 提案 status=pending
  **Then** ActionRow 只顯示 `[Mark Validating]` 單一按鈕
  **When** 點擊 → 填 actor → 送 `transition` body `{ new_status:"validating", actor }`
  **Then** 200 `data:{ slug, new_status:"validating", new_path }`
  **And** dialog 關閉、`['proposal',slug]` 與 `['proposals']` 快取失效刷新
  **And** changelog 追加一行 `- {ts} status: pending → validating by {actor}`

### PR-02 validate（dry-run / pass / fail）｜`P0`｜`POST /api/admin/proposals/{slug}/validate` [可測]

**前置**：提案 status=validating；策略列表能載入。

- **Given** validating 狀態
  **Then** ActionRow 顯示 `[Run Validation…] [Approve…] [Reject…]`
  **When** 開 ValidationDialog，填 strategy/period from-to/universe（必填）、wfa_windows(≥2)/in_sample_ratio(0~1)/initial_capital(>0)，**勾 dry run**
  **Then** 送 `validate` body 含上述欄位 `dry_run:true`
  **And** 回 `verdict=pass|fail`、`new_status:"validating"`（**不轉狀態、不搬檔**）
  **And** toast「Dry run: verdict=… — no state change」

- **Given** dry_run 取消勾選、verdict=pass
  **When** validate
  **Then** 提案**自動**轉 `approved`、檔搬 `PENDING_REVIEW/`、存 `*.validation.json`，toast「moved to PENDING_REVIEW」
  （[偏離] D7：文件 §6 假設人工看報告後才轉，實作自動轉）

- **Given** dry_run 取消勾選、verdict=fail
  **When** validate
  **Then** 提案**自動**轉 `rejected`、檔搬 `rejected/`，toast 顯示 failure 數

- **Given** validate endpoint 收到非 validating 提案
  **Then** 409 `illegal_transition`

- **Given** WFA 執行失敗（參數無法計算）
  **Then** 422 `wfa_validation_failed`

- **欄位持久化**：`strategy/universe/wfa_windows/in_sample_ratio/initial_capital` 存 localStorage `ohmystock.admin.lastValidation`；`period/param_overrides/dry_run` 每次重置。

### PR-03 approve → merged｜`P0`｜transition [可測]

**前置**：提案 status=approved。

- **Given** approved 狀態
  **Then** ActionRow 顯示 `[Mark Merged…] [Reject…]`
  **When** 開 TransitionDialog 填 `merged_to_version`（必填）+ actor → 送 `{ new_status:"merged", actor, merged_to_version }`
  **Then** 200，status→merged、檔搬 `merged/`、frontmatter 加 `merged_to_version`/`merged_at`
  **And** 不可逆（見 PR-05）

- **Given** approved 但未填 `merged_to_version`
  **Then** 400 `missing_merged_to_version`

### PR-04 reject 路徑｜`P1`｜transition [可測]

- **Given** validating **或** approved
  **When** 點 `[Reject…]` 填 reason(必填)+actor → `{ new_status:"rejected", actor, reason }`
  **Then** 200，status→rejected、檔搬 `rejected/`、frontmatter 加 `rejected_reason`

- **Given** 未填 reason
  **Then** 400 `missing_rejection_reason`

- **Given** 未填 actor（任何轉移）
  **Then** 400 `missing_actor`

### PR-05 終態守恆｜`P1` [可測]

- **Given** status=merged
  **Then** ActionRow 完全隱藏，顯示「終局狀態」只讀卡片；其餘內容（header/body/changelog）正常

- **Given** status=rejected
  **Then** 同上，無任何 action 按鈕

### PR-06 非法轉移 / slug 防護｜`P1` [可測]

- **Given** 直跳 `pending → approved`
  **Then** 409 `illegal_transition`

- **Given** slug 含路徑遍歷（`/`、`\`、`..`）
  **Then** 400 `invalid_input`

- **Given** 目標路徑已存在同名檔
  **Then** 409 `conflict`

### PR-B1 Re-validate 按鈕｜`P2`｜[可測]（D8，現況已滿足）

> 現況已滿足：validating 狀態的 `[Run Validation…]` 開啟 ValidationDialog 時即從 localStorage `ohmystock.admin.lastValidation` 帶入上次參數（strategy/universe/wfa_windows/in_sample_ratio/initial_capital），等同 Re-validate。rejected 為終態且後端 validate 要求 `status=validating`，不可重驗（PR-05 終態守恆）。

- **Given** validating 提案、localStorage 有上次驗證紀錄
  **When** 點 `[Run Validation…]`
  **Then** ValidationDialog 預填上次參數
- **Given** 無 localStorage 紀錄
  **When** 開 ValidationDialog
  **Then** 使用預設值

---

## Tier 2 — 觸發長任務

### SW-01 swarm 觸發 → 導向 DAG｜`P1`｜/swarm｜`POST /api/admin/swarm/runs` [可測]

- **Given** /swarm preset 卡片
  **When** 點 `[Run…]` 開 RunSwarmDialog，填 `period_from`/`period_to`（必填）、limit_trades(≥1 或空)、dry_run(預設 true)/force(預設 false)
  **Then** Submit 啟用條件 = 兩日期非空 且 (limit 空 或 ≥1)
  **When** 送 `POST /runs` body `{ preset, params:{ period_from, period_to, limit_trades, dry_run, force } }`
  **Then** 200 `data:{ id, preset, status:"completed"|"failed", result, elapsed_ms, created_at }`
  **And** dialog 關閉、`['swarm-runs']` 失效、toast「Swarm 完成/失敗 — {id}」
  **And** **導向** `/swarm/{preset}/{id}`
  **And** 參數存 localStorage `ohmystock.admin.lastSwarm`（dry_run/force 每次重置）

- **Given** `limit_trades < 1`
  **Then** 400 `invalid_input`

- **Given** unknown preset / 缺 API key / runner 例外
  **Then** 400 `invalid_input` / 422 `missing_api_key` / 422 `swarm_runner_failed`；dialog **保持開啟**顯示 inline error

### SW-02 swarm 節點 SSE 進度｜`P2`｜/swarm/:preset/:runId [可測]

- **Given** 進 SwarmRunPage，初始 `GET /runs/{runId}` 取 result（含 completed_nodes/node_outputs）
  **Then** 五節點 `data_loader→attributor→aggregator→critic→proposer` 依 result 顯示基線狀態
  **When** 推入 `swarm_node_started`（payload.run_id===runId）
  **Then** 對應節點轉 running；`swarm_node_completed` → done；`swarm_run_failed` → 整 run failed 並標 `failed_node`
  **And** 節點 row 可點擊展開該節點 JSON 輸出 / 錯誤

### BT-01 backtest 提交 → 列表刷新｜`P1`｜/backtest｜`POST /api/admin/backtest/run` [可測]

- **Given** /backtest 表單（strategy 預設 sma_cross、symbols chip、period、initial_capital 預設 1,000,000）
  **When** chip 輸入 symbol，正則 `^\d{4,6}$` 才接受、重複拒絕
  **When** 點 `[跑回測]`（或 Cmd/Ctrl+Enter）送 `POST /run` body `{ strategy, symbols, period_from, period_to, initial_capital, ... }`
  **Then** 200 `data:{ job_id, status:"completed"|"failed", elapsed_ms }`
  **And** `['backtest','jobs']` 失效刷新列表；**無 toast、無自動導向**；表單欄位保留

### BT-02 backtest 結果頁｜`P2`｜/backtest/:jobId｜`GET /api/admin/backtest/jobs/{id}` [可測]

- **Given** 點歷史列表某 job 進結果頁
  **Then** 一次性載入 metrics/equity_curve/drawdown/trades（**無輪詢/SSE**）
- **Given** job status=failed
  **Then** KPI 顯示「—」、圖區「無資料 — job 失敗」、紅 alert 顯示 `error.code: message`

### BT-03 backtest 表單驗證 / 錯誤｜`P1`｜/backtest [可測]

| Given | Then |
|---|---|
| symbols 空 | 400 `invalid_input`（後端 min_length=1）|
| symbols > 50 | 400 `input_too_large` |
| unknown strategy | 400 `invalid_input` |
| period_to < period_from | 400 `invalid_input` |
| 期間 > 1830 天 | 400 `input_too_large` |
| initial_capital ≤ 0 | 400 `invalid_input` |
| 某 symbol 無 bars | 400 `missing_bars` |
| engine 崩潰 | 500 `engine_error` |

- 非 2xx → 紅 alert + `[重試]`，表單保留。

### SC-01 screener 觸發 → 就地結果｜`P1`｜/market｜`POST /api/admin/screener/run` [可測]

- **Given** /market 表單（universe dropdown、custom symbols chip、asof_date 預設今天、4 個 filter checkbox：SEPA/RS≥80/法人連買/三角收斂）
  **When** 勾選 filter → 組成 `filters:[{sepa:true},{rs_min:80},...]`；未勾為 `null`；custom 空為 `null`
  **When** 點 `[跑 screener]`（或 Cmd/Ctrl+Enter）送 `POST /run` body `{ universe, custom_symbols, filters, asof_date }`
  **Then** 200 `data:{ run_id, hits:[{symbol,name,price,change_pct,pattern,score}], elapsed_ms }`
  **And** 結果**就地**顯示於表格（無導向）；summary 顯示 `r#{run_id} · {asof} · 共 N 命中 · {sec}s`；表單保留

- **Given** zero hits
  **Then** 200 + 顯示「本次掃描無命中」

- **Given** unknown universe / 非法 symbol / 未來 asof_date
  **Then** 400 `invalid_input`；engine 超時 → 500 `screener_timeout`；非 2xx → 紅 alert + `[重試]`

### SC-02 screener pattern SSE flash｜`P2`｜/market [可測]

- **Given** screener 跑動中
  **When** 推入 `pattern_detected`（payload symbol/name/price/change_pct/pattern/score）
  **Then** 新 row prepend 到表格頂、黃底 flash 0.5s（`_flashUntil`）；同 symbol 舊 row 移除避免重複
  **And** 右側即時事件區顯示最近 5 筆（buffer 20）

---

## Tier 3 — 讀取面

### DB-01 Dashboard KPI 四卡｜`P1`｜/｜`GET /api/admin/stats/today` [可測]

- **Given** stats 回 `{ realized_pnl_twd, open_positions, pending_confirms, llm_cost_usd }`
  **Then** 四卡顯示；已實現損益帶正負號格式（+12,345 TWD），>0 → `data-direction=up` + `.text-up` + ↑、<0 → down/紅
  **And** 每 30s 自動 refetch（`refetchInterval:30_000`）

- **Given** 載入中 → skeleton；載入失敗 → 紅 banner「載入今日 KPI 失敗：{message}」；data=null → 卡片空值。

### DB-02 LiveFeed SSE｜`P2`｜/ [可測]

- **Given** SSE 推事件
  **Then** LiveFeed 顯示最新（上限 20 筆），每筆依前綴選 icon：`confirm_gate.*`沙漏 / `order.*`公事包 / `auto_execute.*`美元 / 其他 activity；時間顯示相對時間。

### DB-B1 risk gate 三色燈｜`P0`｜/｜[BLOCKED][偏離]（D4）

> **BLOCKED**：Dashboard 無 risk gate 面板。補實作後驗收：

- **Given** 系統旗標
  **Then** 綠燈 正常 / 黃燈 警戒（watchlist 需細看）/ 紅燈 Risk-Off
  **And** 觸發條件對應 `workflow-cheatsheet.md` §0（加權跌破 60MA / SPY 5日<-3% / VIX>25 / TWD 貶>0.5% / 外資台指期淨空連 3 日新高）任一 → 紅燈

### DB-B2 月度熔斷 banner｜`P0`｜/｜[BLOCKED][偏離]（D5）

> **BLOCKED**：補實作後驗收：

- **Given** 月 PnL ≤ -8%（月度熔斷）
  **Then** Dashboard 顯示紅色 banner、新進場按鈕 disabled、提示須跑月度復盤解鎖

### DB-B3 LLM 成本進度條｜`P2`｜/｜[BLOCKED][偏離]（D6）

> **BLOCKED**：現只有單一數字。補實作後：本月成本進度條，≥80% 橘色、100% 提示軟熔斷（全 Sonnet）。

### AU-01 多選 kind filter（回歸鎖定）｜`P1`｜/audit｜`GET /api/admin/journal/rows` [可測]

> 這是上次 session 修過的 bug，**必須回歸鎖定**。

- **Given** 5 個有效 kind = `entry / exit / reject / expire / auto_execute_audit`（SSOT：前端 `journal-kinds.ts` ↔ 後端 `journal.py _VALID_KINDS`，兩端必須一致）
  **When** 勾選 `entry` + `reject`
  **Then** query 帶**重複** param `?kind=entry&kind=reject`（IN-clause），結果只含這兩 kind
  **When** 全不勾
  **Then** 前端重置為全選（等效 5 種全帶）
  **When** 帶無效 kind
  **Then** 後端 400 + error envelope

- 回傳 envelope（回歸鎖定）：`{ items, total, limit, offset, has_more }`。

### AU-02 空結果 / 錯誤 / 分頁｜`P2`｜/audit [可測]

| Given | Then |
|---|---|
| items=[]、total=0 | EmptyState「此 filter 無紀錄」+「清空 filter」鈕 |
| 500 | ErrorState 紅 banner +「重試」|
| date_from > date_to | 400 |
| 每頁 50 列 | 分頁；density compact↔comfortable 經 URL param |

### AU-03 status badge 推斷｜`P2`｜/audit [可測]

- **Given** row 無 status
  **Then** 依 kind 推斷：`entry/fill/exit` → executed(綠)、`reject` → rejected(紅)、`risk_off_triggered/breaker_tripped` → errored(深紅)、`awaiting_confirm` → pending(黃)、`decision_made` → approved(藍)
- 點列展開顯示 payload JSON。

### PP-01 距停損%/距T1% 計算（回歸鎖定）｜`P1`｜/paper/positions｜`GET /api/admin/positions/open` [可測]

> 上次 session 修過 envelope 形狀，**回歸鎖定**。

- **Given** 回傳 envelope `{ items, asof_iso, count }`（count === items.length）
  **And** 某持倉 entry_price=1000, stop_loss=970, t1_target=1080
  **Then** 距停損% = `((970-1000)/1000)*100 = -3.0%`、距T1% = `+8.0%`（公式：`(to-from)/from*100`，相對進場價）
  **And** 方向 `pct<0→down`、`pct>0→up`、`pct===0→neutral`

- **Given** entry_price=0
  **Then** distancePct 回 0（防除零）

### PP-02 紅漲綠跌 + 方向 icon｜`P2`｜/paper/positions [可測]

- unrealized_pnl_twd >0 → `.text-up`(綠)、<0 → `.text-down`(紅)
- side long → text-up + ↑；short → text-down + ↓

### PP-03 detail toggle / 空持倉 / 缺值｜`P2`｜/paper/positions [可測]

| Given | Then |
|---|---|
| 點某列 | Detail Panel 出現（進場時間/理由/距停損%/距T1%/time_stop）|
| 再點同列 | Detail Panel 收起 |
| stop_loss / t1_target / time_stop_date = null | 距離% 顯示「—」|
| count=0 | EmptyState「目前無開倉」|
| 500 | ErrorState +「重試」|

---

## Tier 4 — 設定與記憶

### ST-01 Settings 唯讀載入｜`P2`｜/settings｜`GET /api/admin/settings` [可測]

- **Given** 200 payload `{ api_keys{anthropic,finmind,shioaji}, theme, safety{auto_execute,broker}, breakers{...7}, chat{model_default,title_model} }`
  **Then** 4 卡片渲染、所有 input/select **disabled**、**無「儲存」按鈕**（v0 改設定需編 .env + 重啟）

- 載入中 → 4 skeleton；失敗 → role=alert 紅卡 +「重試」(refetch)；401 → 清 token + 導向 login。

### ST-02 API key badge（不洩漏明文）｜`P1`｜/settings [可測]

- **Given** api_keys 各為 bool
  **Then** 各顯示「已設定」(bg-muted) 或「未設定」(outline) badge
  **And** DOM **不出現任何金鑰明文**（只反映 `_is_set()` 非空 bool）

### ST-03 Safety 視覺分化｜`P1`｜/settings [可測]

- **Given** `auto_execute=false`
  **Then** warning border + AlertTriangle +「AUTO_EXECUTE 關閉（人工 Confirm Gate）」，顯示 broker
- **Given** `auto_execute=true`
  **Then** destructive border + AlertCircle +「AUTO_EXECUTE 已啟用」，顯示 broker

### ST-04 Breaker 格式化｜`P2`｜/settings [可測]

- min_confidence → 2 位小數「0.70」；account_equity_twd → 千分位「1,000,000」；百分比去尾數「25」。負值如 loss_pct_threshold=-0.05 → 「-5%」。

### ST-B1 Shioaji/FinMind 連線測試｜`P1`｜/settings｜[BLOCKED][偏離]（D9）

> **BLOCKED**：無連線測試鈕。補實作後：點測試 → 呼叫測試 endpoint → 成功/失敗即時呈現。

### ST-B2 剩餘額度 / 模型分布｜`P2`｜/settings｜[BLOCKED][偏離]（D10）

> **BLOCKED**：payload 無此欄位。補實作後：顯示 LLM 預算進度、軟熔斷狀態、當前模型分布。

### ME-01 瀏覽 + kind/tag filter｜`P2`｜/memory｜`GET /api/admin/memory/rows` [可測]

- **Given** 預設「瀏覽」視圖
  **Then** 表格 5 欄（時間/kind badge/tags/內容預覽 max 42ch/來源），每頁 50，按 `created_at DESC,id DESC`
  **When** kind select 改 `lesson`
  **Then** query `?kind=lesson&limit=50&offset=0`，offset 重置、展開列收起
  **When** tag chip 輸入 `vcp` + Enter
  **Then** query 含 `&tag=vcp`，chip 可 X 移除
  **And** kind 不在 {note,lesson,proposal,review_summary} → 400 `invalid_input`

### ME-02 FTS5 搜尋(BM25)｜`P2`｜/memory｜`GET /api/admin/memory/search` [可測]

- **Given** 切「搜尋」視圖（延遲載入，未輸入時不發請求、顯示「請輸入查詢關鍵字」）
  **When** 輸入 `breakout` + Enter（或 Cmd/Ctrl+Enter / 按鈕）
  **Then** query `?q=breakout&limit=50&offset=0`，結果按 `bm25() ASC` 排序
  **And** 空查詢時按鈕 disabled；CJK 保留、ASCII 控制字元被清

### ME-03 搜尋語法錯誤｜`P2`｜/memory [可測]

- **Given** 輸入非法 FTS5 如 `foo OR`
  **When** 搜尋
  **Then** 400 `error.code=invalid_query` → 顯示 inline「查詢語法錯誤」紅框
  **And** **不顯示「重試」鈕**（使用者輸入問題，非伺服器故障）

### ME-04 分頁 / 展開 / 空結果｜`P2`｜/memory [可測]

| Given | Then |
|---|---|
| 101 筆、limit50 | 點下一頁 → offset=50 新查詢 |
| 點某列 | 展開 `<pre>` 全文 + 字元數 |
| 切視圖再切回 | 展開狀態收起（DataTable key 變化重掛載）|
| 瀏覽無結果+有 filter | 「無符合條件」+「清除 filter」|
| 瀏覽無結果+無 filter | 「尚無 memory；待 Phase 5 / proposal 寫入」|
| 搜尋無結果 | 「找不到符合『{q}』的 memory」|
| 列表 500 | ErrorCard +「重試」|

### ME-B1 寫入個人偏好｜`P1`｜/memory｜[BLOCKED][偏離]（D11）

> **BLOCKED**：v0 刻意 read-only。補實作後（§10 cold start 需要）：可寫入偏好文字（風險偏好、不交易類型、可承受波動），落 memory store，可被瀏覽/搜尋檢索。

---

## 跨頁

### GATE-01 未授權導向 /login｜`P0`｜全部 [可測]（smoke 已有）

- **Given** 無 token 的 context
  **When** 開任一受保護路由
  **Then** 導向 `/login`，顯示「ohMyStock 後台登入」

### GATE-02 全頁載入無 console error｜`P1`｜全部 [可測]（smoke 已有）

- **Given** 注入合法 token
  **When** 逐一開靜態路由
  **Then** HTTP <400、不被導 /login、TopBar h1 標題正確、無非白名單 console error。
- 白名單噪音：favicon / EventSource / ResizeObserver / React DevTools / 404 資源 / net::ERR_。

---

## 附錄 A — seed 資料需求（依情境）

| 情境群 | 需 seed |
|---|---|
| CG-* | pending_confirm entry（payload 含 final_sizing_pct/current_price/atr_14_pct）；部分需 created_at 已逾時 |
| PR-* | 各 status 的 proposal markdown（pending/validating/approved/merged/rejected）+ frontmatter |
| SW/BT/SC | 對應 bars_daily / 籌碼資料；或 mock provider |
| AU-* | 5 種 kind 的 journal 行各數筆 |
| PP-* | open positions（含 null stop_loss/t1 的邊界列）|
| ST-* | settings env（api_keys 混合 set/unset、auto_execute 兩態）|
| ME-* | memory_rows（多 kind/tag、>100 筆測分頁、content >200 字測截斷）|

> harness 已具備 `web-admin/e2e/seed_db.py` + temp DB，可擴充上述 seed。

## 附錄 B — 共用斷言模式

- **成功 envelope**：`{ ok:true, data:{...} }`；**錯誤 envelope**：`{ ok:false, error:{ code, message } }`，message 不洩漏內部細節（internal_error）。
- **紅漲綠跌 token**：`.text-up`（綠/漲）、`.text-down`（紅/跌）、`data-direction=up|down|neutral`。
- **載入三態**：loading→skeleton、error→紅卡+「重試」(refetch)、empty→EmptyState。
- **401**：清 auth token + 導向 /login（全頁一致）。
- **TopBar 標題**：`getByRole('banner').getByRole('heading',{level:1})` = `TITLE_BY_PATH[path]`。

## 附錄 C — 與既有測試的關係

- **Vitest 元件測試**（`web-admin/src/pages/__tests__/*`）：已 mock fetch 驗各頁互動 — 本規格的 [可測] 情境多數可在此層覆蓋（快、穩）。
- **Playwright E2E**（`web-admin/e2e/smoke.spec.ts`）：目前只 GATE-01/02。P0 碰錢/狀態機情境（CG-*、PR-*）建議在此層補真 backend + seeded DB 的 journey。
- [BLOCKED] 情境在功能補實作前不可跑，先作為實作驗收標準存放。
