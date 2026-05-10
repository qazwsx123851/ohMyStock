# web-admin 17 頁版型契約 SSOT

> **角色：** 本檔為 `web-admin/` 後台 17 個非 Dashboard 頁面（含 `/` Dashboard 已實作版型參照）的視覺、互動、狀態契約 SSOT。
> **使用者：** 後續 per-page change 的 implementor 進來，**讀完本檔該頁 section 就能寫頁**，不用再問。
> **不在本檔範圍：**
> - 後端 API contract（看 `openspec/specs/admin-read-endpoints/`、`server-action-endpoints/`、`eventbus-emitters/`）
> - SSE event_type 完整定義（看 `docs/backend-eventbus.md`）
> - Bearer auth / Mask Spec（看 `docs/auth-and-mask.md`）
> - 公網 pixel office UI（看 `docs/frontend-public-pixel.md`）
>
> 本檔列為 `CLAUDE.md` §5 「公式 / Schema 唯一權威表」一列。

---

## 0. 全域共識

### 0.1 既有 shell（`web-admin/src/components/layout.tsx`）— 不在本檔修改範圍
```
+------+--------------------------------------------------------------+
| Side | TopBar  ┃  Page Title (中)              TPE Clock · 登出     |
| bar  +--------------------------------------------------------------+
| 240  |                                                              |
| px   |   p-6 content area  (overflow-y-auto)                        |
| (56  |                                                              |
| col- |                                                              |
| laps |                                                              |
| ed)  |                                                              |
|      |                                                              |
|      +--------------------------------------------------------------+
|      | Footer · 模擬交易僅供研究 · 非投資建議 · 本系統不涉及實單委託 |
+------+--------------------------------------------------------------+
```

Sidebar 依 4 群組顯示：**工作流**（Dashboard / 對話 / Swarm / 回測）· **交易**（模擬交易 / 委託 / 持倉）· **研究**（市場 / Skills / 記憶 / 對話歷史）· **系統**（設定 / 稽核）。每頁的 ASCII wireframe **省略 Sidebar/TopBar/Footer**，只畫 content area 內部，避免重複。

### 0.2 Design tokens（既有，禁止本檔新增）
- 字體：`--font-sans` Inter + Noto Sans TC、`--font-mono` Fira Code
- 紅漲綠跌：`--up #dc2626` / `--down #059669` / `--destructive #991b1b` / `--warning #d97706`（dark 變體見 `index.css`）
- Density（本 change 新增）：`--density-row-h: 36px` / `--density-row-h-compact: 28px`
- 數值欄一律加 `.tabular`（Fira Code + `font-variant-numeric: tabular-nums`）

### 0.3 紅漲綠跌 + 雙重編碼（不可違反）
| 場景 | Color token | 配對 Lucide icon |
|---|---|---|
| 漲 / 獲利 / 多方訊號 | `--up` (red) | `ArrowUp` / `TrendingUp` |
| 跌 / 虧損 / 空方訊號 | `--down` (green) | `ArrowDown` / `TrendingDown` |
| 持平 / 中性 | `text-muted-foreground` | 無 glyph |
| 危險 / 刪除 / 拒絕 | `--destructive` | `X` / `AlertCircle` |
| 警告 / Risk-Off / Breaker | `--warning` | `AlertTriangle` / `Hourglass` |

**鐵律：** 任何時候用 color 表達語意，**必須**同時放 Lucide icon。

### 0.4 共用 composite（本 change 一併落地）
- `<DataTable>` — 分頁 / 排序 / 鍵盤 / `density` / loading / empty / error
- `<KpiCard>` — 1 KPI、`direction = up | down | neutral` 自動配色 + 箭頭
- `<StatusBadge>` — 7 種狀態 (`pending` / `approved` / `rejected` / `executed` / `expired` / `canceled` / `errored`) 各自 icon + color

未在本 change 落地、留給後續 per-page changes 自行決定的 composite：`FilterBar`、`ConfirmDialog`、`useSseStream` 通用化。

---

## 1. `/chat` — 對話入口

**用途：** Claude session 列表與「+ 新對話」入口；點 row → 進對話流。
**後端狀態：** ❌ 未做（future GET `/api/admin/chat/sessions`、POST `/api/admin/chat/sessions`）

**ASCII wireframe**
```
+--------------------------------------------------------------+
| 對話模式                              [+ 新對話 (Cmd+N)]      |
+--------------------------------------------------------------+
|  搜尋: [_______________________]   排序: ▼ 最近活動           |
+--------------------------------------------------------------+
| Session                       訊息數   最後活動    狀態        |
+--------------------------------------------------------------+
| ▶ 早盤盤前掃描討論              42      14:03    ● 進行中     |
| ▶ 2330 籌碼分析                 18      昨天     ○ 結束       |
| ▶ Backtest #128 復盤            7       2026-05  ○ 結束       |
| ▶ Memory: 法人連續買超          —       (空)     ○ 結束       |
+--------------------------------------------------------------+
|                          [< 上一頁  1 / 4  下一頁 >]          |
+--------------------------------------------------------------+
```

**Layout slots**
| Slot | 內容 | shadcn primitive | 紅漲綠跌套用？ |
|---|---|---|---|
| 頁首 action row | 「+ 新對話」`Button`（primary） | `Button` | 否 |
| 搜尋 / 排序 bar | Input + Select（local 狀態） | `Input` / `Select`（後續 page change 加） | 否 |
| Session list | `DataTable` 5 欄：Session / 訊息數 / 最後活動 / 狀態 / 動作 | `DataTable` | 否（純列表） |
| 分頁列 | `pageSize=20` 預設 | `Button` | 否 |

**資料來源**
- (future) `GET /api/admin/chat/sessions?limit=20&offset=0`
- (future) `POST /api/admin/chat/sessions` → 回 `{session_id}` 後 `navigate(/chat/<id>)`
- 訂閱 SSE event_type：不訂閱（列表頁靜態）

**互動**
- click row → `navigate(/chat/<sessionId>)`
- click `+ 新對話` 或按 Cmd/Ctrl+N → POST 建 session → 跳轉
- click 排序 header → cycle `asc → desc → unsorted`（DataTable 行為）
- 搜尋 input 變動 → 200ms debounce → 重新查列表

**State 行為**
- `loading`：DataTable 顯示 3 列 Skeleton（每列高 36px）。
- `empty`：DataTable 顯示「尚無對話 — 點右上『+ 新對話』開始」+ `MessagesSquare` muted icon。
- `error`：DataTable 換成 `Card` 含 `AlertCircle` + 訊息 +「重試」`Button`。
- `live-update`：不適用（不訂閱 SSE）。

**紅漲綠跌套用範例**
- 「狀態」欄：`進行中` 用 `text-up` + `<span className="size-2 rounded-full bg-up"/>`；`結束` 用 muted；`error` 用 `--destructive` + `<AlertCircle/>`。注意 `進行中` 用 `--up` 紅是「活躍」語意，與下方損益語意分流。

**鍵盤可達性**
- Tab：搜尋 input → 排序 select → row 1..N → 分頁按鈕 → 「+ 新對話」
- 每個 row `tabIndex=0`、Enter → 進 session
- 全域 hotkey Cmd/Ctrl+N → 觸發「+ 新對話」

---

## 2. `/chat/:sessionId` — 對話流

**用途：** 與 LLM Decider / 一般 chat 對話；訊息可包含 `tool_use` 區塊與 `journal_written` 連結。
**後端狀態：** ❌ 未做（future GET `/api/admin/chat/sessions/:id/messages` + SSE token streaming endpoint）

**ASCII wireframe**
```
+--------------------------------------------------------------+
| ← 返回   早盤盤前掃描討論              [⋮ 重命名 / 刪除]      |
+--------------------------------------------------------------+
|                                                              |
|  [User · 09:15]                                               |
|  > 今天 universe 有什麼 SEPA 訊號？                           |
|                                                              |
|  [Assistant · Sonnet 4.6 · 09:15]                             |
|  我跑 screener_run 看看。                                     |
|  ┌─────────────────────────────────────────────┐              |
|  │ ⚙ tool_use: screener_run                    │              |
|  │   universe=tw50, filters={sepa: true}       │              |
|  │   → 3 hits: 2330, 2454, 6505               │              |
|  └─────────────────────────────────────────────┘              |
|  其中 2330 (台積電) 今日 ▲+1.2%，符合 RS≥80。                  |
|                                                              |
|  [Assistant streaming...] ▮                                   |
+--------------------------------------------------------------+
|  [_______________________________________]  [送出 (Cmd+↩)]    |
+--------------------------------------------------------------+
```

**Layout slots**
| Slot | 內容 | shadcn primitive | 紅漲綠跌套用？ |
|---|---|---|---|
| 頁首 | 返回鈕 + session 標題 + ⋮ 動作選單 | `Button` | 否 |
| 訊息流 | virtualized scroll list；user / assistant / tool_use 三 variant `Card` | `Card` | 是（價格訊號用 --up/--down 雙重編碼） |
| Streaming indicator | 閃爍 caret `▮` + 部分 token | 自製 | 否 |
| 輸入區 | multi-line `Textarea` + 送出 `Button` | `Textarea` / `Button` | 否 |

**資料來源**
- (future) `GET /api/admin/chat/sessions/:id/messages`（初次載入歷史）
- (future) SSE on `POST /api/admin/chat/sessions/:id/messages` → token stream
- 訂閱 SSE event_type：`decider_thinking`（assistant 區塊頂部 inline 進度）、`journal_written`（assistant 訊息附帶 trade journal 連結）

**互動**
- 輸入 + Cmd/Ctrl+Enter → 送出；按 ↩ 換行
- click `tool_use` block → 展開 / 收合 `args` + `result`
- click `journal_written` chip → `navigate(/audit?decision_id=...)`
- click ← 返回 → `navigate(/chat)`
- ⋮ 選單：重命名（inline 編輯）、刪除（confirm dialog → DELETE → navigate）

