# Frontend — Admin Panel React UI 設計（`web-admin/`）

> 本檔從 `design-zh-TW.md` §4.9 拆出（2026-04-26 docs reorg）。
> **2026-04-27 update：** v3 拆為**前後台兩專案 monorepo**；本檔範圍**改為 web-admin/**（後台 18 頁完整工作介面）。
> **公網前台 pixel UI 見 [`frontend-public-pixel.md`](frontend-public-pixel.md)。**
> 對應程式：`web-admin/src/`
> SSOT：本檔為 **後台 React UI 全部設計**（路由、Zustand、API client、Tailwind/shadcn、design tokens、a11y、wireframes）的唯一權威。

對標 Vibe-Trading `web/src/`，但採用更現代的元件與狀態方案。**MVP 階段以 CLI 為主**（typer），Web UI 在 Phase 4 才上線。

---

## 0. 前後台分層架構（v3 新增）

### 0.1 兩專案 monorepo 概觀

ohMyStock v3 把網頁拆為**兩個獨立 React app**：

| 專案 | 對象 | 範圍 | 部署 |
|---|---|---|---|
| **`web-admin/`**（本檔） | 只有用戶本人（Bearer token auth） | 18 頁完整工作介面：Dashboard / Chat / Swarm / Backtest / Paper Trading / Market / Skills / Memory / Sessions / Settings / Audit | localhost / Cloudflare Tunnel |
| **`web-public/`**（[`frontend-public-pixel.md`](frontend-public-pixel.md)） | 任何人（無認證、masked） | 像素辦公室 demo：9 角色擬人化呈現 LLM 工作流 | Vercel / Cloudflare Pages（公網） |

**為什麼拆兩專案：** 完全 bundle 隔離 — 訪客連 admin 程式碼都看不到；admin 可放 VPN / 不對公網；details 見 [`auth-and-mask.md`](auth-and-mask.md) §5。

### 0.2 共用 packages（monorepo）

```
ohMyStock/
├── web-admin/            ← 本檔範圍
├── web-public/           ← frontend-public-pixel.md 範圍
└── packages/
    ├── ui-tokens/        ← design tokens（紅漲綠跌色票、字型 scale）
    ├── api-types/        ← OpenAPI codegen 出的 TS types
    ├── event-types/      ← Event dataclass 對映 TS interface
    └── api-client-public/← public endpoint client（無 auth header）
```

### 0.3 資料流（含 EventBus）

```
Python LLM Agent
  └─ tool 呼叫 / 決策 → Backend EventBus
        ├─ admin channel (raw 全資料)  → /api/admin/events  (auth)  → web-admin 即時更新
        └─ public channel (masked)     → /api/public/events (no auth) → web-public pixel 動畫

  REST CRUD：
  └─ /api/admin/* (auth required)  → web-admin 18 頁 CRUD
  └─ /api/public/recent_events     → web-public 歷史 timeline
```

EventBus / serializer 詳見 [`backend-eventbus.md`](backend-eventbus.md)。

### 0.4 認證與 Mask

- web-admin 所有 API 呼叫帶 `Authorization: Bearer <OHMYSTOCK_ADMIN_TOKEN>`
- web-admin 看到的資料**未 mask**（含真 symbol / price / pnl_twd / account_id）
- 詳見 [`auth-and-mask.md`](auth-and-mask.md) §2

---

## 1. 技術棧細節

| 領域 | 選擇 | 理由 |
|---|---|---|
| 基底 | React 19 + Vite + TypeScript | Vibe-Trading 一致，HMR 快 |
| 樣式 | **Tailwind CSS v4** | 與 shadcn/ui 整合最佳 |
| UI 元件庫 | **shadcn/ui**（Radix + Tailwind） | copy-paste 不鎖框架，可深度客製 |
| 狀態 | **Zustand**（client）+ **TanStack Query v5**（server cache） | Vibe-Trading 用 Zustand；TanStack 處理 API cache / 重試 |
| 路由 | React Router v7 | 巢狀路由 + loader 預載 |
| 表單 | react-hook-form + zod | 型別安全的下單 / 設定表單 |
| 圖表 | **KLineCharts**（K 線）+ **shadcn/ui Charts (Recharts)**（一般）+ **Tremor**（KPI/BarList）+ **React Flow**（DAG）+ **ApexCharts**（heatmap） | 詳 §6；華語金融最對味組合 |
| Markdown | `react-markdown` + `remark-gfm` + `rehype-highlight` | 渲染 LLM 回覆 / skill 文件 |
| 串流 | 原生 `EventSource`（SSE） | 簡單、無 polyfill |
| 國際化 | `i18next` + `react-i18next`，預設 **zh-TW** | 介面用語對齊台股慣例 |
| 圖示 | `lucide-react` | shadcn 標配 |
| Date | `dayjs` + `dayjs/locale/zh-tw` | 比 date-fns 輕 |
| 測試 | Vitest + React Testing Library + Playwright（E2E） | Vite 原生 |

---

## 2. 路由與頁面結構

```
/                          → Dashboard（總覽：權益曲線、近期 run、市場熱點）
/chat                      → 對話模式（單一 agent，自由問答）
/chat/:sessionId           → 進入既有 session
/swarm                     → Swarm 入口（10 個 preset 卡片）
/swarm/:preset/:runId      → Swarm 執行視覺化（DAG 即時更新）
/backtest                  → 回測入口（策略表單 + 歷史 job 列表）
/backtest/:jobId           → 回測結果（資金曲線、回撤、交易明細、診斷）
/paper                     → 模擬交易（下單、部位、委託、權益）
/paper/orders              → 委託歷史
/paper/positions           → 持倉明細
/market                    → 市場掃描（即時行情、籌碼、強弱排行）
/market/:symbol            → 個股頁（K 線 + 三大法人 + 融資融券 + 籌碼分點）
/skills                    → Skills 瀏覽 / 編輯
/skills/:name              → Skill 詳情（YAML + Markdown 預覽）
/memory                    → 長期記憶管理
/sessions                  → 對話歷史 + FTS5 搜尋
/settings                  → 設定（API Key、Shioaji、FinMind、主題、合規）
/audit                     → 稽核日誌瀏覽（管理員）
```

---

## 3. 元件樹（核心區塊）

```
<App>
├── <Layout>                          # 側邊欄 + 主內容區
│   ├── <Sidebar>                     # 主導覽
│   ├── <TopBar>                      # 搜尋、使用者選單、佈景切換
│   └── <DisclaimerFooter>            # 強制免責聲明
├── <Routes>
│   ├── <DashboardPage>
│   │   ├── <EquityCurveCard>
│   │   ├── <RecentRunsCard>
│   │   └── <MarketHeatmapCard>
│   ├── <ChatPage>
│   │   ├── <ChatStream>              # ⭐ SSE 串流核心元件
│   │   │   ├── <MessageList>
│   │   │   │   ├── <UserMessage>
│   │   │   │   ├── <AssistantMessage>  # markdown
│   │   │   │   ├── <ToolCallCard>     # 折疊式 tool call 視覺
│   │   │   │   └── <ToolResultCard>
│   │   │   └── <ThinkingIndicator>
│   │   ├── <Composer>                # 輸入框 + skill picker
│   │   └── <ContextSidebar>          # session metadata、相關 skill
│   ├── <SwarmDagPage>
│   │   └── <DagViewer>               # ReactFlow 視覺化節點狀態
│   ├── <BacktestPage>
│   │   ├── <StrategyForm>
│   │   └── <BacktestResultView>
│   │       ├── <EquityChart>         # Recharts
│   │       ├── <DrawdownChart>
│   │       ├── <MetricsTable>
│   │       └── <TradeLog>
│   ├── <PaperPage>
│   │   ├── <OrderForm>               # react-hook-form + zod
│   │   │   └── <ConfirmDialog>       # ⚠️ 強制人工確認
│   │   ├── <PositionsTable>
│   │   └── <OrdersTable>
│   ├── <SymbolPage>
│   │   ├── <CandlestickChart>        # KLineCharts（內建 KDJ/MACD/BOLL/SAR/OBV）
│   │   ├── <ChipPanel>               # 三大法人 / 融資融券
│   │   ├── <FundamentalPanel>
│   │   └── <RelatedNewsPanel>
│   └── <SkillEditor>
│       └── <YamlEditor>              # Monaco
└── <Toaster>                          # sonner
```

---

## 4. 狀態管理（Zustand stores）

```ts
useSessionStore     // 當前 session id、訊息列表、串流暫存 token
useRunStore         // 執行中 runs map、cancel / retry 動作
usePaperStore       // 即時部位、委託、權益（WebSocket / SSE 推送同步）
useMarketStore      // 訂閱中的即時報價（Shioaji 行情）
useSettingsStore    // 主題、語言、API Key、合規同意旗標
useAuditStore       // 管理員稽核視圖
```

> **規則**：API 取回的「伺服器資料」一律放 TanStack Query；只有「UI 暫態」與「跨頁共享暫存」放 Zustand。避免兩邊複製造成不一致。

---

## 5. API client（`web/src/lib/api/`）

```ts
// 1. REST → TanStack Query
const { data } = useQuery({
  queryKey: ['paper', 'positions'],
  queryFn: () => api.paper.positions(),
  staleTime: 5_000,
});

// 2. SSE → 自寫 hook（包 EventSource）
useRunStream(runId, {
  onToken: (text) => useSessionStore.getState().appendToken(text),
  onToolCall: (call) => useSessionStore.getState().pushToolCall(call),
  onDone: () => qc.invalidateQueries({ queryKey: ['runs', runId] }),
});

// 3. Mutations（下單）→ 強制兩階段
const submit = useMutation({
  mutationFn: api.paper.submitOrder,
  onSuccess: (order) => openConfirmDialog(order),  // 不直接送出
});
```

---

## 6. 圖表方案分工

採「華語金融最對味」組合（經 2026/04 主流套件評比），總 bundle ≈ 450KB gzip：

| 圖表類型 | 函式庫 | Bundle | License | 用途 / 備註 |
|---|---|---|---|---|
| **K 線（OHLC + MA / KDJ / MACD / BOLL / SAR / OBV）** | **KLineCharts** | ~40KB | Apache 2.0 | 個股頁主圖、回測 K 線；**內建台股交易者熟悉的所有技術指標**，省 1-2 週實作；華語金融社群活躍 |
| **K 線型態 overlay（VCP / 杯柄 / 旗形標註）** | KLineCharts overlay API | — | — | 自訂 detector 結果 → overlay 線段 / 區塊 |
| **權益曲線、回撤瀑布、月報酬曲線** | **shadcn/ui Charts**（= Recharts wrapper） | ~95KB | MIT | Dashboard / 回測結果；與既有 shadcn 風格 100% 一致 |
| **三大法人柱狀、籌碼分點 BarChart** | shadcn/ui Charts (Recharts BarChart) | （同上） | MIT | 個股頁籌碼面 |
| **KPI 卡片 / 迷你 sparkline / BarList / TrackerBlock** | **Tremor** | ~80KB | Apache 2.0 | Dashboard KPI、產業強弱條、Risk Gate 5/5 指示燈；Vercel 收購、財務儀表板專用 |
| **Swarm DAG 視覺** | **React Flow / XYFlow** | ~120KB | MIT | Swarm 執行樹、節點拖拉 / minimap 全內建 |
| **月報酬熱力圖（年 × 月 格子）** | **ApexCharts heatmap** | ~115KB | MIT | 回測結果月度報酬視覺；ApexCharts 僅做 heatmap 一個 chart type，避免引入全部 |
| **產業 7×7 強弱熱力（Dashboard 盤中熱點）** | 自寫 SVG + d3-scale | ~10KB | — | 客製需求高、套件 overkill；50 行 SVG 即可 |

**選型理由**：
- KLineCharts vs TradingView lightweight-charts：兩者 bundle 接近（40KB vs 35KB），但 KLineCharts **內建 KDJ / MACD / BOLL / SAR / OBV / VOL / RSI / WR / MTM / EMV / VR 等 20+ 技術指標**；lightweight-charts 需 plugin 自寫（每個 ~150 行）。台股交易者習慣 KDJ + MACD + BOLL 三件套，KLineCharts 直接配齊。
- shadcn/ui Charts：與整套 shadcn/ui 設計系統零摩擦整合，色票直接吃 design tokens（§10）。
- Tremor：Vercel 親兒子（2024 收購），35+ 元件含 BarList / Tracker / Callout 等 Recharts 沒有的 financial dashboard 專用元件。
- React Flow：Swarm DAG 場景的事實標準（30k+ stars），無懸念。
- ApexCharts heatmap：只取 `ApexCharts.HeatMap` 一個 chart type，tree-shake 後實際 ~50KB。
- 自寫 SVG 熱力：產業 7×7 / 9×9 格子塗色，套 `d3-scale-chromatic` 算 colorScale，自寫 ~50 行比引入第二個 chart lib 乾淨。

**主題色一致性**：所有套件主題色透過 `web/src/lib/chartTheme.ts` 統一注入（讀 §10 design tokens），確保紅漲綠跌、品牌色、明暗模式同步切換。

**禁用 / 不採**：
- ❌ Apache ECharts（330KB 太大、API 非 React-first）
- ❌ Nivo（150-300KB、SSR 友善但 bundle 大）
- ❌ visx（學習曲線太陡，省下的時間不值得）
- ❌ MUI X Charts（Pro 版收費、與 shadcn 風格衝突）
- ❌ TradingView Advanced Charts（免費但需申請、有商標限制）

---

## 7. 主題、字型、i18n

- **主題**：明暗雙模式（shadcn Tailwind tokens），預設 system；圖表色票對齊（紅漲綠跌，**台股慣例**）。
- **字型**：UI 用 `Inter`；中文回退 `Noto Sans TC`；數字等寬用 `JetBrains Mono`。
- **語系**：預設 zh-TW，所有金融術語統一台股用語（如「漲跌停」非「涨跌停」、「除權息」「融資融券」「三大法人」）；保留 en 切換為 future。
- **千分位 / 貨幣**：`Intl.NumberFormat('zh-TW', { style: 'currency', currency: 'TWD' })`。

---

## 8. 合規 UI 約束

- 全站底部固定免責聲明，**不可關閉**：「本系統內容僅供研究參考，不構成任何投資建議或要約。」
- 個股頁上方旗標：若 universe 標記為「處置 / 警示 / 全額交割」→ 顯眼黃 / 紅 banner。
- `<OrderForm>` 送出前**必跳 `<ConfirmDialog>`**，要求使用者勾選「我已閱讀風險警示」並輸入下單張數二次確認；DOM 端不可被自動化點擊（檢查 `isTrusted`）。
- 首次啟動彈窗：自我提醒「本系統僅供個人研究，不構成投資建議；下單為模擬。」一次點掉即可，存於 `useSettingsStore` 的 `disclaimer.acceptedAt`（無 PDPA / ToS 框架，個人專案）。

---

## 9. 前端目錄結構

```
web/
├── package.json                # vite, react, tailwind, shadcn ...
├── vite.config.ts
├── tailwind.config.ts
├── components.json             # shadcn 設定
├── public/
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── routes.tsx              # React Router v7 routes
    ├── lib/
    │   ├── api/                # REST client + SSE hooks
    │   │   ├── client.ts
    │   │   ├── runs.ts
    │   │   ├── paper.ts
    │   │   ├── market.ts
    │   │   └── useRunStream.ts
    │   ├── format.ts           # 千分位 / 漲跌色 / 百分比
    │   └── i18n.ts
    ├── stores/                 # Zustand
    │   ├── session.ts
    │   ├── run.ts
    │   ├── paper.ts
    │   └── settings.ts
    ├── components/
    │   ├── ui/                 # shadcn 元件（button, dialog, table, ...）
    │   ├── layout/
    │   ├── chat/               # ChatStream, MessageList, ToolCallCard
    │   ├── swarm/              # DagViewer
    │   ├── backtest/
    │   ├── paper/
    │   ├── market/             # CandlestickChart, ChipPanel
    │   └── shared/             # DisclaimerFooter, ConfirmDialog
    ├── pages/                  # Route-level 頁面
    ├── hooks/
    ├── locales/
    │   ├── zh-TW.json
    │   └── en.json
    └── styles/
        └── globals.css
```

---

## 10. Design Tokens（設計變數）

採用 Tailwind v4 + CSS variables，所有顏色 / 間距 / 圓角 / 陰影 / 字型集中在 `web/src/styles/tokens.css`，明暗模式雙套。

### 10.1 色彩系統（語意色 + 台股配色）

```css
/* 中性灰階（明亮模式） */
--gray-0:  #ffffff;  --gray-1:  #f9fafb;  --gray-2:  #f3f4f6;
--gray-3:  #e5e7eb;  --gray-4:  #d1d5db;  --gray-5:  #9ca3af;
--gray-6:  #6b7280;  --gray-7:  #4b5563;  --gray-8:  #1f2937;  --gray-9:  #111827;

