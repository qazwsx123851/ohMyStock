## Context

Phase 2 漏斗的入口是 universe — 沒有可交易股池，後續 Trend Template / Stage / chip / scoring 都沒有迭代對象。本系統已經有 `bars_daily`（K 線快取）+ `chip_three_major_daily` / `chip_margin_short_daily`（籌碼快取）兩座基礎，universe 是第三座 cache。

現況：
- 既有純函式套件慣例：`ohmystock.{data,chip,indicators,backtest}`，每個套件有自己的 `cache.py`（DDL + insert/select）+ skill 入口（標準 envelope）。
- FinMindClient 已是 thin wrapper（`_fetch_dataset` 共用），新增端點只要加一個 method。
- 反向依賴防線：`tests/test_*_reverse_import.py` 用 subprocess 確認 `ohmystock.<pkg>` 不會把 FastAPI / uvicorn / starlette 拉進 sys.modules。

## Goals / Non-Goals

**Goals:**

- 把 TW 全市場 symbol 池每日 snapshot 進 SQLite，以 `(asof_date, symbol)` 為 PK，方便歷史回放。
- 提供純函式 `screen_universe()` — 給定 universe + filters，回標準 envelope，candidates 按 symbol 升冪。
- 兩個 filter kind（`negative_filter` / `volume_filter`）只做欄位查詢 / cache 計算，不打外網。
- 沿用 `bars_daily` 算 NT$ ADV，不重抓 K 線（不允許 `volume_filter` 進入時 silent fetch — cache miss 直接回 `DATA_UNAVAILABLE`）。
- 反向依賴：`ohmystock.screener` 不得 import `ohmystock.api`。

**Non-Goals:**

- 不做 SEPA filter（Trend Template / Stage / VCP / RS percentile）— 留給後續 changes，這些都需要 indicator 組合 + 形態偵測。
- 不做 chip filter（雖然 chip cache 已存在，把 join 收斂到下一張票一起做 schema validation）。
- 不做 scoring（`sort_by` 本 change 只支援 `"symbol_asc"`）。
- 不做 `top200` universe — 需要 5d/20d 流動性歷史排名 + tie-break 策略，獨立 change。
- 不註冊 `@register_tool`（Tool 層留給 Phase 3）。
- 不做 `is_warning` / `is_disposal` / `is_fully_paid` 的真實旗標寫入 — `TaiwanStockInfo` 沒有，本 change 的旗標欄位先一律寫 `0`，由後續 change 串接 TWSE 警示公告 / OTC disposal 列表。`is_ky` 從 symbol 字尾 `KY` 推導。

## Decisions

### Decision 1: Universe snapshot 用「每日 PK」而非「current-only」

寫成 `(asof_date, symbol)` PK，而不是只存當下狀態。

**理由：**
- backtest engine 已經用日期當 PK（`bars_daily`）— 一致性。
- 未來歷史回測需要「2024-03-15 那天的可交易股池」，沒有歷史 snapshot 就回不了。
- 多一個欄位的儲存成本 vs. 之後重做整張 cache 的成本 — 前者明顯划算。

**Alternatives considered:**
- `current` 表 + `history` 表雙寫 — 過度工程，個人專案沒這麼多查詢模式。
- 只存當下 — 失去回放能力，違反 backtest 一致性。

### Decision 2: KY 旗標從 symbol 推導，不靠 FinMind 旗標

`is_ky` 在 `aggregate_universe_rows()` 寫入時用 `symbol.endswith("KY")` 判斷。

**理由：** FinMind `TaiwanStockInfo` 沒有 KY 旗標，但 KY 公司 symbol 慣例固定（`9105KY`、`9136KY`），推導零誤差且不需第二資料源。

**Alternatives considered:**
- 等補資料源 — 阻塞本 change。
- 維護白名單 — 易過時。

### Decision 3: 警示 / 處置 / 全額交割旗標本 change 寫 `0`，欄位先佔位

`is_warning` / `is_disposal` / `is_fully_paid` 在本 change 一律寫 `0`，schema 已有欄位等下一張票補資料源後 backfill。

**理由：**
- 拆票紀律 — 這幾個資料源（TWSE 警示公告 / OTC disposal CSV / 全額交割名單）各自要單獨 fetcher + 解析，混進本 change 會把它從「universe 持久化」吹成大票。
- 欄位先佔位避免後續加欄要 `ALTER TABLE`（SQLite 雖然支援 ADD COLUMN，但 schema migration 流程目前還沒做）。
- `negative_filter` 的 `exclude` 參數仍照 spec 接受這些 key，只是現階段 `is_warning` 永遠 0，filter 不會把任何 row 排掉 — 但 contract 已經定下，等資料源到位即生效。