**State 行為**
- `loading`：訊息流 3 個訊息 Skeleton（依序 user 短 / assistant 長 / user 短）；輸入區 disabled。
- `empty`：「這是新對話」+ `<MessagesSquare/>` muted；輸入區 active 等使用者第一句。
- `error`：訊息流頂部紅色 banner「載入歷史訊息失敗」+ 重試；streaming 中斷顯示 inline `<AlertTriangle/>` + 「網路中斷，已保留你輸入的內容」。
- `live-update`：streaming 中 assistant 訊息底部 caret 持續閃；新 token 從訊息流底插入。
- `reconnect`：頁面頂部出現 `Card` warning 條「重新連線中…（嘗試 1/2/4/8/30s）」，連上後自動消失，未送達訊息會自動補。

**紅漲綠跌套用範例**
- assistant 訊息內若提到價格變動（如 `▲+1.2%`），text 用 `--up` + 前置 `<TrendingUp className="inline size-3.5"/>`；下跌用 `--down` + `<TrendingDown/>`。

**鍵盤可達性**
- Tab：返回 → ⋮ → 訊息流（focusable region）→ 輸入區 → 送出
- Cmd/Ctrl+Enter 送出、↩ 換行、Esc 取消重命名 inline 編輯
- ⋮ 動作選單為 Popover：Esc 關閉、↑↓ 切項

---

## 3. `/swarm` — Swarm Preset 入口

**用途：** 10 個 swarm preset 卡片（如 entry_decision_team、post_trade_review、proposal_generator）；click 一張 → 帶參數頁，跑完跳到 run 詳情。
**後端狀態：** ❌ 未做（future GET `/api/admin/swarm/presets` + POST `/api/admin/swarm/runs`）

**ASCII wireframe**
```
+--------------------------------------------------------------+
| Swarm                                                         |
| 10 個預設多代理工作流。選一個 preset 開始。                    |
+--------------------------------------------------------------+
|  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐ |
|  │ entry_decision_  │  │ post_trade_      │  │ proposal_    │ |
|  │ team             │  │ review           │  │ generator    │ |
|  │                  │  │                  │  │              │ |
|  │ 5 角色辯論單筆   │  │ 月度復盤 5 節點  │  │ 從復盤產     │ |
|  │ 進場決策         │  │ DAG              │  │ 生策略提案   │ |
|  │                  │  │                  │  │              │ |
|  │ ⏱ 預估 30s · 5✦ │  │ ⏱ 預估 2m · 5✦  │  │ ⏱ 1m · 3✦   │ |
|  │            [跑 →]│  │            [跑 →]│  │      [跑 →] │ |
|  └──────────────────┘  └──────────────────┘  └──────────────┘ |
|  ...（共 10 卡，3 col 網格，scroll）                          |
+--------------------------------------------------------------+
| 最近執行                                                      |
+--------------------------------------------------------------+
| Preset             RunId  狀態      開始       時長            |
| entry_decision_te  r#129  ● 進行中  14:03      45s            |
| post_trade_review  r#128  ✓ 完成    昨天 22:00 1m48s          |
| proposal_generator r#127  ✗ 失敗    2026-05-05 12s            |
+--------------------------------------------------------------+
```

**Layout slots**
| Slot | 內容 | shadcn primitive | 紅漲綠跌套用？ |
|---|---|---|---|
| 頁首說明 | 標題 + 1 行 subtitle | — | 否 |
| Preset grid | 10 張 `Card`，3 col；每卡顯示 name / 描述 / 預估時長 / 預估 LLM cost / 「跑 →」 | `Card` / `Button` | 否 |
| 最近執行表 | `DataTable` 5 欄；row click → `/swarm/<preset>/<runId>` | `DataTable` / `StatusBadge` | 否 |

**資料來源**
- (future) `GET /api/admin/swarm/presets`（10 筆 preset 描述）
- (future) `GET /api/admin/swarm/runs?limit=20`
- (future) `POST /api/admin/swarm/runs { preset, args }` → 回 `{run_id}` → `navigate(/swarm/<preset>/<run_id>)`
- 訂閱 SSE event_type：不訂閱（列表頁；run 詳情頁訂）

**互動**
- click 卡片任一處 → 開啟 args sheet（`Sheet` primitive 留 future）填參數，按「跑 →」POST
- click 「最近執行」row → 跳 run 詳情
- 鍵盤：卡片整張 `tabIndex=0`，Enter 等同 click

**State 行為**
- `loading`：grid 顯示 6 張 Skeleton 卡，list 顯示 3 列 Skeleton。
- `empty`：preset grid 不會空（presets 是 hardcoded fallback OK）；最近執行 list empty 顯示 `Card`「尚無執行紀錄」+ `<Network/>`。
- `error`：preset grid 載入失敗 → 顯示靜態 fallback grid + 紅色 banner「無法取得 preset metadata，使用本地 fallback」；list 失敗顯示 retry。
- `live-update`：不適用。

**紅漲綠跌套用範例**
- 最近執行表「狀態」欄一律走 `<StatusBadge>` 7 種狀態的固定色板（不引用 --up/--down）：`pending` 用 muted + Hourglass、`completed` 用 success token (`--up` 子色) + Check、`failed` 用 `--destructive` + X。`StatusBadge` 與漲跌語意分流，避免「成功」與「漲」用同色造成混淆。

**鍵盤可達性**
- Tab：preset 卡 1..10 → 「最近執行」row 1..N
- Enter → 等同 click（卡片 → args sheet；row → run 詳情）

---

## 4. `/swarm/:preset/:runId` — Swarm DAG 即時視覺化

**用途：** 一個 swarm run 的節點 DAG 即時跑完狀態 → 點節點看 input/output。
**後端狀態：** ❌ 未做（future GET `/api/admin/swarm/runs/:id` + SSE for `review_node_started` / `review_completed`）

**ASCII wireframe**
```
+--------------------------------------------------------------+
| ← Swarm   post_trade_review · run #128                        |
| ◐ 進行中 · 已跑 1m23s · 已完成 3 / 5 節點                     |
+--------------------------------------------------------------+
|                                                              |
|   ┌───────────┐      ┌───────────┐      ┌───────────┐         |
|   │ data      │ ───▶ │ attribu-  │ ───▶ │ aggrega-  │         |
|   │ ✓ 完成    │      │ tion      │      │ tor       │         |
|   │ 12s       │      │ ✓ 完成    │      │ ◐ 進行中  │         |
|   └───────────┘      │ 28s       │      │ 8s ...    │         |
|                      └───────────┘      └───────────┘         |
|                                                ▼              |
|                                         ┌───────────┐         |
|                                         │ critic    │         |
|                                         │ ○ 待執行  │         |
|                                         └───────────┘         |
|                                                ▼              |
|                                         ┌───────────┐         |
|                                         │ proposer  │         |
|                                         │ ○ 待執行  │         |
|                                         └───────────┘         |
+--------------------------------------------------------------+
|  選定節點: aggregator                                          |
|  ─────────────────────────────────────────────────            |
|  Input:  { wins: [...], losses: [...], by_pattern: {...} }   |
|  Output: streaming...                                         |
+--------------------------------------------------------------+
```

**Layout slots**
| Slot | 內容 | shadcn primitive | 紅漲綠跌套用？ |
|---|---|---|---|
| 頁首 | 返回 + preset 名 + run id + run 狀態 + 進度（done/total） | `StatusBadge` | 否 |
| DAG canvas | SVG 繪節點 + 連線；節點 = `Card` thumbnail（本 change 不引入圖庫） | 自製 | 是（節點狀態邊框） |
| 節點詳情面板 | 下半 `Card` 顯 input/output JSON（用 `<pre className="font-mono">`） | `Card` | 否 |

**資料來源**
- (future) `GET /api/admin/swarm/runs/:id`（節點圖 + 狀態快照）
- 訂閱 SSE event_type：`review_node_started`（節點變 `pending → running`）、`review_completed`（變 `running → done`，附 output）

**互動**
- click 節點 → 下方詳情面板切換為該節點 input/output
- 完成節點顯示「展開全部 output」`Button`
- 連線箭頭 hover → tooltip「資料依賴：data → attribution」（tooltip primitive 留 future）

**State 行為**
- `loading`（首次載入 run snapshot）：DAG 區 Skeleton 5 個節點輪廓；詳情面板 Skeleton。
- `empty`：不適用（run 必有節點圖；如 run id 不存在走 `error`）。
- `error`：「找不到 run #128」+「返回列表」`Button`；run 中斷顯示 `<AlertCircle className="text-destructive"/>` + reason。
- `live-update`：節點狀態切換時，舊 `Card` 邊框 250ms ease 由 `border-muted` → `border-warning` (running) → `border-up` (done)；新 SSE 來時節點輕微 ping。`已完成 N / M` 同步更新。
- `reconnect`：頁頂 `Card` warning「重新連線中…」；連上後 issue `GET runs/:id` 補狀態，UI 對齊。

**紅漲綠跌套用範例**
- 節點 `done` 邊框用 `border-up` (`--up`) + `<Check className="text-up"/>` 角標 — 表示「成功完成」語意（與 swarm 列表頁 StatusBadge `completed` 子色一致）。`failed` 用 `--destructive` + `<X/>`；`running` 用 `--warning` + `<Hourglass className="animate-spin"/>`。

**鍵盤可達性**
- Tab：返回 → 節點 1..N → 詳情面板 scroll region
- Enter on 節點 → 切換選定 + scroll 詳情面板入畫
- ↑↓ 在節點區可移動選取（拓樸序）

---

## 5. `/backtest` — 回測表單 + 歷史 job

**用途：** 填策略 + 期間 + universe 跑回測；下方歷史 job 表。
**後端狀態：** ❌（future POST `/api/admin/backtest/run`、GET `/api/admin/backtest/jobs`）