/* 品牌色（沉穩深藍，避開金融常見綠 / 紅以保留給漲跌） */
--brand-50:  #eef4ff;  --brand-500: #3b5bdb;  --brand-700: #2c3e9b;

/* 台股漲跌（嚴格遵循台股慣例：紅漲 / 綠跌） */
--up-bg:     #fef2f2;  --up-fg:     #dc2626;  --up-strong: #b91c1c;  /* 紅 */
--down-bg:   #ecfdf5;  --down-fg:   #059669;  --down-strong: #047857; /* 綠 */
--flat-fg:   #6b7280;                                                  /* 平盤灰 */

/* 語意狀態 */
--info:      #0ea5e9;  --warn:    #f59e0b;  --danger: #ef4444;  --success: #10b981;

/* Risk-Off / 處置股 高警示 */
--risk-off-bg: #fef3c7;  --risk-off-fg: #92400e;   /* 黃底深棕 */
--halted-bg:   #fee2e2;  --halted-fg:   #991b1b;   /* 紅底深紅 */

/* 圖表色票（K 線 / 量柱 / 線圖；對齊台股慣例） */
--chart-up:        var(--up-fg);
--chart-down:      var(--down-fg);
--chart-volume-up: rgba(220, 38, 38, 0.55);
--chart-volume-dn: rgba(5, 150, 105, 0.55);
--chart-ma-5:      #f59e0b;
--chart-ma-20:     #3b82f6;
--chart-ma-60:     #a855f7;
--chart-bb:        rgba(107, 114, 128, 0.5);
```

> **暗色模式**：所有 `--gray-N` 反轉、漲跌色保持鮮明（`--up-fg: #f87171`、`--down-fg: #34d399`），背景採 `#0b0f17` 偏冷黑。