**Alternatives considered:**
- 等資料源 — 阻塞本 change。
- 不加欄位 — 後續要 `ALTER TABLE`，比佔位麻煩。

### Decision 4: `volume_filter` cache miss 一律 `DATA_UNAVAILABLE`，不 silent fetch

`volume_filter.min_avg_dollar_volume_5d` 需要每檔最近 5 個交易日 `bars_daily.amount` — 若 cache 不足，本 change **不**呼叫 `get_kline()`，直接讓該 symbol 過篩失敗或整體回 `DATA_UNAVAILABLE`（依 `error_policy` 決定，預設 `skip_missing`）。

**理由：**
- screener 一次跑可能掃 2000 檔，silent fetch 會在 universe 第一次跑時打爆 FinMind quota。
- 預期上層排程（cron / scheduler）先跑 `prefetch_kline_universe()`（後續 change），screener 才跑。
- 兩種策略的 trade-off：`skip_missing`（cache miss symbol 過 filter 失敗）vs. `fail_fast`（整體回 `DATA_UNAVAILABLE`）— 預設 `skip_missing` 對日常排程合理（少數 symbol 缺資料不該全盤 abort），但要可切換。

**Alternatives considered:**
- Lazy fetch — 違反 quota 控制原則。
- 永遠 fail_fast — 對排程不友善。

### Decision 5: 公開 `screen_universe()` 回 envelope，filter 函式內部回 plain `list`

`filters.apply_negative_filter(rows, exclude)` 與 `filters.apply_volume_filter(rows, conn, min_adv, asof, error_policy)` 是 **內部** 純函式（回 list），envelope 只包在 `screen_universe()` 出口。

**理由：** 同 `chip` / `market_data` 模式 — 內部 helpers 不該扛 envelope 包裝開銷，envelope 是 boundary contract。

### Decision 6: `asof_date` 預設「今日 TPE」，週末 / 假日 fallback 取最近一個快取日

`asof_date=None` 時，先試今日 TPE，若 `universe_daily` 沒當天 row，往前找最近一個 `asof_date`，找不到回 `DATA_UNAVAILABLE`。Envelope 加 `data.asof_date_used` 欄位讓 caller 知道實際用哪一天。

**理由：** 週末 / 國定假日不會有新 universe，使用者在週六跑不該回空集合或炸錯。

**Alternatives considered:**
- 嚴格：當天沒 cache 直接 `DATA_UNAVAILABLE` — 對週末互動友善度差。

## Risks / Trade-offs

- **[Risk] 警示 / 處置旗標未實作，`negative_filter` 對應 key 在本 change 是 no-op。** → 在 docstring 與 spec 註明「stub flags wired in next change」，且測試覆蓋 `is_ky` 的真實行為，避免 contract 漂移。
- **[Risk] FinMind `TaiwanStockInfo` 一次拉全市場可能 ~3000 row，HTTP timeout / 資料解析時間 > 10s。** → 沿用 `FinMindClient._fetch_dataset` 既有 timeout 設定（30s），不為此 change 改 client 層；測試用 fixture mock 上百 row 的 payload。
- **[Risk] `volume_filter` 對 `bars_daily` cache 完整度敏感，初次部署會看到大量 `skip_missing`。** → 不是本 change 的問題，文檔註明依賴 prefetch；後續 change 補 `prefetch_kline_universe` 排程。
- **[Trade-off] `asof_date` fallback 機制讓週末「跑得起來」但結果是過時 snapshot。** → envelope 加 `data.asof_date_used` 欄位讓 caller 知道實際用哪一天。
- **[Risk] universe 旗標 backfill 會碰到歷史 row 的 `is_warning=0` 假陰性。** → 之後補資料源時，要在那張 change 補 backfill script + 文檔記載哪段日期前的旗標不可信。

## Migration Plan

不適用（首次落地，沒有現存資料要遷移）。

## Open Questions

- 是否要把 `industry` 細分（FinMind 給的 `industry_category` 約 30 大類）vs. 標準化成 `cheatsheet` §6.4 的「產業 RS 領先」用群組？— 留給 Trend Template change，本 change 直接存原值。
- 是否要在 `universe_daily` 多存 `listing_date` 以排除「上市未滿 6 個月」？— SEPA Trend Template 第 8 條會用到，但那條 filter 不在本 change，先不存欄位（後續加 ADD COLUMN 比一次寫過頭好）。