**ASCII wireframe**
```
+--------------------------------------------------------------+
| 回測                                                          |
+--------------------------------------------------------------+
|  策略：[ SEPA ▼ ]    期間：[2024-01-01] ~ [2024-12-31]        |
|  Universe：[ tw50 ▼ ]   初始資金：[ 1,000,000 ] TWD            |
|  進階參數：[展開 ▼]                                            |
|                                                               |
|                                          [清空]  [跑回測 →]   |
+--------------------------------------------------------------+
| 歷史 job                                                      |
+--------------------------------------------------------------+
| JobId  策略  期間             年化  Sharpe MaxDD  狀態        |
+--------------------------------------------------------------+
| j#88   SEPA  2024 Q1-Q4       18.2% 1.42  -8.3%  ✓ 完成       |
| j#87   ATR   2023-2024        7.1%  0.72  -14%   ✓ 完成       |
| j#86   SEPA  2022-2024        ◐ 進行中 (estimated 2m)         |
| j#85   ATR   2024 Q1-Q2       —     —     —      ✗ 失敗       |
+--------------------------------------------------------------+
```

**Layout slots**
| Slot | 內容 | shadcn primitive | 紅漲綠跌套用？ |
|---|---|---|---|
| 表單區 | 策略 / 期間 / universe / 資金 + 進階展開 | `Select` / `DatePicker` / `Input` | 否 |
| Action row | 清空 + 跑回測（primary） | `Button` | 否 |
| 歷史 job 表 | `DataTable` 8 欄；row click → `/backtest/<jobId>` | `DataTable` / `StatusBadge` | 是（年化 / Sharpe / MaxDD） |

**資料來源**
- (future) `POST /api/admin/backtest/run` → 回 `{job_id}` → 留在頁但 list 自動 refresh
- (future) `GET /api/admin/backtest/jobs?limit=20`
- 訂閱 SSE event_type：`wfa_started`（list row 切「進行中」）、`wfa_passed` / `wfa_failed`（更新狀態 + 數字）

**互動**
- 跑回測：disabled 直到必填齊；submit 後 `Button` `<Loader2 animate-spin/>` + 「啟動中…」；成功後 toast / banner（toast primitive 留 future）
- click row → 跳 `/backtest/<jobId>`
- click 「進階參數 ▼」→ inline 展開更多欄位（停損 / TP / sizing 模型）

**State 行為**
- `loading`：歷史 job 表 5 列 Skeleton。
- `empty`：「尚未跑過回測」+ `<FlaskConical/>` muted + 提示「填上方表單後點『跑回測 →』」。
- `error`：表單提交失敗 → 表單下方紅色 banner「啟動失敗：{reason}」+「重試」；list 失敗 → `Card` retry。
- `live-update`：新 SSE event 進來 → 對應 row inline flash（背景 `bg-warning/10` 1s fade-out）。

**紅漲綠跌套用範例**
- 「年化」欄：>0 用 `text-up` + `<ArrowUp className="inline size-3.5"/>`；<0 用 `text-down` + `<ArrowDown/>`；0 用 muted。
- 「MaxDD」欄：永遠 ≤0，數字本身用 `text-down` + `<ArrowDown/>`，搭配 `<TrendingDown/>` 表示「跌幅」更直覺。
- 「Sharpe」欄：>1 用 `text-up`；0~1 muted；<0 用 `text-down`。

**鍵盤可達性**
- Tab：策略 → 期間 from → to → universe → 資金 → 進階 toggle → 清空 → 跑回測 → row 1..N
- Enter on row → 跳 detail
- Cmd/Ctrl+Enter 在表單焦點任一欄位 → 觸發跑回測

---

## 6. `/backtest/:jobId` — 回測結果

**用途：** 單一 job 的資金曲線 / 回撤 / 交易明細 / 統計摘要。
**後端狀態：** ❌（future GET `/api/admin/backtest/jobs/:id`）

**ASCII wireframe**
```
+--------------------------------------------------------------+
| ← 回測  Job #88 · SEPA · 2024-01-01 ~ 2024-12-31              |
+--------------------------------------------------------------+
|  KPI Row                                                      |
|  +----------+ +----------+ +----------+ +----------+          |
|  | 年化     | | Sharpe   | | MaxDD    | | 勝率     |          |
|  | ▲ 18.2%  | | 1.42     | | ▼ -8.3%  | | 54.2%    |          |
|  +----------+ +----------+ +----------+ +----------+          |
+--------------------------------------------------------------+
|  資金曲線                            [圖庫待定 — 暫 placeholder]|
|  ┌──────────────────────────────────────────────────────────┐ |
|  │ [equity curve placeholder — chart lib TBD]               │ |
|  └──────────────────────────────────────────────────────────┘ |
|                                                              |
|  回撤曲線                                                    |
|  ┌──────────────────────────────────────────────────────────┐ |
|  │ [drawdown curve placeholder]                             │ |
|  └──────────────────────────────────────────────────────────┘ |
+--------------------------------------------------------------+
|  交易明細  (DataTable)                                        |
| 進場日 出場日   Symbol  方向  P&L      持倉  Pattern           |
| 01-15  01-22   2330    多    ▲+12,300  7d    SEPA breakout   |
| 02-03  02-04   2454    多    ▼-3,400   1d    failed entry    |
| ...                                                           |
+--------------------------------------------------------------+
```

**Layout slots**
| Slot | 內容 | shadcn primitive | 紅漲綠跌套用？ |
|---|---|---|---|
| 頁首 | 返回 + jobId + 策略 + 期間 | — | 否 |
| KPI Row | 4 張 `<KpiCard>`：年化 / Sharpe / MaxDD / 勝率 | `KpiCard` | 是 |
| 資金曲線 | placeholder 區（含「[chart lib TBD per future change]」標籤） | `Card` wrapper | 否 |
| 回撤曲線 | 同上 | `Card` | 否 |
| 交易明細 | `DataTable` 7 欄；P&L 欄套色 | `DataTable` | 是 |

**資料來源**
- (future) `GET /api/admin/backtest/jobs/:id`（含 KPI、equity series、drawdown series、trades 列表）
- 訂閱 SSE event_type：若仍進行中訂 `wfa_passed` / `wfa_failed` → 完成後刷新；完成後不訂閱

**互動**
- click 交易明細 row → 展開該筆 inline detail 或 drawer（drawer primitive 留 future，本 change 用 inline expand row 即可）
- 「下載 trades CSV」`Button`（次要）→ 觸發 blob download

**State 行為**
- `loading`：KPI Row 4 張 KpiCard `loading` skeleton；圖區顯灰 `Skeleton` 整塊；明細 5 列 Skeleton。
- `empty`：job 無交易 → 明細 DataTable 顯「本 job 區間無交易訊號」。
- `error`：「載入 job #88 失敗 — {reason}」+ 重試 +「返回列表」。
- `live-update`：若 job 仍 `pending`，KPI Row 顯示 `loading=true`，圖區顯示「執行中…」+ Hourglass；完成事件到後刷新一次。

**紅漲綠跌套用範例**
- KpiCard 年化：>0 → `direction="up"` 自動 `--up` + `<ArrowUp/>`；<0 → `direction="down"` + `<ArrowDown/>`。
- KpiCard MaxDD：固定 `direction="down"`（語意上是「跌幅」）+ `<ArrowDown/>`，數字 `text-down`。
- KpiCard Sharpe：>1 up；<0 down；0~1 neutral。
- DataTable「P&L」欄：>0 紅 + `<ArrowUp/>`；<0 綠 + `<ArrowDown/>`。

**鍵盤可達性**
- Tab：返回 → KPI 4 張（focusable region，不交互）→ 圖區（不交互）→ DataTable rows → 「下載 CSV」
- Enter on row → 展開 inline detail；再 Enter / Esc 收合

---

## 7. `/paper` — 模擬交易首頁

**用途：** 全局狀態看板（KPI + 開倉摘要 + 待確認 + 快速下單）。是 Mark 每日早盤第一站。
**後端狀態：** ✅ 部分（`GET /api/admin/stats/today` + `GET /api/admin/positions/open`，後端就緒；快速下單 endpoint future）

**ASCII wireframe**
```
+--------------------------------------------------------------+
|  KPI Row                                                      |
|  +-----------+ +-----------+ +-----------+ +-----------+      |
|  | 今日損益  | | 開倉數    | | 待確認    | | 今日 LLM  |      |
|  | ▲ +12,345 | | 4         | | 2         | | $0.83     |      |
|  +-----------+ +-----------+ +-----------+ +-----------+      |
+--------------------------------------------------------------+
|  待確認進場 (2)                  [全部 sweep 過期 (Cmd+Shift+E)]|
|  +----------------------------------------------------------+ |
|  | ● 2330 多 200 股 @ 1,025  · 信心 0.78  · 倒數 4m12s ▮▮▮  | |
|  |   [✓ 確認 (Y)]   [✗ 拒絕 (N)]   [⋮ 看完整推理]           | |
|  +----------------------------------------------------------+ |
|  | ● 2454 多 100 股 @ 1,180  · 信心 0.82  · 倒數 9m05s ▮▮▮▮▮▮ |
|  |   [✓ 確認]   [✗ 拒絕]                                     | |
|  +----------------------------------------------------------+ |
+--------------------------------------------------------------+
|  開倉中 (4)             [→ 詳細看 /paper/positions]            |
| Symbol  方向  Qty   Entry   現價   未實現P&L  停損    剩餘日   |
| 2330   多    100  1,000.5  1,025  ▲ +2,450   970     12d/14d  |
| 6505   多    500    33.5     32.8 ▼ -350     31      8d/14d   |
| ...                                                           |
+--------------------------------------------------------------+
|  Live Feed (latest 8)                  [清空] [全部展開 ▼]    |
| 14:03 ✓ confirm_gate.confirmed  2454 entry confirmed          |
| 14:01 ◐ decider_thinking        2454 PM 評估中…                |
| ...                                                           |
+--------------------------------------------------------------+
```