### 10.2 字型 Scale（zh-TW 為主）

```
Display     32 / 40    Inter 700 + Noto Sans TC 700      頁面主標
H1          24 / 32    Inter 600 + Noto Sans TC 600      區塊主標
H2          20 / 28    600                               卡片標題
H3          16 / 24    600                               小區塊標
Body        14 / 22    400                               一般內文
Body-sm     13 / 20    400                               輔助說明
Caption     12 / 16    400                               表格頁尾、tooltip
Code        13 / 20    JetBrains Mono                    代碼塊
Number-lg   24 / 32    JetBrains Mono 600 tabular-nums   主要數字（股價 / P&L）
Number      14 / 22    JetBrains Mono 500 tabular-nums   表格數字
```

> **數字一律 `font-variant-numeric: tabular-nums`**，避免表格數字位數不齊。

### 10.3 間距 / 圓角 / 陰影

```
spacing:  4 / 8 / 12 / 16 / 20 / 24 / 32 / 48 / 64       (基礎 4 倍率)
radius:   sm 4   md 6   lg 8   xl 12   2xl 16   pill 999
shadow:   sm 0 1px 2px rgba(0,0,0,.05)
          md 0 4px 6px rgba(0,0,0,.07), 0 2px 4px rgba(0,0,0,.06)
          lg 0 10px 15px rgba(0,0,0,.10), 0 4px 6px rgba(0,0,0,.05)
          glow-up   0 0 0 3px rgba(220,38,38,.18)
          glow-down 0 0 0 3px rgba(5,150,105,.18)
```

