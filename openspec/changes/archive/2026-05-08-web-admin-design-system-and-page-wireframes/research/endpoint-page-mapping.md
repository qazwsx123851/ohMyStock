# 17 頁 × endpoint × event_type 對照表

> **用途：** Task 1.1 產出，做為 task 1.2 invoke ui-ux-pro-max 的 input brief。  
> **來源：**
> - 路由：`web-admin/src/router.tsx`（18 routes：17 stubs + Dashboard real）
> - 端點：`openspec/specs/admin-read-endpoints/spec.md`（4 GET）+ `openspec/specs/server-action-endpoints/spec.md`（6 POST + 1 SSE GET）
> - Events：`openspec/specs/eventbus-emitters/spec.md` 的 16 個 canonical `event_type`

---

## 後端就緒清單（v0 已可用）

### Read endpoints
- `GET /api/admin/journal/rows`（query: `kind` / `symbol` / `date_from` / `date_to` / `limit≤500` / `offset`）
- `GET /api/admin/journal/decisions/{decision_id}`（單一 decision 完整路徑）
- `GET /api/admin/positions/open`（含 entry_price / stop_loss / t1_target / hold_days / time_stop_date）
- `GET /api/admin/stats/today`（KPI 6 計數器：decisions_made / entries_pending / entries_filled / rejects / expires / auto_execute_audits）

### Write endpoints
- `POST /api/admin/screener/run`（universe / custom_symbols / filters / asof_date）
- `GET /api/admin/confirm-gate/pending`
- `POST /api/admin/confirm-gate/confirm`、`/reject`、`/sweep-expired`
- `POST /api/admin/exit-engine/run`（asof_date / symbol filter）

### SSE
- `GET /api/admin/events`（statelessly streams all 16 event_types via `AdminEventSerializer`）

### Canonical 16 event_types
`screener_started` / `screener_completed` / `pattern_detected` / `decider_thinking` / `decision_made` / `awaiting_confirm` / `order_sent` / `journal_written` / `journal_queried` / `review_node_started` / `review_completed` / `proposal_created` / `wfa_started` / `wfa_passed` / `wfa_failed` / `risk_off_triggered`

---

## 17 頁映射表

| # | Route | Page | 後端狀態 | 主要 endpoints | 相關 SSE event_types |
|---|---|---|---|---|---|
| 1 | `/chat` | 對話入口（session list + 新增 chat） | ❌ 未做 | (future) | (future) |
| 2 | `/chat/:sessionId` | 對話流（SSE token streaming） | ❌ 未做 | (future) | `decider_thinking`, `journal_written` |
| 3 | `/swarm` | 10 個 preset 卡片入口 | ❌ 未做 | (future) | (future) |
| 4 | `/swarm/:preset/:runId` | DAG 即時視覺化 | ❌ 未做 | (future) | `review_node_started`, `review_completed` |
| 5 | `/backtest` | 策略表單 + 歷史 job 列表 | ❌ Phase 1 未做 | (future POST `/api/admin/backtest/run`) | `wfa_started` |
| 6 | `/backtest/:jobId` | 回測結果（資金曲線 / 回撤 / 交易明細） | ❌ Phase 1 未做 | (future GET `/api/admin/backtest/{id}`) | `wfa_passed`, `wfa_failed` |
| 7 | `/paper` | 模擬交易首頁（KPI + 持倉 + 快速下單） | ✅ 部分可用 | `GET stats/today` + `GET positions/open` | `awaiting_confirm`, `order_sent` |
| 8 | `/paper/orders` | 委託歷史 | ✅ 完全可用 | `GET journal/rows?kind=entry/fill/exit` | `order_sent`, `journal_written` |
| 9 | `/paper/positions` | 持倉明細 | ✅ 完全可用 | `GET positions/open` | `order_sent` |
| 10 | `/market` | 市場掃描（即時行情 + screener 觸發） | 🟡 screener 部分可用 | `POST screener/run` | `screener_started`, `screener_completed`, `pattern_detected` |
| 11 | `/market/:symbol` | 個股頁（K 線 + 籌碼 + 三大法人） | ❌ 未做 | (future) | `pattern_detected` |
| 12 | `/skills` | 30 個 skills 列表 + 啟用切換 | ❌ 未做 | (future) | (future) |
| 13 | `/skills/:name` | YAML + Markdown 編輯器 | ❌ 未做 | (future) | (future) |
| 14 | `/memory` | 長期記憶條目管理 | ❌ 未做 | (future) | (future) |
| 15 | `/sessions` | FTS5 session 搜尋 | ❌ 未做 | (future) | (future) |
| 16 | `/settings` | API key / Shioaji / FinMind / 主題 / Safety toggle | ❌ 未做 | (future) | (future) |
| 17 | `/audit` | 稽核日誌瀏覽（含下載 JSONL） | ✅ 完全可用 | `GET journal/rows` 全 kinds | `journal_written`, `risk_off_triggered` |

---

## 設計含義（給 ui-ux-pro-max 的 design brief 用）

### 立即可實作的「真頁」候選（4 頁）
- `/paper/orders`、`/paper/positions`、`/audit`：純讀，DataTable 樣板
- `/paper`：composite Dashboard-like 頁（KPI + 持倉小表 + 快速下單）

### 觸發長任務 + SSE 進度
- `/market`（screener.run + screener_completed）

### 後端未做但版型仍要設計
- 13 頁（chat / swarm / backtest / market 個股 / skills / memory / sessions / settings）
- 這些頁面的 wireframe 仍要產出版型契約 + 預期 API contract，等對應 phase 實作時遵循
- 在 SSOT 文件每頁標 「資料來源：(future) ...」或「資料來源：本頁無後端依賴」

### 共通 patterns（每頁版型契約必含）
- `loading` / `empty` / `error` / `partial` 狀態
- 訂閱 SSE 的頁面必含 `live-update` 區塊與「重連中」可見回饋
- 紅漲綠跌 token 套用範例（`--up` 紅 / `--down` 綠 + Lucide 箭頭雙重編碼）
- 鍵盤可達性（Tab / Enter / Escape；可達 row、可達 sortable header）