**Layout slots**
| Slot | 內容 | shadcn primitive | 紅漲綠跌套用？ |
|---|---|---|---|
| KPI Row | 4 張 `<KpiCard>` (今日 P&L / 開倉 / 待確認 / 今日 cost) | `KpiCard` | 是（今日 P&L direction by sign） |
| 待確認列表 | 0~N 張 `<Card>`，每張含 symbol / qty / price / 信心 / 倒數 progressbar / 確認/拒絕/詳情按鈕 | `Card` / `Button` / `StatusBadge` | 是（多空訊號） |
| 開倉摘要 | mini DataTable 6 欄（精簡，只看 top 5；右上「→ 完整版」） | `DataTable` | 是（未實現 P&L） |
| Live Feed | 滾動 timeline（8 列）；每列 timestamp + StatusBadge + 描述 | `Card` + 自製列 | 否（status badge 自有色） |

**資料來源**
- `GET /api/admin/stats/today` → KPI Row（包 `realized_pnl_twd` / `open_positions` / `pending_confirms` / `today_llm_cost_usd` 等）
- `GET /api/admin/positions/open` → 開倉摘要
- `GET /api/admin/confirm-gate/pending` → 待確認列表
- 訂閱 SSE event_type：`awaiting_confirm`、`order_sent`、`decision_made`、`journal_written`、`risk_off_triggered`

**互動**
- click 待確認卡「✓ 確認」/ 鍵盤 `Y` (focused 卡片) → POST `/confirm-gate/confirm` → 樂觀 UI（卡片立刻 fade out + StatusBadge 切 `executed`）
- 「✗ 拒絕」/ `N` → POST `/reject` → fade out
- 「⋮ 看完整推理」→ 開 drawer（drawer primitive future），暫用 `navigate(/audit?decision_id=<id>)` fallback
- 「全部 sweep 過期」按鈕 → confirm dialog → POST `/sweep-expired`（confirm dialog primitive future，本 change 暫用 `window.confirm`）
- click 開倉摘要 row → `navigate(/paper/positions?symbol=<...>)` 高亮
- Live Feed 「清空」→ 本地清空（不打後端）

**State 行為**
- `loading`：KPI Row 全 `loading`；待確認 / 開倉 / Live feed 各自 3 列 Skeleton。
- `empty`：待確認區 → `Card`「目前無待確認」+ `<Check className="text-muted"/>`；開倉 →「目前無開倉」+ `<Briefcase muted/>`；Live feed →「等待事件…」+ blinking dot。
- `error`：每個區塊獨立 `Card` retry；KPI Row 任一卡 fail 顯灰底 + `<AlertCircle/>` 對齊既有 Dashboard 行為。
- `live-update`：SSE 推 `awaiting_confirm` → 待確認區頂部插入新卡 + 倒數 picker 啟動；`order_sent` → 對應卡 fade out；KPI Row 對應數字直接更新；Live Feed 頂部插入新列 + 0.5s 黃底 flash。
- `reconnect`：頁頂 `Card` warning「重新連線中…（嘗試 N/5）」對齊 `useAdminEvents` backoff；連上後一次性 GET stats/today + GET positions/open + GET confirm-gate/pending 補齊。

**紅漲綠跌套用範例**
- KpiCard `今日損益`：sign 自動推 direction (`>0 → up`, `<0 → down`, `===0 → neutral`)；up 用 `text-up` + `<ArrowUp/>`；down 用 `text-down` + `<ArrowDown/>`。
- 待確認卡「方向」：多用 `text-up` + `<ArrowUp/>`；空用 `text-down` + `<ArrowDown/>`。
- 開倉摘要「未實現 P&L」：>0 紅 + `<ArrowUp/>`；<0 綠 + `<ArrowDown/>`。
- 「停損」欄不套色（純技術價）。

**鍵盤可達性**
- Tab：KPI Row（focusable for screen readers, not interactive）→ 待確認卡 1..N → 開倉 row → Live Feed
- 待確認卡 focused 後：`Y` → 確認、`N` → 拒絕（單字 hotkey 全域 listener，需 input 不在 focus 才生效）
- Cmd/Ctrl+Shift+E → 全部 sweep 過期（先 confirm dialog）
- Esc on confirm dialog → 取消

---

## 8. `/paper/orders` — 委託歷史

**用途：** journal 全部 entry / fill / exit / reject 紀錄；可分頁、過濾、看單張單明細。
**後端狀態：** ✅（`GET /api/admin/journal/rows?kind=entry|fill|exit&limit&offset&symbol&date_from&date_to`）

**ASCII wireframe**
```
+--------------------------------------------------------------+
|  Filter bar                                                   |
|  Kind: [ ☑entry ☑fill ☑exit ☑reject ]  Symbol: [____]         |
|  日期: [2026-04-01] ~ [2026-05-08]                            |
|                                          [套用] [清空] [匯出 CSV]|
+--------------------------------------------------------------+
| 時間            Kind   Symbol  方向  Qty   Price   狀態         |
+--------------------------------------------------------------+
| 14:03:12       fill   2454    多   100   1,180   ✓ executed   |
| 14:03:08       entry  2454    多   100   1,180   ✓ executed   |
| 13:58:01       reject 6505    多   500     33.6  ✗ rejected   |
| ...                                                           |
+--------------------------------------------------------------+
|              第 1 / 12 頁  [< 上一頁]  [下一頁 >]              |
+--------------------------------------------------------------+
```

**Layout slots**
| Slot | 內容 | shadcn primitive | 紅漲綠跌套用？ |
|---|---|---|---|
| Filter bar | kind multi-checkbox / symbol input / date range / 套用 / 清空 / 匯出 | `Checkbox` / `Input` / `Button` | 否 |
| Orders DataTable | 7 欄；row click → drawer 展示單張完整 decision_id chain | `DataTable` / `StatusBadge` | 是（方向） |
| Pagination | DataTable 內建 | `Button` | 否 |
| Detail drawer (per-page change 加) | 顯示對應 decision_id + 全 journal kinds | future | — |

**資料來源**
- `GET /api/admin/journal/rows?kind=entry&kind=fill&kind=exit&kind=reject&...`
- `GET /api/admin/journal/decisions/{decision_id}`（drawer 用，per-page change 加）
- 訂閱 SSE event_type：`order_sent`、`journal_written`（新列即時 prepend；若使用者在 page 1 才插）

**互動**
- 改 filter → 「套用」按鈕變 primary；「清空」回預設
- click row → 展開 inline 顯示 decision chain（暫，drawer 留 future page change）
- 「匯出 CSV」→ blob download 當前 filter 結果
- 排序 click：`時間` 欄預設 desc，可切 asc

**State 行為**
- `loading`：DataTable 顯 10 列 Skeleton。
- `empty`：「此 filter 無紀錄」+ `<ReceiptText muted/>` +「清空 filter」按鈕。
- `error`：「載入 journal 失敗 — {reason}」+ retry。
- `live-update`：`journal_written` 推來：若使用者在 page 1 + 無 filter 阻擋 → 第一列 prepend + 0.5s 黃底 flash；若在其他 page，頁頂顯示 toast「有 N 筆新紀錄，回 page 1 查看」。

**紅漲綠跌套用範例**
- 「方向」欄：多 `text-up` + `<ArrowUp/>`；空 `text-down` + `<ArrowDown/>`；reject 不套色（reject 顯示在「狀態」欄為 `--destructive` 的 StatusBadge）。
- 「狀態」欄全用 `<StatusBadge>` 7 種狀態。

**鍵盤可達性**
- Tab：filter 欄位 → 套用 → 清空 → 匯出 → row 1..N → 分頁
- Enter on row → 展開 detail；再 Enter / Esc 收合
- 排序 header：Tab 可達，Enter 切換 sort，`aria-sort` 同步

---

## 9. `/paper/positions` — 持倉明細

**用途：** 所有開倉部位的詳細欄位（含風險指標 stop_loss、t1_target、time_stop_date）。
**後端狀態：** ✅（`GET /api/admin/positions/open`）

**ASCII wireframe**
```
+--------------------------------------------------------------+
|  Filter: Symbol [____]  狀態 [ ☑開倉 ☐已平倉 ]                |
+--------------------------------------------------------------+
| Symbol 方向 Qty  Entry   現價    未實現 P&L  停損   T1     持倉 |
+--------------------------------------------------------------+
| 2330   多  100  1,000.5  1,025   ▲+2,450 +2.5% 970   1,080  12d|
| 6505   多  500    33.5     32.8  ▼-350   -2.1% 31      35.5 8d |
| 2454   多  100  1,180.0  1,195   ▲+1,500 +1.3% 1,150 1,250  3d |
| 1101   多 1000     45.2     45.2 — 0     0%   43.5   48     1d |
+--------------------------------------------------------------+
|  選定列：2330                                                  |
|  進場時間：2026-04-22 09:30   進場理由：SEPA breakout + RS≥80   |
|  停損距離：-5.4%   T1 距離：+5.4%   Time stop：2026-05-20      |
+--------------------------------------------------------------+
```

**Layout slots**
| Slot | 內容 | shadcn primitive | 紅漲綠跌套用？ |
|---|---|---|---|
| Filter bar | Symbol input + 狀態 checkbox | `Input` / `Checkbox` | 否 |
| Positions DataTable | 10 欄；row click → 下方 detail panel | `DataTable` | 是（方向 / 未實現 P&L） |
| Detail panel | 選定列的擴充欄位（進場理由 / time_stop / hold_days 視覺化） | `Card` | 否 |

**資料來源**
- `GET /api/admin/positions/open`（含 `entry_price` / `stop_loss` / `t1_target` / `hold_days` / `time_stop_date`）
- 訂閱 SSE event_type：`order_sent`（新進場 / 平倉 → 列即時 add/remove）

**互動**
- click row → 下方 detail panel 切換；箭頭 ↑↓ 也可
- 排序：`未實現 P&L` 欄 sortable（預設 desc）
- Filter `已平倉` → 切到 `GET /api/admin/journal/rows?kind=exit`（per-page change 時改 endpoint）

**State 行為**
- `loading`：5 列 Skeleton + detail panel Skeleton。
- `empty`：「目前無開倉」+ `<ListOrdered muted/>` + 1 行說明。
- `error`：retry 卡。
- `live-update`：`order_sent` 推來：新進場 → prepend + 黃底 flash；平倉 → 該 row fade out + 移到 detail panel 顯示「已平倉於 14:03，實現 P&L ▲+2,450」。