### 10.4 Z-index 層級

```
base 0   sticky 10   header 20   dropdown 30   overlay 40
modal 50   toast 60   tooltip 70   confirm-dialog 80
```

---

## 11. Tailwind Theme 設定要點（`tailwind.config.ts`）

- 啟用 `darkMode: 'class'`，由 `useSettingsStore` 切換 `<html class="dark">`
- 自訂 plugin：`tw-up` / `tw-down` 工具類，自動套漲跌色 + tabular-nums
- 啟用 `@tailwindcss/forms` + `@tailwindcss/typography`
- `screens`：`sm: 640 / md: 768 / lg: 1024 / xl: 1280 / 2xl: 1536 / 3xl: 1920`（多螢幕交易員 1920+ 友善）

---

## 12. shadcn/ui 元件變體與使用準則

| 元件 | 變體 / 規範 | 使用場景 |
|---|---|---|
| **Button** | `default / destructive / outline / ghost / link` + `size: sm/md/lg/icon` | `destructive` 專供下單 / 刪除；其餘 `default` |
| **Card** | 基礎 + `Card.Header / Title / Description / Content / Footer` | 全站資訊卡片 |
| **Dialog** | `Dialog` + 客製化 `<ConfirmDialog>` 強制兩階段 | 下單、刪除 session、清空 watchlist |
| **Drawer** | 桌面右側 / 手機底部 | 個股詳情側拉、設定面板 |
| **Sheet** | 抽屜式設定 | Settings 子頁、Skill editor |
| **Tabs** | `pills` / `underline` 兩種 | 個股頁切換籌碼/技術/基本面 |
| **Table** | + TanStack Table | 持倉、委託、回測明細 |
| **Form** | react-hook-form + zod | 下單表單、設定表單 |
| **Toast (sonner)** | `success / error / warning / info / loading` | tool 結果通知、SSE 中斷提示 |
| **Tooltip** | hover 100ms / focus 即時 | 縮寫術語、漲跌色說明 |
| **Popover** | + `Command` (cmdk) | 標的快速搜尋（⌘K） |
| **Badge** | `default / secondary / success / warning / danger` | 處置/警示/Risk-Off 旗標 |
| **Skeleton** | 圓角配 `--radius-md` | 等待 SSE 第一個 token、API loading |
| **Alert** | `default / warning / destructive` | 免責聲明、Risk-Off 公告 |
| **ScrollArea** | 自訂 scrollbar | 訊息區、長表格 |

**禁用清單**（為避免 UI 失控）：
- ❌ 自製 modal — 一律用 `Dialog`
- ❌ 原生 `<select>` — 用 shadcn `Select`
- ❌ 原生 `<table>` — 用 `Table` + TanStack Table
- ❌ 任何 `position: absolute` 浮層 — 用 `Popover` / `Tooltip`

---

## 13. 互動狀態規格（Loading / Empty / Error / Disabled）

每個資料展示元件**必須實作 5 種狀態**：

| 狀態 | 視覺 | 範例 |
|---|---|---|
| **Loading** | Skeleton（與最終佈局同尺寸）+ 不顯示「Loading...」字樣 | 持倉表三行 skeleton |
| **Empty** | 灰階 illustration（lucide icon）+ 標題 + 一句話 + CTA 按鈕 | 「目前無持倉，去 Watchlist 找標的」 |
| **Error** | 紅色 Alert + 重試按鈕 + 「複製錯誤碼」 | API 503 顯示錯誤碼 + retry |
| **Partial** | 部分資料 + 灰色「資料延遲」標示 | FinMind 籌碼資料延遲 |
| **Disabled** | 透明度 60% + cursor not-allowed + tooltip 說明原因 | Risk-Off 期間下單按鈕禁用 |

**Streaming 特殊狀態**：
- SSE 第一個 token 到達前 → `<ThinkingIndicator>`（脈動點 + 「分析中...」）
- token 串流中 → 文字游標 `▌`（每 500ms 閃）
- tool_call 進行中 → tool 卡片 spinning + 已過時間
- SSE 中斷 → toast 警告 + 「重連」按鈕

