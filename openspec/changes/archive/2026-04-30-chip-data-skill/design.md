## Context

Phase 1 路線圖明列「技術 / 籌碼面 Skills + 回測引擎」。技術指標（`ohmystock.indicators`）與回測引擎（`ohmystock.backtest`）已交付，籌碼面尚無任何模組。下游 Phase 2 screener 與 Phase 2B candidate snapshot 都依賴籌碼資料；不先把最常用的兩個籌碼端點落地，後續所有需要 chip 條件的 skill / strategy 都會卡住。

現有相關基礎建設：

- `ohmystock.data.finmind_client.FinMindClient` — thin httpx wrapper，已支援 `TaiwanStockPrice` dataset，使用 `Settings().finmind_token`。
- `ohmystock.data.market_data.get_kline` — cache-first / source-fallback 流程，定義了標準 envelope 與 error code 分類器（`_classify_exception`）。
- `ohmystock.data.cache` — `bars_daily` 表的 idempotent migration、`insert_bars` (`INSERT OR IGNORE`)、`select_bars`。
- `ohmystock_db_path` Settings — 同一支 SQLite DB 已被 `bars_daily`、`journal_entries`、`llm_costs` 共用。

`docs/tools-contracts.md` §3 已定義 `chip_data_tool` 介面（`get_three_major_investors / get_margin_short / get_securities_lending / get_top_brokers / get_stock_futures_oi` 五個方法）。本 change 只交付前兩個，其餘三個留給後續 change，因為它們需要不同的 FinMind dataset 與權限分級。

Stakeholders：solo dev (Mark) + 後續 Phase 2 screener、Phase 3 LLM Decider 的呼叫者。

## Goals / Non-Goals

**Goals:**

- 兩個純函式：`get_three_major_investors`、`get_margin_short`，介面與 `market_data.get_kline` 對稱（同樣 envelope / 同樣 error code / 同樣 cache-first）。
- 兩張新 SQLite cache 表，與 `bars_daily` 共存於同一個 DB；schema migration 由 `init_chip_schema(conn)` 提供，IF NOT EXISTS 安全。
- `FinMindClient` 新增兩個 dataset wrapper，與既有 `get_taiwan_stock_price` 同樣的錯誤行為。
- 純函式 + 依賴注入：FinMind client 與 SQLite connection 都可在測試中換掉，不需 monkeypatch httpx。
- 單元測試覆蓋：input validation、cache hit / partial miss / full miss、aggregator 正確性、HTTP 錯誤分類、reverse-import 防線。

**Non-Goals:**

- 不交付 `get_securities_lending` / `get_top_brokers` / `get_stock_futures_oi`（需另開 change，dataset 與 unit 不同）。
- 不註冊 `@register_tool`；本層僅是 skill 級的純函式，Tool 層整合留給 Phase 2 一併處理。
- 不做 screener 整合、不寫 FastAPI endpoint、不發 EventBus event。
- 不做跨日 backfill 排程；首次呼叫時 fetch，之後 cache 命中即可。
- 不做 retry / exponential backoff；單次失敗就回 envelope，呼叫端決定是否 retry。

## Decisions

### D1. 沿用 `market_data` 的 envelope 與 error code，而非另創一套

**Decision**: error code 限定 `INVALID_INPUT / DATA_UNAVAILABLE / RATE_LIMIT / UPSTREAM_ERROR / AUTH_FAILED`，分類器邏輯與 `market_data._classify_exception` 一致（lowercase substring match）。

**Why**: 下游 LLM Decider / screener 已經要學一套 envelope，再多一套只會徒增 prompt 複雜度。Solo dev 專案的 SSOT 原則 — 既有的就重用。

**Alternative**: 為 chip 自訂 `CHIP_PARTIAL` 等專用 code。**Rejected**：cache-first 的部分命中本來就不算錯（會自動補齊），不需要新 code。

### D2. Cache schema 兩張表，不共用一張寬表

**Decision**: `chip_three_major_daily` 與 `chip_margin_short_daily` 分開，各自 `(symbol, date)` PK。

**Why**:

- 兩個 dataset 在 FinMind 是分開兩個 endpoint、不同更新時間（三大法人 16:30、融資融券 17:00 後），分別 cache 才能各自命中各自的時間窗。
- 寬表會強迫每次寫一邊就要 NULL 另一邊的欄位，PK 衝突處理變複雜。
- 兩張窄表加起來大約 8–10 欄，比一張 14 欄寬表更直觀。

**Alternative**: 一張寬表 `chip_daily`。**Rejected**：見上。

### D3. `foreign_net` 等三大法人欄位用 **股** 存、回應時轉 **張**

**Decision**: cache 存 shares，公開函式回 `shares // 1000` 為張。

**Why**:

- FinMind `TaiwanStockInstitutionalInvestorsBuySell` 原始單位是股；存原值才能在未來想看股數時無損還原。
- `bars_daily.v` 已經存「張」（在 `finmind.py` adapter 做了 `// 1000`），這個 change 故意走相反路徑：cache 層保留最高解析度，轉換在 boundary 做 — 是更穩健的設計，也讓未來新增 `get_top_brokers`（會用到股級資料）時不必改 schema。
- 回應層回張，是因為 `tools-contracts.md` §3 與 cheatsheet 文檔都用張當單位，跟交易語境一致。