**紅漲綠跌套用範例**
- 「方向」欄：多 `--up` + `<ArrowUp/>`；空 `--down` + `<ArrowDown/>`。
- 「未實現 P&L」欄：>0 `text-up` + `<ArrowUp className="size-3.5"/>`；<0 `text-down` + `<ArrowDown/>`；持平 muted + `—`。
- 「停損」「T1」「Time stop」欄不套色（純技術價）。
- detail panel「停損距離」「T1 距離」百分比同套：>0 紅 / <0 綠 / =0 muted。

**鍵盤可達性**
- Tab：filter → row 1..N → detail panel
- ↑↓ on row → 切換選定 row
- Enter on row → 同 click（其實 ↑↓ 已涵蓋；保留 Enter 為 redundant 安全網）

---

## 10. `/market` — 市場掃描

**用途：** 觸發 screener.run（universe + filters）、看 result 列表。
**後端狀態：** 🟡 部分（`POST /api/admin/screener/run`）

**ASCII wireframe**
```
+--------------------------------------------------------------+
|  Universe: [ tw50 ▼ ]   Custom symbols: [____ + add chip]      |
|  Filters:                                                     |
|    [☑ SEPA]  [☑ RS ≥ 80]  [☐ 法人連續買超]  [☐ 三角收斂]    |
|  As-of date: [ 2026-05-08 ]                                  |
|                                  [跑 screener (Cmd+Enter) →] |
+--------------------------------------------------------------+
|  上次執行: r#48 · 14:02 · 共 3 命中 · 耗時 1.8s               |
+--------------------------------------------------------------+
| Symbol 名稱      現價     漲跌    Pattern             Score    |
+--------------------------------------------------------------+
| 2330   台積電    1,025   ▲+1.2%  SEPA breakout       0.86     |
| 2454   聯發科    1,180   ▲+0.8%  SEPA + RS=92        0.82     |
| 6505   台塑化       33.5 ▼-0.3%  failed entry        0.41     |
+--------------------------------------------------------------+
|  Live event feed: pattern_detected events (latest 5)          |
| 14:02:51 pattern_detected  2454 SEPA + RS=92 score=0.82      |
| 14:02:50 pattern_detected  2330 SEPA breakout    score=0.86  |
| 14:02:48 screener_started  universe=tw50 size=50             |
+--------------------------------------------------------------+
```

**Layout slots**
| Slot | 內容 | shadcn primitive | 紅漲綠跌套用？ |
|---|---|---|---|
| Filter form | universe / custom_symbols (chip input) / filters checkboxes / asof date | `Input` / `Checkbox` / `DatePicker` | 否 |
| Action row | 跑 screener primary | `Button` | 否 |
| Last run summary | 1 行：`r#48 · 14:02 · 共 3 命中 · 1.8s` | `Card` 緩衝 | 否 |
| Result DataTable | 6 欄；row click → `/market/<symbol>`；score sortable desc | `DataTable` | 是（漲跌 / pattern 方向） |
| Live feed | 5 列 timeline（screener_started / completed / pattern_detected） | 自製 + `StatusBadge` | 否 |

**資料來源**
- `POST /api/admin/screener/run` → `{run_id, hits[]}`
- 訂閱 SSE event_type：`screener_started`、`screener_completed`（更新「上次執行」）、`pattern_detected`（result 表 + live feed 即時插）

**互動**
- 「跑 screener」/ Cmd+Enter → 樂觀 UI：按鈕 disabled + spinner，「上次執行」更新為「啟動中…」；result 表清空 + Skeleton；Live feed 立刻插「screener_started」
- click result row → `navigate(/market/<symbol>)`
- chip input：輸入 symbol 按 Enter 或 `,` 加入 chip；Backspace 在空輸入區刪最後 chip
- score header click → 三循環排序

**State 行為**
- `loading`（首次或執行中）：result 表 5 列 Skeleton +「上次執行」顯示「啟動中…」+ Hourglass。
- `empty`：「本次掃描無命中」+ `<LineChart muted/>` + 提示「試試放寬 filter」。
- `error`：表單下方紅 banner「screener.run 失敗 — {reason}」+「重試」；保留 form 值不清空。
- `live-update`：`pattern_detected` 推來 → result 表 prepend row + 0.5s 黃底 flash；live feed prepend；`screener_completed` 推來 →「上次執行」更新終值。
- `reconnect`：頁頂 warning banner；連上後若有 in-flight run，UI 從 SSE 自然補上。

**紅漲綠跌套用範例**
- 「漲跌」欄：>0 `text-up` + `<ArrowUp/>`；<0 `text-down` + `<ArrowDown/>`；持平 muted + `—`。
- 「Pattern」欄：`SEPA breakout` 用 `<TrendingUp className="text-up"/>` + 文字；`failed entry` 用 `<TrendingDown className="text-down"/>`；中性 pattern 不套色。
- 「Score」欄不套色（純數值，>0.7 加粗 font-medium 但不上色 — 避免與 P&L 混淆）。

**鍵盤可達性**
- Tab：universe → custom symbols → filter checkboxes 1..N → asof date → 跑 screener → result row → live feed
- Cmd/Ctrl+Enter 全頁 hotkey → 跑 screener
- Enter on row → 進個股頁
- chip input：Enter 加、Backspace 刪

---

## 11. `/market/:symbol` — 個股頁

**用途：** 單檔 K 線 + 籌碼 SEPA / RS / 分點 + 三大法人 + 近期偵測 pattern。
**後端狀態：** ❌（future GET `/api/admin/market/symbols/:symbol`）

**ASCII wireframe**
```
+--------------------------------------------------------------+
| ← /market   2330 台積電                                       |
| 現價 1,025  ▲+1.2% (+12)  · 量 18,432K · 振幅 0.9%             |
+--------------------------------------------------------------+
|  K 線圖（日 / 週 切換）                                        |
|  ┌──────────────────────────────────────────────────────────┐ |
|  │ [K-line chart placeholder — chart lib TBD]               │ |
|  └──────────────────────────────────────────────────────────┘ |
+--------------------------------------------------------------+
|  籌碼指標                                                     |
|  +----------+ +----------+ +----------+                       |
|  | RS Rank  | | SEPA     | | 連續買超 |                       |
|  | 92       | | ✓ Stage2 | | 3 / 5 d |                       |
|  +----------+ +----------+ +----------+                       |
+--------------------------------------------------------------+
|  三大法人 (近 5 日)                                           |
| 日期      外資     投信     自營商   合計                      |
| 05-08   ▲+1,200  ▲+300   ▼-50    ▲+1,450                   |
| 05-07   ▲+800    ▼-100   ▲+30    ▲+730                     |
| ...                                                          |
+--------------------------------------------------------------+
|  近期偵測 Pattern (近 30 日)                                   |
| 日期    Pattern         Score   結局                           |
| 04-22   SEPA breakout  0.86    多單進場 → +2.5% 持有中         |
| 04-15   pullback       0.62    未進場                          |
+--------------------------------------------------------------+
```

**Layout slots**
| Slot | 內容 | shadcn primitive | 紅漲綠跌套用？ |
|---|---|---|---|
| 頁首 | symbol + 名稱 + 現價 + 漲跌 + 量 / 振幅 | — | 是（漲跌） |
| K 線區 | placeholder（標明圖庫待定） | `Card` | 否 |
| 籌碼 KPI | 3 張小卡 (RS / SEPA / 連續買超) | `Card`（不用 KpiCard，因為非單一數字 + 配色語意不同） | 部分（連續買超用 --up） |
| 三大法人表 | 5 列 × 5 欄；每數值欄套色 | `DataTable`（compact density） | 是 |
| Pattern 表 | 5 列 × 4 欄；row click → `/audit?...` | `DataTable` | 是（pattern 方向 + 結局 P&L） |

**資料來源**
- (future) `GET /api/admin/market/symbols/:symbol`（含 quote / chart series / chips / institutional / patterns）
- 訂閱 SSE event_type：`pattern_detected`（若該 symbol 在 universe，新 pattern → patterns 表 prepend）

**互動**
- 「日 / 週」toggle → 切換 K 線時間粒度（local state；後端再請）
- click 籌碼小卡 → 展開 tooltip 詳細解讀（tooltip primitive future）
- click pattern 表 row → `navigate(/audit?symbol=2330&date_from=...)` 或展開該 pattern 的 LLM decision detail

**State 行為**
- `loading`：頁首數字 inline Skeleton；K 線整塊 Skeleton；籌碼 3 張卡 Skeleton；2 個表 Skeleton。
- `empty`：symbol 無交易資料 →「該 symbol 無資料 — 確認代號」+ 返回連結。
- `error`：「載入 2330 失敗 — {reason}」+ retry + 返回。
- `live-update`：`pattern_detected` 對應該 symbol → patterns 表 prepend + flash。

**紅漲綠跌套用範例**
- 頁首「漲跌」：紅 `--up` + `<ArrowUp/>`；綠 `--down` + `<ArrowDown/>`。
- 三大法人欄：>0（買超）紅 + `<ArrowUp className="inline size-3"/>`；<0（賣超）綠 + `<ArrowDown/>`。
- pattern「Pattern」欄：方向性 pattern (`breakout` / `bullish reversal`) 紅 + `<TrendingUp/>`；空方 pattern 綠 + `<TrendingDown/>`。
- pattern「結局」欄：「+2.5% 持有中」紅 + `<ArrowUp/>`；「-3% 出場」綠 + `<ArrowDown/>`；「未進場」muted。

**鍵盤可達性**
- Tab：返回 → 日/週 toggle → 籌碼小卡 → 三大法人 row → pattern row
- Enter on pattern row → 展開 detail
- 沒 modal，所以 Esc 留給瀏覽器原生（清焦點）

---

## 12. `/skills` — Skills 列表