---

## 14. 動畫與微互動

- **基準時長**：fast 120ms / base 200ms / slow 320ms
- **緩動**：`cubic-bezier(0.16, 1, 0.3, 1)`（ease-out 為主，不用 linear）
- **進入動畫**：toast / dialog / drawer 用 `slide + fade`；卡片用 `fade + scale 0.98 → 1`
- **數字動畫**：股價 / P&L 變動時 `framer-motion` 計數動畫 200ms；漲為紅閃、跌為綠閃 600ms
- **K 線即時更新**：KLineCharts 內建增量更新（`updateData()`），禁用 `<motion>` 包裹
- **禁忌**：
  - ❌ 任何 > 400ms 的動畫
  - ❌ 持續性動畫（loading bar 除外）
  - ❌ 滾動劫持（保持 native scroll）

---

## 15. 響應式斷點與版面

| 斷點 | 對象 | 版面策略 |
|---|---|---|
| `< 640` (mobile) | 手機（**MVP 不優先**） | Sidebar → 底部 tab；表格→卡片堆疊 |
| `640-1024` (tablet) | iPad | Sidebar 收成 icon-only；3 欄變 2 欄 |
| `1024-1536` (laptop) | 主要使用情境 | 側邊欄 240px + 主區流式 |
| `1536-1920` (desktop) | 多視窗交易員 | + 右側 context drawer 320px |
| `> 1920` (ultra-wide) | 雙螢幕 | 主區最大 1440 置中，兩側留白做面板 |

> **MVP 鎖定 1280×800 以上**，手機 / 平板 P3 後再優化。

---

## 16. 無障礙（WCAG 2.1 AA 基線）

- **對比度**：純文字 ≥ 4.5:1；漲跌色（紅綠）對比 ≥ 3:1（**色弱者另以箭頭 ▲▼ 與 +/- 符號雙重編碼**）
- **鍵盤導覽**：所有互動元素 Tab 可達；focus ring 用 `--brand-500` 2px 外框，禁止 `outline: none`
- **快捷鍵**：
  - `⌘K` 全域搜尋（cmdk）
  - `⌘Enter` Composer 送出
  - `⌘\` 切換 Sidebar
  - `g h` Dashboard、`g c` Chat、`g p` Paper、`g b` Backtest（Vim 風）
  - `?` 顯示快捷鍵清單
- **ARIA**：
  - SSE 訊息區用 `aria-live="polite"`
  - 下單確認 dialog 用 `role="alertdialog"`
  - 處置/Risk-Off banner 用 `role="status"` + 適當 `aria-label`
- **Reduced motion**：`@media (prefers-reduced-motion)` 關閉所有非必要動畫
- **i18n**：`<html lang="zh-Hant-TW">`；數字 / 日期統一 `Intl` API

---

## 17. Wireframe 圖庫（全 18 個頁面）

### 17.A. Layout 共用骨架

```
┌──────────────────────────────────────────────────────────────────┐
│ TopBar  [⌘K 搜尋]                       [Risk: 🟢On] [👤 user]   │ 56px
├──────┬───────────────────────────────────────────────────────────┤
│      │                                                           │
│ Side │                  主內容區                                  │
│ bar  │                  (max-w-1440 置中)                         │
│ 240  │                                                           │
│ px   │                                                           │
│      │                                                           │
├──────┴───────────────────────────────────────────────────────────┤
│ ⚠ 本系統內容僅供研究參考，不構成任何投資建議。                    │ 40px
└──────────────────────────────────────────────────────────────────┘
Sidebar：Dashboard / Chat / Swarm / Backtest / Paper / Market / Skills /
        Memory / Sessions / Settings / (Audit, admin)