**Alternative**: cache 也存張。**Rejected**：unit conversion 一旦 lossy（除不盡）就回不去，未來會卡。

### D4. 融資融券單位用 **張** 存、不轉換

**Decision**: `chip_margin_short_daily.margin_balance` 等欄位直接存 FinMind 原值（張）。

**Why**: `TaiwanStockMarginPurchaseShortSale` 的原生單位本來就是張，不像三大法人是股。沒有 lossy conversion 的風險，也跟使用者語境一致。

### D5. `short_to_margin_ratio` 寫入時計算並儲存

**Decision**: 在 cache 寫入時就算 `short_balance / margin_balance * 100`，存進表；讀取時不重算。

**Why**:

- 簡化 read path，避免每次回應都做 ZeroDivision 防護。
- 單一公式 SSOT — 整個系統只有 cache writer 知道公式，未來改公式只改一處。
- ratio 是純衍生欄，不會有「源資料更新但 ratio 沒同步」的問題（INSERT OR IGNORE 不更新既有列）。

### D6. `aggregate_three_major` 為純函式、可獨立測試

**Decision**: 把「FinMind raw rows → 一日一列、三欄淨值」的彙總邏輯抽成 `aggregate_three_major(raw_rows) -> list[dict]`，與 cache I/O 分離。

**Why**: FinMind `TaiwanStockInstitutionalInvestorsBuySell` 一日一檔股票回 4 列（`Foreign_Investor`、`Foreign_Dealer_Self`、`Investment_Trust`、`Dealer_self`、`Dealer_Hedging`），需做欄位映射 + 加總。把這段邏輯做成純函式，測試只需丟 dict list，不必碰 SQLite 也不必碰 httpx。

`Foreign_Investor` 起頭包含 `Foreign_Investor` 與 `Foreign_Dealer_Self`（外資自營），都應計入外資；`Dealer_` 起頭包含 `Dealer_self` 與 `Dealer_Hedging`（自營商自行買賣 + 避險），合計為 prop_dealer_net。`Investment_Trust` 為投信。

### D7. 依賴注入用 `_conn` / `_client` underscore-prefixed kwargs

**Decision**: 公開函式 signature 是 `(symbol, days=30, end_date=None)`，但底下接受 `_conn=None, _client=None` 私有 kwargs 給測試用，與 `market_data.get_kline` 的 `_conn / _adapters` 同一個 pattern。

**Why**: 一致性 + 不污染公開介面 + 測試不必 monkeypatch module-level singleton。

### D8. 同一支 SQLite DB（`ohmystock_db_path`），不另開檔

**Decision**: chip cache 表加進現有 DB，靠 `init_chip_schema(conn)` 在首次使用時建表。

**Why**: solo dev 個人專案，多檔 DB 只增加備份 / 路徑管理負擔；既有 `bars_daily` / `journal_entries` 已共存證明這個模式可行。

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| FinMind dataset 欄位名稱（如 `name` 的具體枚舉）未來改變 | aggregator 為純函式 + 完整 unit test，FinMind 改名時只需改映射常數 + 補測試；不會把 cache 寫壞（INSERT OR IGNORE 跳過已有列） |
| 三大法人股數 → 張的 `// 1000` 截斷誤差累積 | 故意接受 — 張是顯示單位，1 張以下的尾數本來就無交易意義；cache 仍存原值，未來若需要可改回應層公式 |
| FinMind 贊助會員額度（6000 req/hr）被打爆 | cache-first 設計天然降載；單一 symbol 一日只可能呼叫 1 次（之後全 hit），10 個 symbol × 250 個交易日 = 2500 次 / 天上限，遠低於額度 |
| `short_to_margin_ratio` 公式未來想改（例如改成 `short_change / margin_change`）| 寫入時計算意味著歷史列無法回填新公式；接受此 trade-off — solo dev 專案不需要追溯式改寫，下次 fetch 時新列即用新公式 |
| 兩張新表未來變成「不可拆 schema」變大 | 兩張都是 append-only daily snapshot，schema 用 `ALTER TABLE ADD COLUMN` 加欄即可；無 migration 工具負擔 |
| Reverse-import (chip → api) 漸漸滲入 | 用 subprocess test 防線（同 backtest），CI 自動擋；違反時測試直接紅 |

## Migration Plan

無 schema 升級需求 — 兩張表都是新建，IF NOT EXISTS 安全，與既有 `bars_daily` / `journal_entries` 完全獨立。

部署：
1. `pip install -e .` 即生效（純 Python，無新 deps）。
2. 第一次呼叫任一 chip 函式時自動建表。
3. 無需手動跑 migration，無需停機，無需備份既有 DB。

回滾：刪除 `ohmystock/chip/` 目錄即可；既有 cache 表留在 DB 中無人讀寫，不影響其他功能。

## Open Questions

無關鍵阻塞。實作時若 FinMind 回傳格式與本文件假設不符（例如 `name` 欄位枚舉值不同），以實際回應為準調整 `aggregate_three_major` 的常數，並補測試案例。