**用途：** ~30 個 Claude Agent SDK skill（YAML frontmatter + Markdown body）的列表 + 啟用 toggle + 最後執行時間。
**後端狀態：** ✅ v0（GET `/api/admin/skills`，list-only）。PATCH `/api/admin/skills/:name` 仍 deferred。

**v0 範圍（已 ship — `web-admin-skills-pages` change，2026-05-09）**
- 實際 ship：filter bar（搜尋 input + 類別 select，client-side 即時過濾、無 debounce）、responsive grid（1/2/3/4 col）、卡片顯示 name（font-mono）+ description（line-clamp-2）+ `<CategoryBadge>`（neutral `secondary` Badge + Lucide icon 配對，**不**用紅漲綠跌）。卡片 click + Enter / Space 導向 `/skills/<name>`。
- 仍為 stub：「☑ 啟用」toggle、「最後跑: 5m ago」時間、「編輯 →」按鈕。本 v0 是 **read-only**：沒有 `enabled` 欄位、沒有執行 log，所以 toggle 與時間在後端落地前不會出現於 UI。

**ASCII wireframe**
```
+--------------------------------------------------------------+
|  搜尋: [____________]   類別: [ 全部 ▼ ]   排序: [ 最近 ▼ ]    |
+--------------------------------------------------------------+
|  ┌────────────────────┐  ┌────────────────────┐  ┌──────────┐ |
|  │ ✦ market_data_tool │  │ ✦ rs_calculator    │  │ ✦ ...    │ |
|  │ 抓 daily / quote   │  │ 計算 RS percentile │  │          │ |
|  │ 類別: data         │  │ 類別: indicator    │  │          │ |
|  │ 最後跑: 5m ago     │  │ 最後跑: 30m ago    │  │          │ |
|  │ [☑ 啟用]    [編輯→]│  │ [☑ 啟用]    [編輯→]│  │          │ |
|  └────────────────────┘  └────────────────────┘  └──────────┘ |
|  ...（4 col 網格，~30 卡）                                     |
+--------------------------------------------------------------+
```

**Layout slots**
| Slot | 內容 | shadcn primitive | 紅漲綠跌套用？ |
|---|---|---|---|
| Filter bar | 搜尋 input / 類別 select / 排序 select | `Input` / `Select` | 否 |
| Skills grid | 4-col `Card`，每卡：name / 描述 / 類別 / 最後跑 / 啟用 toggle / 編輯 | `Card` / `Switch` (future) / `Button` | 否 |

**資料來源**
- (future) `GET /api/admin/skills?category=&q=`
- (future) `PATCH /api/admin/skills/:name { enabled: bool }`
- 訂閱 SSE event_type：不訂閱

**互動**
- 啟用 toggle → 樂觀 UI（switch 立刻變色），fail 後 revert + toast
- 「編輯 →」→ `navigate(/skills/<name>)`
- 搜尋 200ms debounce
- 卡片整張 click（toggle / edit 之外）→ navigate（同編輯）

**State 行為**
- `loading`：grid 12 張 Skeleton 卡。
- `empty`：「無符合條件的 skill」+「清除 filter」按鈕。
- `error`：頁頂紅 banner「載入 skills 失敗」+ retry。
- `live-update`：不適用。

**紅漲綠跌套用範例**
- 啟用 toggle 不套漲跌色（避免「啟用 = 漲」誤導），用 shadcn 預設 zinc primary on / muted off。本卡無價格語意，故無紅漲綠跌；但因屬「狀態語意」需 icon 配對 → 啟用顯 `<Check className="size-3"/>` 在 toggle 旁，關閉顯 `<X className="size-3 text-muted-foreground"/>`。

**鍵盤可達性**
- Tab：filter → 卡 1..N（卡片整張 focusable，Enter = 編輯）→ 卡內 toggle (Tab inside card) → 編輯按鈕
- Space on toggle → 切換啟用
- Enter on 卡 → 編輯

---

## 13. `/skills/:name` — Skill 編輯器

**用途：** 編輯單一 skill 的 YAML frontmatter + Markdown body；存檔。
**後端狀態：** ✅ v0（GET `/api/admin/skills/:name`，read-only）。PUT 仍 deferred。

**v0 範圍（已 ship — `web-admin-skills-pages` change，2026-05-09）**
- 實際 ship：header（back-link `← Skills` + name as `<h1>` font-mono + `<CategoryBadge>` + 一行 description）、cited-specs row（每個 spec 名以 `<code>` chip 呈現；空陣列顯示「（無 cited_specs）」fallback）、Body Card（`<pre className="whitespace-pre-wrap font-mono text-sm">` 含 char count，**沒有** markdown parser／syntax highlighter）。`max-h-[70vh] overflow-auto` 防止超長 body 把頁面拉到天荒地老。
- 404 surfaces 為「找不到 skill: `<name>`」empty-state + 「返回 Skills」按鈕；500 surfaces 為 destructive Card + AlertCircle + 重試 button（與 §共用 patterns 一致）。
- 仍為 stub：「預覽」/「儲存」按鈕、YAML / Markdown 編輯 textarea、dirty state、Cmd/Ctrl+S hotkey、離頁 confirm dialog。本 v0 是 **read-only**：沒有寫回 disk 的後端 API，所以編輯器在 PUT endpoint 落地前不會出現於 UI。

**ASCII wireframe**
```
+--------------------------------------------------------------+
| ← /skills   market_data_tool                  [預覽] [儲存]   |
+--------------------------------------------------------------+
|  ┌─ Frontmatter (YAML) ────────────────────────────────────┐  |
|  │ name: market_data_tool                                  │  |
|  │ description: 抓取 daily 與 quote                        │  |
|  │ category: data                                          │  |
|  │ enabled: true                                           │  |
|  └─────────────────────────────────────────────────────────┘  |
|  ┌─ Body (Markdown) ───────────────────────────────────────┐  |
|  │ # 用途                                                  │  |
|  │ 從 FinMind 與 Shioaji 取得 OHLCV ...                    │  |
|  │                                                         │  |
|  │ # I/O                                                   │  |
|  │ ...                                                     │  |
|  └─────────────────────────────────────────────────────────┘  |
|                                                               |
|  狀態：● 已修改 (Cmd+S 儲存)        ● 上次儲存 5m ago          |
+--------------------------------------------------------------+
```

**Layout slots**
| Slot | 內容 | shadcn primitive | 紅漲綠跌套用？ |
|---|---|---|---|
| 頁首 | 返回 + name + 「預覽」+「儲存」（primary，dirty 時亮） | `Button` | 否 |
| YAML 區 | 純 textarea（編輯器 lib 留 future）+ 1 行 lint 錯誤訊息 | `Textarea` | 否 |
| Markdown 區 | 大 textarea（編輯器 lib 留 future）；右側預覽切換 | `Textarea` | 否 |
| 狀態列 | dirty 標記 + 上次儲存時間 | — | 是（warning / 確認） |

**資料來源**
- (future) `GET /api/admin/skills/:name`
- (future) `PUT /api/admin/skills/:name { yaml, markdown }`
- 訂閱 SSE event_type：不訂閱

**互動**
- 編輯任一區 →「儲存」按鈕由 muted 變 primary，狀態列「● 已修改」
- Cmd/Ctrl+S → 觸發儲存（與按按鈕等效）
- 「預覽」→ Markdown 區切換為 readonly render（用 `<pre>` 暫顯，後續 page change 加 markdown renderer）
- 離開頁時若 dirty → `window.confirm('未儲存，確定離開？')`

**State 行為**
- `loading`：兩區 Skeleton。
- `empty`：skill 不存在 →「找不到 skill: <name>」+「返回 skills」按鈕。
- `error`：「載入失敗」+ retry；儲存失敗 → 紅 banner「儲存失敗 — {reason}」+「重試」/「複製內容到剪貼簿」（避免遺失）。
- `live-update`：不適用。

**紅漲綠跌套用範例**
- 狀態列「已修改」用 `--warning` + `<AlertTriangle className="size-3"/>`；「已儲存」用 muted + `<Check/>`。不套漲跌色（編輯器與市場語意無關）。

**鍵盤可達性**
- Tab：返回 → 預覽 → 儲存 → YAML 區 → Markdown 區
- Cmd/Ctrl+S 全頁 hotkey
- Esc 在 textarea 內無動作（避免吃掉編輯）；離頁 confirm dialog 中 Esc = 取消離開

---

## 14. `/memory` — 長期記憶

**用途：** Memory entries CRUD + FTS5 search。
**後端狀態：** ✅ read-only v0（GET `/api/admin/memory/rows` + GET `/api/admin/memory/search`，spec: `openspec/specs/{memory-store,admin-memory-endpoints,web-admin-memory-page}/spec.md`，shipped 2026-05-09）

> **v0 範圍（read-only）：** 本頁 v0 為 read-only，下面 wireframe 中的「+ 新增」/「⋮ 編輯 / 刪除」/「Cmd+N」/ inline 新增 row / 刪除 confirm dialog **皆為後續 change 的目標，未實作**。同樣 deferred 的還有 tag autocomplete、date-range filter、semantic search。
>
> v0 實際 render：
> - 頂部 segmented control 切換「瀏覽」/「搜尋」兩個 view（取代 wireframe 上方那一條 filter bar）。
> - 「瀏覽」view = kind `<Select>`（5 個 option：全部 / 筆記 / 經驗 / 提案 / 復盤）+ 1-tag chip-input + 5-col `<DataTable>`（時間 / kind / tags / 內容預覽 / 來源）+ DataTable 內建分頁。
> - 「搜尋」view = single `<Input>`（FTS5 表達式，例 `VCP AND breakout`）+ 「搜尋」 button；按 Enter / Cmd+Enter / Ctrl+Enter 送出；空 input 不發 request、改顯示「請輸入查詢關鍵字」。
> - row click（或 keyboard Enter / Space）= inline expand 顯示完整 `content`（`<pre>` block，max-h 70vh，含字元數）；切 tab 收合展開。
> - 載入：6 列 Skeleton；空集合：「尚無 memory；待 Phase 5 復盤 / proposal 任務寫入」 / 「無符合條件的 memory」+ 清除 filter / 「找不到符合『q』的 memory」三種；error：destructive Card + AlertCircle + 重試；FTS5 syntax error → inline「查詢語法錯誤」。
> - **無**新增 / 編輯 / 刪除 button、無 Textarea、無 Save/Cmd+S、無 dirty state、無 ⋮ popover。寫入路徑要等 Phase 5 復盤 / proposal job change 把 memory writer 接上才會出現。