```

### 17.B. Dashboard `/`

```
┌─ 風險面板 ─────────────┬─ 帳戶總覽 ──────────┬─ 今日 PnL ────────┐
│ 🟢 Risk-On (5/5)      │ 模擬資金: 1,000,000 │ +12,400  +1.24%   │
│ 加權: 17,890 (+0.4%)  │ 持倉: 4 / 6         │ 已實現: +8,200    │
│ VIX: 18.2  USDTWD:    │ 曝險: 64%           │ 未實現: +4,200    │
└────────────────────────┴─────────────────────┴────────────────────┘
┌─ 權益曲線（30D） ────────────────────────┬─ 今日待辦 ─────────────┐
│ ╭─╮              ╭──╮                  │ 🟢 Phase 2B 完成        │
│ ╱   ╲╱╲     ╭───╯                      │ 🟡 3 檔達 score ≥ 65    │
│       ╲────╯                           │ → 進 Phase 3 確認       │
│  Sharpe: 1.82  MDD: -3.4%              │ ⏰ 09:30 Risk Gate     │
└──────────────────────────────────────────┴────────────────────────┘
┌─ Watchlist Top 5 ────────────────────────────────────────────────┐
│ 代號  名稱      score  漲跌    籌碼  催化劑      動作             │
│ 2330  台積電    78  ▲+1.2%   外資+  目標價↑    [→ 詳情] [+ Phase 3]│
│ 2454  聯發科    72  ▲+0.8%   投信+  營收新高    [→ 詳情]          │
│ ...                                                              │
└──────────────────────────────────────────────────────────────────┘
┌─ 近期 Run ───────────────────┬─ 產業熱度（5D） ────────────────┐
│ 投資委員會 · 2330 · 5 分前    │ AI伺服器 +5.2%  ████████        │
│ 月營收掃描 · 02/05            │ 重電    +3.1%  █████            │
│ 回測 0050 雙均線 · 1 小時前    │ 軍工    +2.8%  ████             │
└──────────────────────────────┴──────────────────────────────────┘
```

### 17.C. Chat `/chat` `/chat/:sessionId`

```
┌──────────┬────────────────────────────────────────┬──────────────┐
│ Sessions │ ┌─ Session Title ─────────────────┐ ⋮ │ Context      │
│ ────     │ │ 2330 籌碼分析                   │   │ ────         │
│ • 今日   │ └─────────────────────────────────┘   │ 標的: 2330   │
│ 2330籌碼 │                                       │ 進場價: 980  │
│ 0050回測 │ 👤 幫我分析 2330 最近一個月的籌碼面     │ ATR: 18.4    │
│ ─        │                                       │              │
│ • 昨日   │ 🤖 我會從以下幾個面向分析...           │ 相關 Skill   │
│ AI 選股  │   ▌                                  │ • chip/three │
│ ...      │ ┌─ Tool: chip_data_tool ───────┐     │ • chip/margin│
│          │ │ ⚙ 分析 2330 30 日籌碼  (1.2s)│     │              │
│ + 新增   │ └────────────────────────────────┘     │ Memory 命中  │
│          │   ✓ 完成                              │ "偏好高股息" │
│          │ 結果分析：外資 5 日累計買超 1.2 萬張...│              │
│          │                                       │              │
│          │ ┌──────────────────────────────────┐   │              │
│          │ │ 輸入訊息...        [📎][🛠][送出]│   │              │
│          │ └──────────────────────────────────┘   │              │
└──────────┴────────────────────────────────────────┴──────────────┘
```

### 17.D. Swarm 入口 `/swarm`

```
┌─ 預設 Swarm（10 組）─────────────────────────────────────────────┐
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────┐  │
│ │ 投資委員會    │ │ 當沖機會掃描  │ │ 籌碼分析團    │ │ 季報研究 │  │
│ │ 多空辯論+PM   │ │ 盤中量價異常  │ │ 三大法人+借券 │ │ 財報季   │  │
│ │ [啟動 →]     │ │ [啟動 →]     │ │ [啟動 →]     │ │ [啟動 →] │  │
│ └──────────────┘ └──────────────┘ └──────────────┘ └─────────┘  │
│ ... 6 more cards ...                                              │
└──────────────────────────────────────────────────────────────────┘
[啟動] → Modal「輸入標的代號 / 策略主題」→ 跳 /swarm/{preset}/{runId}
```

### 17.E. Swarm DAG 視覺 `/swarm/:preset/:runId`

```
┌────────────────────────────────────────────────────────────────┐
│ 投資委員會 · 2330 · 執行中  [⏸ 暫停] [✕ 中止]                  │
├────────────────────────────────────────────────────────────────┤
│                  ┌──────────┐                                  │
│                  │ 資料蒐集 │ ✓                                │
│                  └────┬─────┘                                  │
│              ┌────────┴────────┐                                │
│         ┌────▼────┐       ┌────▼────┐                          │
│         │ 多方論點 │ ⚙    │ 空方論點 │ ✓                       │
│         │ (Sonnet)│      │ (Sonnet)│                          │
│         └────┬────┘       └────┬────┘                          │
│              └────────┬────────┘                                │
│                  ┌────▼────┐                                    │
│                  │ 風控審查 │ ⏳                                │
│                  └────┬────┘                                    │
│                  ┌────▼────┐                                    │
│                  │ PM 結論 │ ⊙                                  │
│                  └─────────┘                                    │
├────────────────────────────────────────────────────────────────┤
│ 節點輸出（點選節點顯示）                                         │
│ ─────────────────────────                                      │
│ [多方論點] 完成 (12.4s, 1,820 tokens)                          │
│ 「2330 第三季毛利率回升至 53.8%...」                            │
└────────────────────────────────────────────────────────────────┘
```

### 17.F. Backtest `/backtest`

```
┌─ 新建回測 ──────────────────────┬─ 歷史 Job ─────────────────┐
│ 策略: [tw_momentum_swing  ▼]   │ #142 0050 雙均線  2D 前 ✓  │
│ 標的: [TWSE Top 200       ▼]   │ #141 momentum_swing 2D ✓  │
│ 期間: [2020-01] ~ [2024-12]    │ #140 vcp_breakout  3D ✗   │
│ 初始資金: [1,000,000]          │ ...                        │
│ 參數                            │                            │
│  ATR 倍數停損: [2.0    ]       │                            │
│  T1 出場 %:    [50     ]       │                            │
│  Chandelier:   [3.0×ATR]       │                            │
│ ☐ 啟用 Walk-Forward             │                            │
│ ☐ 啟用 Optuna 最佳化            │                            │
│ [預估時間: 2 分 30 秒] [▶ 開始]│                            │
└─────────────────────────────────┴────────────────────────────┘
```

### 17.G. Backtest Result `/backtest/:jobId`

```
┌─ 摘要 ──────────────────────────────────────────────────────────┐
│ Sharpe 1.82  Sortino 2.14  Calmar 6.4  MDD -8.2%               │
│ 勝率 64.2%  PF 2.42  期望值 +6.4%  最大連敗 4                   │
│ 樣本內 / 外 Sharpe 落差: 12% ✓                                  │
└─────────────────────────────────────────────────────────────────┘
┌─ 權益曲線 (vs TAIEX) ──────────────────────────────────────────┐
│ 1.6x ┤              ╭─                                         │
│ 1.4x ┤        ╭────╯                                           │
│ 1.2x ┤  ╭────╯ ────────── TAIEX                                │
│ 1.0x ┼──                                                        │
│      └──────────────────────────                                │
│        2020   2021   2022   2023   2024                         │
└─────────────────────────────────────────────────────────────────┘
[Tab: 回撤瀑布] [Tab: 月報酬熱力] [Tab: 交易明細] [Tab: 診斷]
```

### 17.H. Paper Trading `/paper`

```
┌─ 帳戶 ───────────────┬─ 風險閘 ──────┬─ 月度熔斷 ────────────┐
│ 權益: 1,012,400      │ 🟢 Risk-On    │ 月 PnL: +2.4%         │
│ 可用: 364,000        │ 5/5 通過      │ 距離熔斷 -8%: 安全     │
│ 曝險: 64%            │               │                       │
└──────────────────────┴───────────────┴────────────────────────┘
┌─ 持倉（4 / 6） ────────────────────────────────────────────────┐
│ 代號 名稱     張數 進場 現價  PnL%   停損 衛星 持有 動作         │
│ 2330 台積電   2  980 992  +1.22% 945 🟢   3D  [出 50%][全出]  │
│ 2454 聯發科   1  ...                                          │
└────────────────────────────────────────────────────────────────┘
┌─ 快速下單 ─────────────────────────────────────────────────────┐
│ 代號: [2330  ] 動作: [買入 ▼] 張數: [計算中... ] 價格: [市價]  │
│ ATR(14): 18.4  建議倉位 (Vol Targeting): 20 萬 (20%)            │
│ 停損: 945 (-3.6%)  T1 980→1039 (+6%)                           │
│ ☐ 我已閱讀風險警示          [→ 確認下單]                        │
└────────────────────────────────────────────────────────────────┘
```

### 17.I. 個股頁 `/market/:symbol`

```
┌─ 2330 台積電 ─────────────────────────────────────────────────┐
│ 992 ▲ +12 (+1.22%)   量 28,432 張   [+ 加入 watchlist]        │
│ 旗標：[score 78 🟢] [外資+] [投信+]  ※處置股 banner 在此       │
└────────────────────────────────────────────────────────────────┘
┌─ K 線（KLineCharts，內建 MA/KDJ/MACD/BOLL/SAR/OBV）────────────┐
│   🕯🕯🕯🕯🕯🕯🕯🕯🕯🕯🕯  + MA5 / 20 / 60 + 布林               │
│   ░░▓▓░░▓▓▓░░  量柱（紅漲綠跌）                               │
│ [日 K] [60 分] [15 分] [週] [月]                              │
└────────────────────────────────────────────────────────────────┘
[Tab: 籌碼面] [Tab: 基本面] [Tab: 技術指標] [Tab: 新聞] [Tab: 籌碼分點]