**ASCII wireframe**
```
+--------------------------------------------------------------+
|  搜尋: [____________]    類型: [ 全部 ▼ ]    [+ 新增 (Cmd+N)] |
+--------------------------------------------------------------+
| Type     Content (摘要 80 字)                建立      動作    |
+--------------------------------------------------------------+
| pattern  法人連續買超 + RS≥80 → SEPA breakout 命中  04-22  ⋮  |
| rule     2330 不參與當沖（避免高頻交易稅）          03-15  ⋮  |
| outcome  Backtest j#88 SEPA 2024 年化 18.2%         05-01  ⋮  |
| ...                                                          |
+--------------------------------------------------------------+
|              第 1 / 8 頁  [< 上一頁]  [下一頁 >]              |
+--------------------------------------------------------------+
```

**Layout slots**
| Slot | 內容 | shadcn primitive | 紅漲綠跌套用？ |
|---|---|---|---|
| Filter bar | 搜尋 + 類型 select +「+ 新增」 | `Input` / `Select` / `Button` | 否 |
| Memory DataTable | 4 欄；row click → expand inline 顯全文；⋮ 為 popover「編輯 / 刪除」 | `DataTable` | 否 |
| Pagination | DataTable 內建 | — | 否 |

**資料來源**
- (future) `GET /api/admin/memory?q=&type=&limit&offset`
- (future) `POST /api/admin/memory { type, content }`
- (future) `DELETE /api/admin/memory/:id`
- 訂閱 SSE event_type：不訂閱

**互動**
- 搜尋 200ms debounce → 重查（FTS5 server-side）
- 「+ 新增」/ Cmd/Ctrl+N → 開 inline 新增 row（type select + content textarea + 儲存 / 取消）
- ⋮ → popover「編輯 / 刪除」；刪除 → confirm dialog
- click row → 展開 inline 全文

**State 行為**
- `loading`：5 列 Skeleton。
- `empty`：「無記憶條目」/「無符合搜尋的條目」+「+ 新增第一筆」。
- `error`：retry 卡。
- `live-update`：不適用。

**紅漲綠跌套用範例**
- 不套漲跌色（與市場語意無關）。「Type」欄用 `<Badge variant="outline">` 顯示 type 字串，不套漲跌色。
- 刪除 confirm dialog 主按鈕用 `--destructive` + `<X/>`（雙重編碼鐵律仍適用）。

**鍵盤可達性**
- Tab：filter →「+ 新增」 → row 1..N → ⋮ button per row → 分頁
- Enter on row → 展開全文；再 Enter / Esc 收合
- Cmd/Ctrl+N → 觸發「+ 新增」
- ⋮ popover 內 ↑↓ 切項，Esc 關閉

---

## 15. `/sessions` — 對話歷史搜尋

**用途：** Claude Code session transcripts FTS5 搜尋（時間範圍 + 關鍵字）。
**後端狀態：** ❌（future GET `/api/admin/sessions`）

**ASCII wireframe**
```
+--------------------------------------------------------------+
|  搜尋: [_____________________________________]  [搜尋 (↩)]    |
|  日期: [2026-04-01] ~ [2026-05-08]                            |
+--------------------------------------------------------------+
|  3 個 sessions、12 段命中                                      |
+--------------------------------------------------------------+
| 早盤盤前掃描討論  · 2026-04-22 09:15                           |
|   …他 …(高亮)`SEPA breakout`… 是個好的進場訊號嗎…              |
|   …(高亮)`SEPA breakout`… 確認後 confirm gate 倒數 5m…          |
|                                                       [開啟 →]|
+--------------------------------------------------------------+
| 2330 籌碼分析     · 2026-04-15 14:00                          |
|   …(高亮)`SEPA`… 連續 8 季 EPS 成長…                          |
|                                                       [開啟 →]|
+--------------------------------------------------------------+
```

**Layout slots**
| Slot | 內容 | shadcn primitive | 紅漲綠跌套用？ |
|---|---|---|---|
| Search bar | 大型 input + 搜尋按鈕 | `Input` / `Button` | 否 |
| Date range | 兩個 date picker | `Input type=date` | 否 |
| Result group list | 每 session 一張 `Card`，內含 N 個高亮 snippet +「開啟 →」 | `Card` | 否 |

**資料來源**
- (future) `GET /api/admin/sessions?q=&date_from=&date_to=&limit=20`
- 訂閱 SSE event_type：不訂閱

**互動**
- 在 search input 按 ↩ 觸發搜尋
- click「開啟 →」→ `navigate(/chat/<sessionId>?highlight=...)`
- click snippet → 同上但帶 `?msgId=...` jump 到該訊息

**State 行為**
- `loading`：3 張卡 Skeleton。
- `empty`：「無命中」+ `<History muted/>` +「試試其他關鍵字」。
- `error`：retry banner。
- `live-update`：不適用。

**紅漲綠跌套用範例**
- 高亮 snippet 用 `bg-warning/20` 黃底（不套紅綠 — 黃色標記是搜尋慣例；雙重編碼鐵律不影響此處因為「搜尋高亮」非語意警告）。

**鍵盤可達性**
- Tab：search input → 日期 from → to → 搜尋按鈕 → result Card 1..N →「開啟 →」per card
- ↩ on search input → 觸發搜尋
- Enter on Card → 等同「開啟」

---

## 16. `/settings` — 設定

**用途：** API keys（Anthropic / FinMind / Shioaji）、主題、Safety toggle (`OHMYSTOCK_AUTO_EXECUTE`)、breaker thresholds。
**後端狀態：** ✅（read-only v0；`GET /api/admin/settings`）；PUT 為意圖性 deferred — `OHMYSTOCK_AUTO_EXECUTE` 等安全旗標僅可由 `.env` + restart 改動（`docs/safety-and-simulation.md` §2.9 防禦縱深）。

**ASCII wireframe (read-only v0)**
```
+--------------------------------------------------------------+
|  設定（只讀檢視。變更請編輯 .env 並重啟服務。）                |
+--------------------------------------------------------------+
|  ┌─ API keys ──────────────────────────────────────────────┐  |
|  │ Anthropic                              [已設定]         │  |
|  │ FinMind                                [未設定]         │  |
|  │ Shioaji                                [已設定]         │  |
|  │   編輯 .env 並重啟以變更                                  │  |
|  └─────────────────────────────────────────────────────────┘  |
|                                                               |
|  ┌─ 主題 ──────────────────────────────────────────────────┐  |
|  │ 模式: [ 跟隨系統 ▼ ] (disabled)                          │  |
|  │   此版本未提供主題切換 UI                                 │  |
|  └─────────────────────────────────────────────────────────┘  |
|                                                               |
|  ┌─ Safety  (border-warning + AlertTriangle) ──────────────┐  |
|  │ ⚠  Safety                                                │  |
|  │   AUTO_EXECUTE 關閉（人工 Confirm Gate）                  │  |
|  │   Broker：shioaji-sim                                    │  |
|  │   編輯 .env 並重啟以變更                                  │  |
|  └─────────────────────────────────────────────────────────┘  |
|                                                               |
|  ┌─ Breakers ─────────────────────────────────────────────┐   |
|  │ 信心下限   [ 0.70 ]    (disabled)                        │  |
|  │ 單日上限   [ 5    ] 筆 (disabled)                        │  |
|  │ 配額       [ 25   ] %  (disabled)                        │  |
|  │ 偏離上限   [ 30   ] %  (disabled)                        │  |
|  │ 鎖定小時   [ 24   ] h  (disabled)                        │  |
|  │ 鎖定觸發   [ -5   ] %  (disabled)                        │  |
|  │ 帳戶權益   [1,000,000] TWD (disabled)                    │  |
|  │   編輯 .env 並重啟以變更                                  │  |
|  └─────────────────────────────────────────────────────────┘  |
+--------------------------------------------------------------+
```

`auto_execute=true` 時：Safety Card 改套 `border-destructive` + `AlertCircle`，文案改為 "⚠ AUTO_EXECUTE 已啟用"。

**Layout slots**
| Slot | 內容 | shadcn primitive | 紅漲綠跌套用？ |
|---|---|---|---|
| Header | 頁標題 + "只讀檢視" 提示 | 純文字 | 否 |
| API keys 區 | 3 列：name / Badge（已設定/未設定）；無 mask dot，無 raw value | `Card` / `Badge` | 否 |
| 主題區 | 1 個 disabled select（佔位） | `Card` / `Select` (disabled) | 否 |
| Safety 區 | warning/destructive Card + Lucide icon + AUTO_EXECUTE 文案 + broker | `Card` (`border-warning` 或 `border-destructive`) / Lucide `AlertTriangle` 或 `AlertCircle` | 是（warning / destructive 雙重編碼） |
| Breakers 區 | 7 個 disabled `<input>`（`type="text" inputMode="numeric"`，因為 `type="number"` 會剔除千分位逗號） | `Card` / `Input` (disabled) | 否 |

**資料來源**
- `GET /api/admin/settings`（Bearer auth, `{ok,data,error}` envelope, 4 sections — `api_keys` / `theme` / `safety` / `breakers`）
- 訂閱 SSE event_type：不訂閱（`Settings` 對 process 生命週期內 immutable）

**互動（read-only v0）**
- 全頁 disabled。沒有「儲存」「啟用」「我已了解風險」「更新」按鈕。
- 唯一可點：載入失敗時的「重試」按鈕。
- 鍵盤 Tab 順序：API keys → 主題 → Safety → Breakers（spec `web-admin-settings-page` 強制）。