籌碼面 Tab：
┌─ 三大法人（30D） ─────┬─ 融資融券 ──────┬─ 借券 / 個股期 ──┐
│ 外資 +12,400          │ 融資 124k 張    │ 借券 8,200      │
│ 投信 +1,200           │ 融券 4.2k 張    │ 期 OI ↑15%      │
│ 自營 -340             │ ...             │                  │
└────────────────────────┴──────────────────┴──────────────────┘
```

### 17.J. Skills 列表 `/skills`

```
┌─ 篩選 ────────┬─ Skills（30 / 已啟用 28）─────────────────────┐
│ ☑ technical   │ 🛠 chip/three-major-investors  [編輯][禁用]    │
│ ☑ fundamental │ 🛠 chip/margin-short            [編輯][禁用]   │
│ ☑ chip        │ 🛠 chip/securities-lending      [編輯][禁用]   │
│ ☑ tw_specific │ 🛠 technical/ma-crossover       [編輯][禁用]   │
│ ☑ quant       │ ...                                            │
│ ☑ portfolio   │ + 新增 Skill                                   │
└───────────────┴────────────────────────────────────────────────┘
```

### 17.K. Skill Editor `/skills/:name`

```
┌─ 三大法人分析 ─ chip/three-major-investors ──────────────────┐
│ [✓ 儲存] [↺ 復原] [▶ 試跑] [📥 匯出]                         │
├───────────────────────────────────────────────────────────────┤
│ ┌── YAML frontmatter ──────────────────────────────────────┐ │
│ │ name: three-major-investors                              │ │
│ │ description: ...                                         │ │
│ └─────────────────────────────────────────────────────────-┘ │
│ ┌── Markdown 主文（Monaco 編輯器） ────────────────────────┐ │
│ │ # 三大法人分析                                            │ │
│ │ 用於分析外資 / 投信 / 自營商當日及近 N 日動向...           │ │
│ │ ...                                                      │ │
│ └──────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
[右側預覽] LLM 視角的 skill catalog 如何看到這個 skill
```

### 17.L. Memory `/memory`

```
┌─ 長期記憶（12 條）──────────────────────────[+ 新增] [🔍 搜尋]┐
│ ⭐ 偏好高股息 + 低本益比                       2026-04-20 [🗑]│
│ ⭐ 不交易 KY 股                                2026-03-15 [🗑]│
│ • 對 2330 / 2454 特別熟悉                      2026-04-12 [🗑]│
│ • 月薪 ~ 8 萬，可承受月度 -10% 波動            2026-02-08 [🗑]│
│ ...                                                          │
└──────────────────────────────────────────────────────────────┘
```

### 17.M. Sessions `/sessions`

```
┌─ 搜尋 [_______________________] [搜尋] [日期區間] [Preset]    ┐
├─ 結果（FTS5）─────────────────────────────────────────────────┤
│ 2026-04-25  投資委員會 · 2330  「外資 5 日累計買超...」        │
│ 2026-04-24  Chat · 籌碼分析     「主力分點集中度 32%...」      │
│ ...                                                            │
└────────────────────────────────────────────────────────────────┘
```

### 17.N. Settings `/settings`

```
[Tab: 一般] [Tab: API Keys] [Tab: Shioaji] [Tab: FinMind]
[Tab: 主題與語系] [Tab: 合規] [Tab: 危險區]

一般：使用者名稱、預設 LLM 模型、預設 swarm preset
API Keys：Anthropic API Key（masked）、OpenAI（fallback）
Shioaji：api_key / secret_key（masked）+ 連線測試 + 模擬倉重置
FinMind：token、贊助會員旗標、剩餘額度顯示
主題：明 / 暗 / 跟隨系統、字級
合規（個人版）：免責聲明顯示偏好、稽核日誌路徑（90 天 hot）
危險區：清空所有 sessions、重置模擬部位（雙重確認）
```

### 17.O. Audit `/audit`（管理員）

```
┌─ 日期 [2026-04-26 ▼] 類型 [全部 ▼] [📥 下載 JSONL]            ┐
├─ 稽核日誌 ─────────────────────────────────────────────────────┤
│ 14:32:11 prompt       run_id=r_8fa1  「分析 2330 籌碼面」      │
│ 14:32:13 tool_call    chip_data_tool   {symbol: 2330, days:30}│
│ 14:32:14 tool_result  ok=true  elapsed=312ms                  │
│ 14:33:02 order        2330 buy 2 張 @ 980  status=pending     │
│ 14:33:05 order        2330 buy 2 張 @ 980  status=filled      │
│ ...                                                            │
└────────────────────────────────────────────────────────────────┘
```

### 17.P. Orders / Positions / Equity（Paper 子頁，列表為主）

- `/paper/orders`：可篩選日期 / 狀態 / 標的；欄位 `id, ts, symbol, side, qty, price, status, day_trade`
- `/paper/positions`：與 Dashboard 同元件，顯示更多欄位（成本、PnL、持有日數、距停損 %、距 T1 %）
- `/paper/equity`：純粹 EquityChart 全螢幕 + 月報酬熱力圖

### 17.Q. 決策審核 `/decisions`(v3 新增)

LLM Decider 產生的待 confirm 決策佇列。對應 cheatsheet §6.7 模式 A。

```
┌─ 待 confirm 決策 (3) ──────────────────────────────────┬─ Filter ────┐
│ ┌────────────────────────────────────────────────────┐ │ Status:     │
│ │ 2330 台積電    [enter]  conf 0.83   pending        │ │ ☑ pending   │
│ │ Score 78  Sizing 18% (LLM 提案 22% → 系統覆寫)      │ │ ☐ confirmed │
│ │ 「外資連 5 日買超...」  [展開 reasoning ▼]          │ │ ☐ rejected  │
│ │ 距 expire: 22:14         [✓ Confirm] [✗ Reject]     │ │ ☐ expired   │
│ ├────────────────────────────────────────────────────┤ │             │
│ │ 6488 環球晶    [reduce_size]  conf 0.71  pending    │ │ Today: 2/5  │
│ │ ...                                                  │ │ (auto limit) │
│ └────────────────────────────────────────────────────┘ │             │
├────────────────────────────────────────────────────────┴─────────────┤
│ 已展開:2330 reasoning                                                │
│ ─────────────────────────────────────────────────                  │
│ • Must-have 3/3 通過(評估證據)                                      │
│ • 加分項 6/8 通過                                                    │
│ • 引用 skill:technical/breakout, chip/three-major-investors         │
│ • LLM 標記風險:借券餘額近 5 日 +18%                                  │
│ • Tool calls(7):market_data_tool / chip_data_tool / ...             │
└──────────────────────────────────────────────────────────────────────┘
```

互動約束:
- `[✓ Confirm]` 必觸發 `<ConfirmDialog>`(輸入張數二次確認 + isTrusted 檢查,沿用 §13)
- `[✗ Reject]` 開啟拒絕原因 textarea,寫入 journal `kind=reject`
- `expire` 倒數結束自動移除 + 寫 journal `kind=expire`
- 自動模式啟用時(`OHMYSTOCK_AUTO_EXECUTE=true`)頂部顯示紅色 chip,熔斷 fallback 的決策仍會出現在此佇列

### 17.R. 復盤檢討 `/reviews/:id`(v3 新增)

對應 cheatsheet §15。

```
┌─ Review 2026-04 ───────────────────────────────────────────────────┐
│ 區間 2026-04-01 ~ 2026-04-30   ｜  交易筆數 23  ｜  PF 1.84       │
│ [Tab: 摘要] [Tab: 歸因] [Tab: 命中率時序] [Tab: 提案 (3)]            │
├────────────────────────────────────────────────────────────────────┤
│ 摘要(自然語言,LLM 產出)                                            │
│  本月勝率 56.5% 略低於前月 64%。主要拖累來自 VCP 型態(命中率僅      │
│  38%),建議調整量能門檻;Chandelier 衛星倉表現亮眼,期望值 +18.2%   │
│  ...                                                               │
├────────────────────────────────────────────────────────────────────┤
│ 歸因表格(節錄)                                                     │
│  thesis_held: 12 筆(prof +8.4%)                                   │
│  thesis_failed_but_profit: 3 筆(運氣)                             │
│  thesis_failed_loss: 5 筆(待改進)                                 │
│  stop_saved: 2 筆(良好)                                           │
│  time_stop_correct: 1 筆                                          │
│  time_stop_wrong: 0 筆                                            │
└────────────────────────────────────────────────────────────────────┘
```

### 17.S. 策略提案 `/proposals/:id`(v3 新增)

對應 cheatsheet §16。

```
┌─ Proposal: 2026-04-30-vcp-volume-threshold ───────────────────────┐
│ Status:[approved]   Target:cheatsheet §6.4   Created:LLM         │
│ ─────────────────────────────────────────────                    │
│ 改動描述                                                           │
│   VCP 型態量能門檻 1.5×→1.3×                                      │
│ 動機                                                               │
│   過去 30 筆 VCP 交易命中率僅 38%,放寬可預期 +12 檔/月            │
│ Diff                                                               │
│   - VCP 量能 ≥ 1.5× 5 日均量                                      │
│   + VCP 量能 ≥ 1.3× 5 日均量                                      │
├────────────────────────────────────────────────────────────────────┤
│ WFA 報告                                                          │
│   原版 OOS Sharpe 1.74  →  改後 1.91  (+9.8%) ✓                  │
│   樣本內外落差 22% < 30% ✓                                        │
│   Robust ±10%:衰減 28% < 50% ✓                                   │
│   黃金樣本:0050/2330/0056 全部不退化 ✓                            │
│                                                                    │
│ [✓ Merge to v3.1]   [✗ Reject]   [Re-validate]                    │
└────────────────────────────────────────────────────────────────────┘
```

`[✓ Merge to v3.1]` 必觸發 `<ConfirmDialog>`(權限保護:僅管理員角色)+ POST `/api/proposals/{id}/merge` 並注入 `confirm_token`。merge 完成後自動 bump cheatsheet 版本與 git tag。

---

## 18. 元件命名與檔案約定

- 元件檔名 `PascalCase.tsx`，hook `useXxx.ts`，常數 `UPPER_SNAKE`
- 元件依「**功能域**」分資料夾（`chat/`、`paper/`、`market/`），不依「型別」分（不要 `containers/` `presentational/`）
- 每個頁面元件**最多 200 行**，超過拆分子元件
- shadcn 元件保留 `ui/` 內，**禁止改 ui/ 檔案**；客製化用 wrapper（如 `PrimaryButton.tsx` 包 `Button`）