**State 行為**
- `loading`：4 個 Card 各帶 Skeleton。
- `empty`：不適用（每欄一律有值，secret 以布林呈現、未設定顯示「未設定」Badge）。
- `error`：頁頂單一 destructive Card + retry 按鈕。
- `live-update`：不適用。

**紅漲綠跌套用範例**
- `auto_execute=false`：Safety Card `border-warning` + `<AlertTriangle className="text-warning"/>` + 「AUTO_EXECUTE 關閉（人工 Confirm Gate）」。
- `auto_execute=true`：Safety Card `border-destructive` + `<AlertCircle className="text-destructive"/>` + 「⚠ AUTO_EXECUTE 已啟用」。色彩永遠搭配 icon — 不依賴顏色為唯一訊號（§0.3 強制）。

**鍵盤可達性**
- Tab：API keys 區（3 列 Badge，非互動，跳過）→ 主題（disabled select）→ Safety Card → Breakers Card 內 7 個 disabled input → 「重試」（僅錯誤狀態時存在）
- 沒有寫入路徑就沒有 confirm dialog；Esc 不需處理。

---

## 17. `/audit` — 稽核日誌

**用途：** 所有 journal kinds 的稽核瀏覽（最大 DataTable）；可下載 JSONL；接收 risk_off_triggered 即時警示。
**後端狀態：** ✅（`GET /api/admin/journal/rows`）

**ASCII wireframe**
```
+--------------------------------------------------------------+
|  Filter bar                                                   |
|  Kind: [ ☑ 全部 ]  Symbol: [____]  Decision id: [____]         |
|  日期: [2026-04-01] ~ [2026-05-08]                            |
|              [套用] [清空] [匯出 JSONL]   [ density ⇆ compact ]|
+--------------------------------------------------------------+
| 時間            Kind          Symbol  Decision  狀態   摘要     |
+--------------------------------------------------------------+
| 14:03:12       fill          2454    d#129    ✓ ok   100@1180 |
| 14:03:08       entry         2454    d#129    ✓ ok   ...      |
| 14:02:55       awaiting_     2454    d#129    ◐      conf=0.82|
|                confirm                                        |
| 14:02:48       decision_     2454    d#129    ✓ ok   多 100   |
|                made                                           |
| 14:02:30       decider_      2454    d#129    ◐      PM 評估  |
|                thinking                                       |
| 13:55:12       risk_off_     —       —        ⚠      VIX>30   |
|                triggered                                      |
+--------------------------------------------------------------+
|              第 1 / 42 頁  [< 上一頁]  [下一頁 >]  共 8,432 列|
+--------------------------------------------------------------+
```

**Layout slots**
| Slot | 內容 | shadcn primitive | 紅漲綠跌套用？ |
|---|---|---|---|
| Filter bar | kind multi / symbol / decision_id / date range / 套用 / 清空 / 匯出 / density toggle | `Input` / `Checkbox` / `Button` | 否 |
| Audit DataTable | 6 欄；compact density 預設；row click → drawer / 展開該 decision 完整 chain | `DataTable` (`density="compact"`) / `StatusBadge` | 否（純列表） |
| Pagination + total count | DataTable 內建 +「共 N 列」 | — | 否 |
| Risk-off banner | 頁頂條件式：`risk_off_triggered` 後 24h 內顯示 | `Card` (warning) | 是（警告） |

**資料來源**
- `GET /api/admin/journal/rows?kind=&symbol=&decision_id=&date_from=&date_to=&limit&offset`
- 訂閱 SSE event_type：`journal_written`（新列即時 prepend on page 1）、`risk_off_triggered`（彈頁頂 banner）

**互動**
- click row → 展開 inline 顯示該 decision_id 完整 chain（呼叫 `GET journal/decisions/:id`，按時序 ASC 列出全 kinds）
- 「匯出 JSONL」→ blob download 當前 filter 結果
- density toggle → 改 `<DataTable density>` 局部
- 排序：`時間` desc 預設

**State 行為**
- `loading`：表 10 列 Skeleton。
- `empty`：「此 filter 無紀錄」+「清空 filter」。
- `error`：retry。
- `live-update`：`journal_written` 推來 → page 1 prepend + flash；`risk_off_triggered` → 頁頂彈警告 banner，含時間 + reason，可手動 dismiss。
- `reconnect`：頁頂 warning「重新連線中…」；連上後若在 page 1 一次性 GET 補齊。

**紅漲綠跌套用範例**
- 「狀態」欄全用 `<StatusBadge>`，不套漲跌色（kind 與漲跌語意無關）。
- `risk_off_triggered` banner 用 `--warning` 底 + `<AlertTriangle className="text-warning"/>`；連續 risk_off > 1 次或關鍵字含 `breaker_tripped` 改 `--destructive` + `<AlertCircle/>`。

**鍵盤可達性**
- Tab：filter → density toggle → row → 分頁
- Enter on row → 展開 decision chain；再 Enter / Esc 收合
- 排序 header `aria-sort` 切換

---

## 共用 patterns（給後續 per-page change 參考）

### 1. Loading skeleton

| 場景 | 寫法 |
|---|---|
| `KpiCard` loading | 1 個 `<Skeleton className="h-7 w-24"/>` 取代 value（label 留 visible） |
| DataTable loading | 預設 3 列；高度依 `density` 決定（comfortable=36px / compact=28px）；列內各欄寬度 = `<Skeleton className="h-4 w-{20 \| 16 \| 12}"/>` 對應預期 cell 寬 |
| Card 內整塊圖區 | `<Skeleton className="h-64 w-full rounded-md"/>` |

**鐵律：** Skeleton 尺寸必須對齊預期內容尺寸（避免內容載入後 layout shift）。不可用 generic `<Skeleton/>` 不指定大小。

### 2. Empty state

```tsx
<Card className="p-8 text-center">
  <Icon className="mx-auto size-8 text-muted-foreground" />  // Lucide icon 對應頁主題
  <h3 className="mt-3 text-sm font-medium">主訊息（11~14 字）</h3>
  <p className="mt-1 text-xs text-muted-foreground">輔助說明（&lt;30 字）</p>
  {actionButton && <Button className="mt-4">...</Button>}
</Card>
```

主訊息範例：「目前無開倉」「尚無對話」「本次掃描無命中」。**禁用** emoji；必用 Lucide。

### 3. Error panel

```tsx
<Card className="border-destructive/50 p-6">
  <div className="flex items-start gap-3">
    <AlertCircle className="size-5 text-destructive shrink-0" />
    <div className="flex-1">
      <h3 className="text-sm font-medium">載入失敗</h3>
      <p className="mt-1 text-xs text-muted-foreground">{error.message}</p>
      <Button size="sm" variant="outline" className="mt-3">重試</Button>
    </div>
  </div>
</Card>
```

### 4. SSE live-region pattern

**重連 banner**（頁頂，固定位置）：
```tsx
{reconnectAttempt > 0 && (
  <Card role="status" aria-live="polite" className="border-warning/50 bg-warning/5 px-3 py-2">
    <div className="flex items-center gap-2 text-xs">
      <Hourglass className="size-3.5 text-warning animate-spin" />
      <span>重新連線中…（嘗試 {reconnectAttempt}/5）</span>
    </div>
  </Card>
)}
```

`aria-live="polite"` 讓螢幕閱讀器讀出。重連回穩後 `reconnectAttempt` 歸零，banner 消失。

**新事件 row-flash**（DataTable / Live feed 內）：
```tsx
className={cn(
  '...',
  isNewlyArrived && 'animate-[flash_800ms_ease-out]'
)}
// @keyframes flash { 0% { background: var(--warning) / 20%; } 100% { background: transparent; } }
```

預設 800ms 黃底淡出。`prefers-reduced-motion` 時改 background 直接設值 250ms。

### 5. 紅漲綠跌 universal rule（鐵律）

| 用法 | 是否合法 |
|---|---|
| `text-up` only（沒 icon） | ❌ 禁止 |
| `<ArrowUp/>` only（沒 color） | ⚠ 不建議（圖標太小看不清方向，需配色加強） |
| `text-up` + `<ArrowUp/>` | ✅ 標準 |
| `text-up` + emoji 紅圈 | ❌ 禁止（不用 emoji） |

跌、危險、警告同理：必須色 + Lucide icon 雙重編碼。

### 6. 鍵盤普世模式

- 全頁 hotkey 約定：`Cmd/Ctrl+N` → 新增、`Cmd/Ctrl+S` → 儲存、`Cmd/Ctrl+Enter` → 主要 submit
- 單字 hotkey 約定（focus 在 row 或卡片時）：`Y` 確認 / `N` 拒絕 / `?` 開 cheatsheet（cheatsheet 留 future change）
- 全頁 `?` 開鍵盤指南 — **TODO future**：本 change 不落地，後續 `web-admin-keyboard-shortcuts` change 加
- DataTable row 一律 `tabIndex=0` + Enter 觸發 `onRowClick`
- Sortable header 一律 `aria-sort="ascending|descending|none"`
- 對話 / dialog / drawer / popover 開啟時 `Esc` 關閉，不可吃掉瀏覽器原生 Esc 行為（如取消 fullscreen）
- 焦點環不可隱藏：所有 interactive 元素 `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring`

---

## 延伸閱讀

- 後端 EventBus / Mask / 16 個 event_type：`docs/backend-eventbus.md`
- Bearer auth / Mask Spec：`docs/auth-and-mask.md`
- 桌面 wireframe 既有風格：`docs/frontend.md`（本檔取代其中 17 頁 wireframe 章節，frontend.md 其餘狀態管理 / Zustand / 路由設計仍有效）
- 公網 pixel UI：`docs/frontend-public-pixel.md`（本檔不涵蓋）
- 共用元件 props 契約：`openspec/changes/web-admin-design-system-and-page-wireframes/specs/web-admin-design-system/spec.md`

> 本檔為 SSOT。其他文件描述若與本檔衝突，以本檔為準。
