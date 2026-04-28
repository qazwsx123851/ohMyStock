# 台股短線動能交易系統 — 各情境選股與交易邏輯速查 **v3.1**

> **版本**：v3.1 ｜ **更新日期**：2026-04-28 ｜ **前版**：v3.0（保留 git history）
> **用途**：四階段漏斗 + 盤中觸發 + 全域風險閘 + **LLM 閉環決策迴圈** + **Mark Minervini SEPA 框架** 的混合工作流
> **策略定位**：SEPA 風格動能交易（Stage 2 + Trend Template + VCP/Pivot Breakout），持有 **3-15 個交易日**（含 10 日時間停損）
> **決策優先序**：
>   - **硬性閘（系統強制）**：Risk-Off > 月度熔斷 > 連敗管理 > 持倉 / 同產業上限
>   - **交易執行（通過硬性閘後）**：停損 > 停利 / 出場 > 進場（**LLM Decider + Confirm Gate**） > 觀望
>
> **核心原則**：LLM 進場決策必須先通過全部硬性閘；Risk Gate 拒單 LLM 無法覆蓋。系統公式（Volatility Targeting / ATR 停損）與 LLM 提案取較保守者。

---

## ⚡ v1 → v2 Changelog（重大調整一覽）

| 類別 | v1 | v2 |
|---|---|---|
| 評分權重 | 技 40 + 籌 40 + 產 20 = 100 | **技 35 + 籌 45 + 產 10 + 情緒 10 = 100** |
| 籌碼面細項 | 外資/投信/主力/融資券/集保 | + **借券餘額** + **個股期 OI** + **主力分點集中度量化** |
| 消息情緒面 | 無 | **新增 10 分**（法人/重訊/搜尋熱度反向） |
| 停損 | 固定 -6% / 弱勢 -4% | **max(-6%, -2×ATR(14))** / 弱勢 -1.5×ATR |
| 停利 | T1 +6% 全出（PF 2.42） | **T1 +6% 出 50% + 衛星倉 Chandelier(3×ATR)** |
| 持倉檔數 | 最多 4 檔 | **4-6 檔，同產業最多 2 檔** |
| 進場條件 | 11 選 6 | **3 must-have + 8 選 4** |
| 風險閘 | 寬鬆（KD/5MA） | **Risk-Off 5 條件，任一觸發禁止新進場** |
| 排程 | 週五 + 每日收盤 | + **11:00 / 13:00 盤中** + **月初 1-10 日營收掃描** |
| 時間停損 | 無 | **7 日未達 +3% 倉位減半 / 10 日全出** |
| 月度熔斷 | 無 | **單月 -8% 全平 + 停止新進場至月底** |
| Position Sizing | 固定 % | **Volatility Targeting（個股 ATR 反向）** |
| 連敗管理 | 3 減半 / 5 暫停 | + **近 20 筆勝率 < 40% 暫停** |
| K 線型態庫 | 紅三兵/吞噬等基礎 | + **VCP / 杯柄 / 平台突破 / 旗形** |
| EMA20 進場 | 0~5% 強制 | **0~5% 正常 / 5~10% 倉位減半 / >10% 等回** |

---

## ⚡ v2 → v3 Changelog（閉環迴圈調整）

| 類別 | v2 | v3 |
|---|---|---|
| Phase 3 進場 | 使用者**手動**觸發 + 人腦判斷 | **LLM Decider 自動分析**（`entry_decision_team` swarm）→ Sizing/ATR 系統覆寫 → Risk Gate → **Confirm Gate（人工 confirm 預設 / 自動執行可切換）** |
| 進場決策紀錄 | `entry_thesis` 自然語言 + 數值欄位 | 新增 `llm_decision_id`、`llm_model`、`llm_confidence`、`cited_skills[]`、`tool_calls[]`、`auto_executed`、`human_confirmed_by/at` |
| 月底復盤 | 統計表（勝率 / PF / MDD） | **§15 LLM 復盤迴圈**：資料 → 歸因 → 聚合 → 批判 → 提案，產出 `reviews/` 報告 + `proposals/` 改動提案 |
| 策略優化 | 僅 Optuna 參數網格 + WFA | 新增 **§16 提案 → 驗證 → 合併** 工作流：LLM 出 proposal → WFA 驗證閘 → **人工 PR review** 才合併 cheatsheet（LLM 不可直接 commit） |
| 工作流階段 | Phase 0/1/1.5/2A/2B/3/4 | **+ Phase 5（月度復盤）** |
| 自動下單防線 | 防線 1-8（sim/live 切換） | **+ 防線 9（LLM 自動下單熔斷）**：單日筆數、單筆金額、confidence 閾值、sizing 偏離限制 |

---

## ⚡ v3.0 → v3.1 Changelog（Mark Minervini SEPA 框架引入）

> **動機**：v3.0 的選股漏斗（量化初篩 → 籌碼 → 技術 → 基本面）邏輯紮實，但**沒有完整的 Stage Analysis 框架、缺 Trend Template 8 條、RS 概念極弱（僅「近 5 日 RS > 大盤」）**。v3.1 引入 Mark Minervini SEPA（Specific Entry Point Analysis）三柱：**Trend Template + Stage 2 + VCP/Pivot Breakout**，並針對台股做本地化（無 IBD 商業 RS、漲跌停、成交額替代 $ADV、季報節奏 8/2 月）。

| 類別 | v3.0 | v3.1 |
|---|---|---|
| 全域風險閘 | 僅大盤層級（Risk-Off） | **+ §0.4 個股 Stage 4 一票否決**（MA50 < MA150 < MA200 且價跌破 MA50） |
| §2 第二層 量化初篩 | 站上 20MA + 量 + 漲幅前 20% | **改為 Trend Template 8 條全過**（價 > MA50 > MA150 > MA200；MA200 上升 ≥ 20 日；距 52W 高 ≤ 25%；距 52W 低 ≥ 30%；**RS Percentile ≥ 65**） |
| §2 第三層 籌碼確認 | 主力分點 / 個股期 / 借券 | **同 v3.0** + **Stage 2 確認**（價 > MA50 > MA150 > MA200 + MA200 ≥ 20 日上升） |
| §2 第四層 技術精選 | VCP / 杯柄 / 平台突破 + 量價 | **明確 Pivot Breakout 量價條件**（量 ≥ 1.4× 20DMA、Pivot+1~2% 內進場、Pivot+5% 不追） |
| §5 評分公式 | 技 35 + 籌 45 + 產 10 + 情 10 | **技 40 + 籌 25 + 基本面 25 + 情緒 10**（提升基本面權重，Minervini 重 EPS YoY ≥ 25%、營收 YoY ≥ 20%） |
| §6.3 must_have_check | 突破收陽 / 量 1.5× / RS > 大盤 | **改為 SEPA 三柱**：(a) Trend Template 8/8、(b) Stage 2、(c) VCP/杯柄/平台 + Pivot Breakout 量能（≥ 1.4× 20DMA） |
| §6.4 加分項 | 8 項偏籌碼 / 技術 | **改為 SEPA flavor**：EPS YoY ≥ 25%、營收 YoY ≥ 20%、RS Percentile ≥ 80、距 52W 高 ≤ 15%、VCP 收縮 ≥ 4 次、機構持股遞增、產業 RS 領先、新高+量爆 |
| §6.6 Sizing 公式 | Volatility Targeting | **不動**（Vol Targeting 在台股 ±10% 漲跌停下對極端波動股自帶保護；不採用 Minervini 1% Fixed-Risk） |
| §6.6 ATR 停損公式 | `max(price × 0.94, price - 2 × ATR)` | **不動**（既有 -6% 下限與 Minervini -6~7% 對齊，已預留漲跌停緩衝） |
| §9 K 線型態庫 | VCP / 杯柄 / 平台突破 + 經典 | **排序明確化**：VCP（最高優先）> 杯柄 > 平台突破 > 經典型態（降為輔助） |
| §12 黃金樣本 | 0050 / 2330 / 0056 | **+ 5–8 檔 2023–2024 已知 SEPA 強勢股**（2454/3231/3017 等中型成長） |
| **新概念** | — | **RS Percentile**（自建 IBD 式，台股 TWSE+OTC 流動股池，252 日加權，門檻 65）+ **Stage 1/2/3/4** + **Trend Template 8 條** |

> **未變動的 SSOT 項目**（依 CLAUDE.md §5）：§6.6 Volatility Targeting / ATR 停損公式、Risk-Off 觸發條件 5 項（市場層級）、Phase 5 五節點 DAG、Tools 21 項清單、§16 提案閘流程、Trade Journal schema 既有欄位（v3.1 僅追加 5 個 SEPA 欄位，詳 `llm-decision-schema.md`）。

---

## 0. 全域風險閘（Risk Gate）— 一票否決

### 0.1 Risk-Off 觸發條件（市場層級，任一即進入）
- 加權指數跌破 60MA **且** 60MA 走平 / 翻揚轉平
- 美股 SPY 過去 5 日 < -3% 且當日續跌
- VIX > 25 **或** 1 日漲幅 > 30%
- 台幣兌美元 1 日貶值 > 0.5%
- 外資台指期淨空單連 3 日創新高

### 0.2 Risk-Off 模式規則
- 🚫 禁止所有新進場（即使 score ≥ 65）
- 📉 既有持倉**停損價統一上移 2%**
- 🟢 出場 / 觀望 / 對沖（買 0050 反一短期避險）允許

### 0.3 月度熔斷
當月累積 P&L ≤ **-8%** → **強制全平 + 停止新進場至月底 + 強制復盤檢討**才可解鎖。

### 0.4 個股 Stage 4 一票否決（v3.1 新增 — SEPA 框架）

> **依 Mark Minervini / Stan Weinstein Stage Analysis：Stage 4 = 下跌期，機構持續派發。** Minervini 紀律：絕不在 Stage 4 進場（包括試圖撈底的「修復股」）。本系統若使用者想做 Stage 1→2 轉換的修復股，需另開 strategy（v3.1 不做）。

**Stage 4 判定**（**全部**符合即視為 Stage 4，**任一筆候選為 Stage 4 直接 hard reject，無論 Phase 2B final_score 多高、無論 LLM Decider 怎麼推薦**）：
- MA50 < MA150 < MA200（均線空頭排列）
- 收盤價 < MA50
- MA200 過去 20 個交易日不上升（持平或下降）

**判定時機**：Phase 2B 評分前的前置硬性過濾（與處置 / 警示 / 全額交割同層）。命中即寫 `kind=reject`、`reject_layer=pre_check`、`reject_reason=stage_4_individual` 進 trade journal。

> **設計意圖**：與 §0.1 市場層級 Risk-Off 互補。Risk-Off 擋的是大盤，§0.4 擋的是個股本身已壞。即使大盤 Risk-On，個股 Stage 4 仍 hard reject — Minervini 認為這是 SEPA 紀律的核心。

---

## 1. 任務情境與觸發時機總覽

| 階段 | 任務名稱 | 排程任務 ID | 觸發時機 | 執行方式 | 耗時 | 主要產出 |
|------|---------|------------|---------|---------|------|---------|
| **Phase 0** | 全域風險閘檢查 | `tw-risk-gate` | 每交易日 09:30 + 13:35 | 自動 | 1 分 | Risk-On / Risk-Off 旗標 |
| **Phase 1** | 週末強勢股篩選 | `tw-weekly-screening` | **週五 17:30**（v2 後移，等分點齊全） | 自動 | 15-30 分 | 10-15 檔候選 → watchlist |
| **Phase 1.5** | 月營收動能掃描 | `tw-revenue-scan` | **每月 1-10 日 19:00**（v2 新增） | 自動 | 10 分 | 月營收動能 watchlist |
| **Phase 2A** | 盤中強勢股掃描 | `tw-intraday-scan` | **11:00 + 13:00**（v2 新增） | 自動 | 3 分/次 | intraday-watch 標的 |
| **Phase 2B** | 收盤後觀察清單評分 | `tw-daily-watchlist` | 每交易日 17:30 | 自動 | 10-20 分 | watchlist 分數 + 信號 |
| **Phase 3** | 進場信號最終確認 | `tw-entry-confirmation` | Phase 2B 篩出 ≥ 65 後 | **LLM 自動決策 + 人工 confirm（預設）/ 自動執行（切換）** | 2-5 分 | 進場計畫 + LLM thesis + 人工確認結果 |
| **Phase 4** | 持倉檢視 + 出場 | 整合 Phase 2B | 每交易日收盤後 | 自動 | 5-10 分 | 停損/停利/論點失效決策 |
| **Phase 5** | 月度交易復盤 | `tw-monthly-review` | 月底自動 + 人工任意觸發 | **LLM 自動分析**（`post_trade_review_team` swarm） | 10-20 分 | 復盤報告（`reviews/`） + 策略改動提案（`proposals/`） |

> 額外風控觸發點：每筆出場後須更新 `consecutive_loss_tracker`、`recent_20_winrate`、`monthly_pnl_tracker`。

---

## 2. 【情境 1】Phase 1 — 週五 17:30：週末強勢股篩選

**觸發條件**：每週五收盤後 + 三大法人含分點資料齊全（v2 由 16:30 移後至 17:30）。

### 漏斗式四層（v3.1 SEPA 重整：Trend Template → 籌碼/Stage 2 → VCP/Pivot）

#### 第一層 N（負面排除 + Stage 4 一票否決）
- 近 2 季任一季 EPS < 0
- 董監/大股東近 1 月持股減少 > 1%
- 外資連 10 日以上淨賣超
- **借券餘額近 10 日增加 > 30%**（v2 新增，借券無強制回補 → 真空頭部位）
- KY 股 / 全額交割股 / 處置股 / 警示股
- **個股 Stage 4（v3.1 新增）**：MA50 < MA150 < MA200 且價跌破 MA50 且 MA200 ≥ 20 日不上升 → hard reject（依 §0.4）

#### 第一層 — Trend Template 8 條全過（v3.1 SEPA 核心，~80-150 檔）

> **依 Mark Minervini Trend Template；本地化**：成交額門檻替代美股 ADV、RS Percentile 門檻 65（vs 美股 70）、其餘條件不變。**8 條須全過，任一不過排除**。

| # | 條件 | 台股本地化閾值 |
|---|---|---|
| (1) | 收盤價 > MA50 | — |
| (2) | MA50 > MA150 | — |
| (3) | MA150 > MA200 | — |
| (4) | 收盤價 > MA150 | — |
| (5) | 收盤價 > MA200 | — |
| (6) | MA200 上升趨勢 | 過去 ≥ 20 個交易日 MA200 單調或非降；理想 ≥ 4–5 個月 |
| (7) | 距 52 週高 ≤ 25% | 收盤價 ≥ 52W_High × 0.75 |
| (8) | RS Percentile ≥ 65 + 距 52 週低 ≥ 30% | RS Percentile 由 `rs_percentile_calc` 計算（252 日加權；台股池 = TWSE+OTC 成交額 ≥ NT$100M/日）；門檻 65（vs 美股 70；台股流動股池較小） |

**輔助流動性過濾**（避免進低流動股）：
- 5 日均量 > 2,000 張 **OR** 均成交額 > NT$ 100M

#### 第二層（產業熱度，計算 0-10 分，輔助訊號）
- 產業 5 日漲幅前 30% +4
- 八大行庫本週淨買超前 5 大產業 +3
- 外資+投信本週合計淨買超 +3

#### 第三層（Stage 2 確認 + 籌碼確認 ~30-50 檔）

**Stage 2 確認（v3.1 新增 — SEPA 必要條件）**：
- 收盤價 > MA50 > MA150 > MA200（多頭排列）
- MA200 過去 ≥ 20 個交易日上升
- 量能在突破日 ≥ 1.4× 20DMA（顯示機構介入）
- 不在 Stage 3 高位震盪期（高點與低點振幅 30 日內 ≤ 20% 視為 Stage 2；> 30% 標記為 Stage 3 警示）

**籌碼確認（v3.0 沿用，不動）**：
- 外資+投信 5 日合計淨買超 > 0
- **主力分點集中度 = (前 15 大買超分點淨買量) / (當日成交量) ≥ 25% 連 3 日**
- **個股期未平倉量近 5 日增加**（法人佈局個股期常領先現股 1-2 日）
- 融資增幅 < 融券增幅
- 集保戶數遞減
- **借券餘額不在快速增加區（< +15% / 10 日）**

#### 第四層（VCP / 杯柄 / 平台突破 + Pivot Breakout 量價條件，~10-15 檔）

**SEPA 核心型態（v3.1 排序明確化）**：
- **VCP（最高優先）**：3-5 次回檔幅度遞減（如 15% → 10% → 6% → 3%），每次振幅 ≤ 前次 50%；量能同步遞減；最後一次收縮量能極低（供給耗盡）
- 杯柄（次優先）：U 型整理 7-65 週 + 5-25% 把手回檔
- 平台突破（再次）：5-7 週橫盤振幅 < 15% 後突破

**Pivot Breakout 量價條件（v3.1 明確化）**：
- Pivot point = 整固期最後一個高點
- **進場區間：Pivot ~ Pivot + 5%**（超過 +5% 不追）
- **量能 ≥ 1.4× 20DMA**（典型 1.5–2.0×；平量或下量突破為失敗信號）
- 收盤價 > 20MA 二次確認

**輕基本面 + 情緒面**：
- 近月營收 YoY > 平均、EPS 預估未下調
- **近 7 日法人調升目標價 ≥ 2 家 OR 重訊正面**

### watchlist 更新邏輯（汰弱留強）
- 持倉股強制保留
- 既有股本週通過 → 合併欄位（保留 `added_date`、覆蓋分數/題材）
- 既有股本週未通過 → 移至 `removed_recent[]`（paused 1 週寬容期）
- 新命中且不在清單 → 新增
- **上限 20 檔（持倉外加，v2 由 15 提升至 20，因允許 4-6 檔持倉）**

### 交易邏輯
本階段**不做交易**，僅產出候選池。

---

## 3. 【情境 1.5】Phase 1.5 — 每月 1-10 日 19:00：月營收觸發掃描（v2 新增）

**月營收公布是台股動能策略最強催化劑**，獨立排程避免被週/日線蓋過。

### 篩選條件（任一通過即加入 monthly-revenue-watch）

```
條件 A（爆發型）：
  當月 YoY > +30% AND MoM > +10% AND 創歷史新高

條件 B（趨勢型）：
  過去 3 個月 YoY 連續 > +20%（趨勢確認）

必要過濾：
  股本 < 100 億（避免大型股稀釋效應）
  當日成交量 > 2,000 張
  非處置 / 警示 / 全額交割
```

### 處理流程
1. 加入 `monthly-revenue-watch` 清單
2. 下個交易日於 Phase 2B 中**優先評估**（分數天花板 +5 加分）
3. 連續 2 個月通過 → 自動進入 Phase 1 watchlist

---

## 4. 【情境 2A】Phase 2A — 盤中 11:00 / 13:00：強勢股即時掃描（v2 新增）

動能交易等到 16:30 收盤才動作 → 強勢股當天就漲停了。新增盤中觸發點。

### 11:00 強勢股掃描
```
篩選條件（v3.1 SEPA 強化）：
  - 當日漲幅前 30 名
  - 量能 > 2.0× 5 日均量
  - RS Percentile ≥ 65（替代 v3.0「近 5 日 RS > 大盤」，依 §1 第二層 Trend Template (8) 同源計算）
  - 個股 Stage = 2（非 Stage 3/4）
  - 非 Risk-Off 模式
  - 非處置 / 警示 / 全額交割

→ 加入「intraday-watch」並推播通知
```

### 13:00 收盤前最後檢視
```
intraday-watch 標的若：
  - 仍維持當日漲幅前 50
  - 收盤前 30 分鐘量能持續放大（VWAP 量能斜率正向）

→ 標記為「明日優先評估」
→ 收盤後直接進 Phase 2B 高優先序
```

### 交易邏輯
本階段**不直接下單**，僅標記訊號。動能策略仍以收盤後 Phase 3 為主決策點。

---

## 5. 【情境 2B】Phase 2B — 每交易日 17:30：觀察清單動態評分

**觸發條件**：每個交易日收盤 + 法人資料齊全後（v2 由 16:30 移後至 17:30）。

### 大盤環境判讀（Section A）
加權/櫃買指數位置（vs 5MA/20MA/60MA）、外資期貨多空變化、三大法人當日買賣超、台幣匯率、當日強弱產業排行、Phase 0 風險閘狀態。

### 逐檔重評分（**v3.1 SEPA 公式：40+25+25+10=100**）

```
═══════════════════════════════════════════════════════════
技術面（40）              ← v3.1 由 35 升為 40，吸收 RS Percentile + Stage / Trend Template
  趨勢結構（均線多頭/EMA/布林）   10
  Trend Template 8/8 全過          5     ← v3.1 SEPA 核心
  Stage 2 確認                     5     ← v3.1 SEPA 核心
  K 線品質（VCP/杯柄/平台優先）    8     ← VCP > 杯柄 > 平台 > 經典
  RS Percentile                    7     ← v3.1 自建 IBD 式：≥65=3 / ≥80=5 / ≥90=7
  量價結構（OBV + 突破量 ≥ 1.4×）  5

籌碼面（25）              ← v3.1 由 45 降為 25，把基本面分出來
  外資 5 日淨買超                  5
  投信 5 日淨買超                  4
  主力分點集中度 ≥ 25%（連 3 日）  7
  個股期未平倉量變化               3
  融資融券（融資減 + 股價漲）      2
  集保戶數遞減                     2
  借券餘額變化                    -3 ~ +2

基本面（25）              ← v3.1 完全新增（Minervini SEPA 重 EPS / 營收成長）
  季 EPS YoY ≥ 25%                 8
  季 EPS QoQ 加速（本季 vs 前季 ≥ 5pp）  5
  月營收 YoY ≥ 20% 且創歷史新高    6
  季營收 YoY ≥ 15%                 3
  機構持股遞增（外資/投信 30 日）  3

消息情緒面（10）
  法人調升目標價/出報告（7 日內）  3
  營收/財報優於預期 SUE > 1.0      3
  重訊正面（接單/擴產/購併）        2
  搜尋熱度（PTT/Google Trends）   -2 ~ +2  ← 過熱反向
═══════════════════════════════════════════════════════════
基礎分（100）+ 催化劑修正（+5 / -10）= 最終綜合分

★ 注：原 v2/v3.0 的「產業熱度 10」併入第二層漏斗作為 0-10 加分（§2「第二層」），不重複計入綜合分以避免共線性。
★ 權重待 §12 SEPA 黃金樣本 WFA 校準後定稿；現階段為設計值。
```

### 信號燈
- 🟢 ≥ 65 強力進場候選 → 觸發 Phase 3
- 🟡 50-64 持續觀察
- 🔴 < 50 暫不考慮

> **Risk-Off 期間：所有訊號天花板自動降為 50（即綠燈一律降黃）。**

### 新候選發掘（Section C）
當日漲停 / 接近漲停股若有基本面 + 籌碼支持 → 記錄至下次 Phase 1 優先評估。

### 交易邏輯
本階段**不直接下單**，僅標記「準備進場」狀態並通知使用者觸發 Phase 3。

---

## 6. 【情境 3】Phase 3 — LLM 自動決策 + Confirm Gate（v3 重構）

> **v3 變更**：取代 v2「使用者手動觸發 + 人腦判斷」。Phase 2B 篩出 ≥ 65 的候選**自動進入 LLM Decider**（`entry_decision_team` swarm），系統覆寫 sizing/ATR、Risk Gate 硬擋後，依 `OHMYSTOCK_AUTO_EXECUTE` 旗標走「人工 confirm」或「自動執行 + 熔斷」。

### 6.1 觸發

- **自動觸發**：Phase 2B 任一檔 `final_score ≥ 65` → 系統把候選送進 `entry_decision_team` swarm
- **批次節流**：同一候選 24 小時內最多送進 LLM 一次（避免重複決策）
- **過濾前置硬性檢查**（任一觸發直接拒絕，**不送 LLM**，省 token）：
  - ❌ Risk-Off 旗標亮起
  - ❌ 月度 P&L ≤ -8% 熔斷中
  - ❌ 近 20 筆勝率 < 40%
  - ❌ 5 連敗暫停期內
  - ❌ 持倉檔數 ≥ 6
  - ❌ 同產業已有 2 檔（除非 LLM 標記為衛星倉 ≤ 10%）
  - ⚠️ 3 連敗倉位減半中 → 倉位上限砍半（仍進 LLM,但 sizing 上限自動降）

### 6.2 LLM 輸入（系統自動組裝 prompt）

LLM Decider 收到的標準輸入結構（由 `entry_decision_team` 編排器組裝）：

- **候選快照**：`symbol`、`final_score`、`tech_score(35)`、`chip_score(45)`、`industry_score(10)`、`sentiment_score(10)` 子分數明細
- **市場上下文**：當前 Phase 0 旗標、月度 P&L、近 20 筆勝率、連敗計數、既有持倉清單（同產業檔數、總曝險）
- **規則摘要**：本文件 §6.3 Must-have 三項 + §6.4 加分項八項條文（不要求 LLM 重背規則，由系統注入）
- **資料工具**：LLM 可呼叫 `chip_data_tool`、`market_data_tool`、`pattern_recognition_tool`、`news_sentiment_tool` 取最新資料
- **引用 skill**：`technical/breakout`、`chip/three-major-investors`、`tw_specific/momentum-swing` 等（系統列出可引用清單）

> **設計用意**：LLM 不是憑空想，而是「**讀規則 + 看數據 + 引用 skill** 後給結構化判斷」。

### 6.3 進場 Must-have（v3.1 改為 SEPA 三柱，3 項全要，LLM 必須逐項驗證）

> **v3.0 → v3.1 取代理由**：原 must_have（突破收陽 / 量 1.5× / RS > 大盤）只看當日訊號，缺長期 trend / market stage 驗證。SEPA 三柱涵蓋 Minervini 完整框架（趨勢 + 階段 + 進場結構），LLM 在 §6.5 schema 必須逐項給 evidence。

1. **Trend Template 8/8 全過**（依 §2 第一層 Trend Template 8 條）
   - LLM 必須列出 8 條每一條的 pass/fail + 數值佐證；任一不過即 must_have_check fail
2. **Stage 2 確認**（依 §0.4 / §2 第三層 Stage 2 定義）
   - 多頭排列 + MA200 ≥ 20 日上升 + 30 日內振幅 ≤ 20%（非 Stage 3）+ 非 Stage 4（已在 §0.4 hard reject）
3. **VCP / 杯柄 / 平台突破 + Pivot Breakout 量能**
   - K 線型態為 VCP（最優）/ 杯柄 / 平台突破其一
   - 進場價在 Pivot ~ Pivot + 5% 區間內
   - 突破日量能 ≥ 1.4× 20DMA（典型 1.5–2.0×）
   - 收盤價 > 20MA 二次確認

### 6.4 加分項（v3.1 SEPA flavor，8 項至少 4 項通過）

> **v3.0 → v3.1 改動**：把偏籌碼 / 通用技術項目，換成 SEPA 強調的「成長 + 強度」訊號。

- **季 EPS YoY ≥ 25%** 且本季 > 前季加速（Minervini 必看）
- **月營收 YoY ≥ 20% 且創歷史新高**（台股動能最強催化劑）
- **RS Percentile ≥ 80**（卓越強度，vs §6.3 Trend Template 門檻 65）
- **距 52 週高 ≤ 15%**（接近歷史高點，vs §6.3 Trend Template 門檻 25%）
- **VCP 收縮 ≥ 4 次** 且每次振幅 ≤ 前次 50%（教科書級 VCP）
- **機構持股遞增**（外資 / 投信過去 30 日持股比上升 + 主力分點集中度 ≥ 25%）
- **產業 RS 領先**（產業 RS Percentile 同樣 ≥ 80，反映產業群動能）
- **新高 + 量爆**（突破 52 週新高且量 ≥ 1.5× 20DMA，典型 Stage 2 加速期訊號）

### 6.5 LLM 必須輸出 schema（嚴格 JSON）

> 📎 **嚴格欄位約束（型別 / 範圍 / 強制 reject 條件）的唯一權威見 [`llm-decision-schema.md` §2.1](llm-decision-schema.md#21-欄位約束系統強制驗證)。** 以下 yaml 僅為高階摘要。

```yaml
decision: enter | reject | reduce_size  # 三選一
confidence: 0.0~1.0                     # 自信值；< 0.6 系統強制 reject
must_have_check:                        # 三項逐項驗證,任一 fail 強制 reject
  - {name: breakout_close, pass: bool, evidence: str}
  - {name: volume_15x,     pass: bool, evidence: str}
  - {name: rs_above_index, pass: bool, evidence: str}
bonus_score: 0~8                        # 通過數;< 4 強制 reject
proposed_sizing_pct: 0.0~25.0           # 提案部位 %（系統會與公式比對取較小）
reasoning: str                          # 自然語言論點（≥ 200 字）
cited_skills: [str, ...]                # 引用的 skill 路徑（≥ 1 項）
invalidation_conditions: [str, ...]     # 自寫失效條件（除預設外的客製條件）
risk_flags: [str, ...]                  # LLM 主動標記的風險（如:借券快速增加、產業轉空）
expected_holding_days: int              # 預期持倉天數（用於 §7.B 時間停損校準）
```

詳細 JSON Schema 見 [`llm-decision-schema.md`](llm-decision-schema.md)。

### 6.6 系統強制覆蓋（LLM 不可規避）

LLM 提案進入下單管線前,系統用以下規則覆寫：

| 項目 | 覆蓋規則 |
|---|---|
| **Sizing** | Volatility Targeting 公式重算（見下表）;LLM 提案 vs 公式取**較小**者 |
| **ATR 停損價** | 系統直接算 `max(進場價 × 0.94, 進場價 - 2.0 × ATR(14))`,LLM 不可覆寫 |
| **進場價區間** | 距 EMA20 0–5% 正常;5–10% sizing 自動減半;>10% LLM 即使建議 enter 也強制 reject |
| **Risk Gate** | 處置/警示/全額交割/漲跌停無法成交 → 直接拒單,LLM 無法覆蓋 |

### Position Sizing：Volatility Targeting（系統公式）

> 🔖 **本檔為 Volatility Targeting + ATR 停損 + 核心衛星出場公式的唯一權威**（SSOT）。
> design-zh-TW.md / safety-and-simulation.md / 其他文件**只能 reference 本節**，不可複製公式。
> 修改公式時只改本檔；走 §16 提案流程。

```
單筆名目曝險 = (帳戶權益 × 目標日波動 0.6%) / 個股 ATR%(14)

範例：
  帳戶 100 萬，目標日波動 0.6% → 6,000 元
  A 股 ATR% = 3% → 單筆 6,000 / 3% = 20 萬（20%）
  B 股 ATR% = 6% → 單筆 6,000 / 6% = 10 萬（10%）

軟性上限（取最小）：
  final_score ≥ 80 → 25% 上限
  final_score 65-79 → 20% 上限
  3 連敗中 OR 5~10% 距 EMA20 → 10% 上限
  總曝險 ≤ 80%
```

### 停損：ATR-Based（系統公式）
```
正常市況：停損價 = max(進場價 × 0.94, 進場價 - 2.0 × ATR(14))
弱勢盤：  停損價 = max(進場價 × 0.96, 進場價 - 1.5 × ATR(14))
```

> **設計用意**：低波動股停損更緊（提升勝率）；高波動股停損放寬（避免被洗）。

### 停利：核心 + 衛星分批（系統公式）
```
T1（+6%）         → 出場 50%（核心倉鎖獲利）
T1.5（+12%）      → 再出場 25%
剩餘 25%（衛星倉）→ Chandelier Exit:
                    持倉以來最高價 - 3 × ATR(22)
```

> **回測對比**：v1（T1 全出）PF 2.42、期望值 +6%；v2（核心+衛星）PF 約 2.0 但期望值 +15-25%。代價是 PF 略降，換取不被 monster trade 甩開。

### 6.7 Confirm Gate（依 `OHMYSTOCK_AUTO_EXECUTE` 切換）

#### 模式 A：人工 confirm（預設,`OHMYSTOCK_AUTO_EXECUTE=false`）

- LLM decision 寫入「待確認佇列」(`pending_decisions` 表)
- 使用者於 UI / CLI 看到：候選 + LLM `reasoning` + 系統 sizing + 預估停損 / 停利
- 必須通過 `<ConfirmDialog>`（強制勾選「我已閱讀」+ 輸入張數二次確認 + `isTrusted` 檢查,見 design §4.9.13）
- 確認後送 `paper_trade_tool` → Shioaji 模擬倉
- **Timeout**：建議 30 分鐘 expire（理由：訊號隨盤勢過時）

#### 模式 B：自動執行（`OHMYSTOCK_AUTO_EXECUTE=true`,需顯式設定）

通過下列**自動模式熔斷**才可送單（任一不通過 fallback 為人工 confirm）：

- LLM `confidence` ≥ 0.7
- 單日 LLM-decided 下單筆數 ≤ 5
- 單筆金額 ≤ `account_equity × 25%`
- 與系統 sizing 偏離 ≤ 30%（超過則自動取較小者）
- 連續 3 筆 LLM-decided 出場後虧損 > 5% → 鎖定 24 小時 fallback 人工

> ⚠️ **安全聲明**：自動模式仍屬模擬倉（`OHMYSTOCK_BROKER=shioaji-sim`）。Live 模式即使 `OHMYSTOCK_AUTO_EXECUTE=true` 也**強制人工 confirm**（design §4.5 防線 9）。

### 6.8 必須記錄（v3 擴充）

每筆進場決策（含被拒絕者）寫入 `trade-journal.json` 並同步進 FTS5 索引：

- **原欄位**：`entry_thesis`（natural language）、`thesis_invalidation`、`atr_at_entry`、`risk_regime_at_entry`
- **v3 新增**：
  - `llm_decision_id`：唯一識別 ID
  - `llm_model`：例 `claude-opus-4-7`、`claude-sonnet-4-6`
  - `llm_confidence`：0.0~1.0
  - `llm_reasoning`：完整 reasoning 文字
  - `cited_skills[]`：LLM 引用的 skill 路徑
  - `tool_calls[]`：LLM 在決策過程中呼叫的所有 tool（含參數與回傳摘要）
  - `proposed_sizing_pct`：LLM 提案 vs `final_sizing_pct`：系統覆寫後的最終值
  - `auto_executed: bool`：是否走自動模式
  - `human_confirmed_by`：confirm 者識別（Login user）
  - `human_confirmed_at`：confirm 時間（ISO-8601）
  - `decision_status`：`pending | confirmed | rejected | expired | auto_executed`
- **更新檔案**：`tw-portfolio-config.json` watchlist → positions（confirm 後）

---

## 7. 【情境 4】Phase 4 — 每交易日收盤後：持倉檢視與出場

**觸發條件**：每交易日整合在 Phase 2B 中執行；亦可手動單獨檢視。

### A. 停損檢查（最優先，不可妥協）
- 收盤跌破 ATR-based 停損價 → **隔日開盤市價出場**
- **盤中觸停損但收盤拉回**：停損價下移至「收盤價 - 1.5×ATR」與「進場價 - 2×ATR」較低者，警覺度升高
- 跌破進場日 K 線低點 → 觸發技術停損

### B. 時間停損（v2 新增）
- 持有 **7 個交易日未達 +3%** → **倉位減半**
- 持有 **10 個交易日未達 +3%** → **全出**

> 動能股不動就是錯。時間是動能策略的隱性成本。

### C. 停利 / 續抱判斷
- 獲利 ≥ +6% T1 → 出場 **50%**（核心倉鎖利）
- 獲利 ≥ +12% T1.5 → 再出場 **25%**
- 衛星倉 25% → **Chandelier(3×ATR)** 啟動
- 連 3 日縮量未創新高 + 綜合分數降 > 10 → 建議全出
- 出現頂部 K 線（射擊之星 / 吊人線 / 烏雲罩頂）+ 獲利 ≥ 6% → 全出
- 法人轉賣超 + 量縮 < 0.6× → 獲利 ≥ 5% 減 50%；< 5% 嚴密監控
- 布林碰 3.0 倍上軌 + 收黑 K → 強烈減碼

### D. 論點失效檢查（thesis_invalidation）
比對 entry_thesis 失效條件，任一觸發 → **不等停損，主動平倉**。常見失效條件：
- 綜合分數降 > 15
- RS 由正轉負
- 投信連 3 日賣超
- **借券餘額爆增 > 30%**（v2 新增）
- **個股期 OI 反向放空**（v2 新增）
- 催化劑取消（接單破局 / 法說失利）

### E. 移動停利規則（保留供人工調整參考）
僅在不啟用 Chandelier 衛星倉時使用：
- 獲利 > 8% → 停損上移至 +4%
- 獲利 > 12% → 停損上移至 +8%
- 獲利 > 16% → 停損上移至 +12%

### F. 出場後處理（v3 擴充）
- 移除 positions、寫入 `trade-journal.json`
- 更新 `consecutive_loss_tracker`
- **更新 `recent_20_winrate`**（v2 新增）
- **更新 `monthly_pnl_tracker`**（v2 新增，觸發月度熔斷檢查）
- 任一筆盈利 → streak 歸零，恢復正常倉位
- **出場時必須補完 trade-journal 條目**（v3 新增）：
  - `exit_reason`（自然語言）
  - `exit_tag`（自動標記，七選一）：`hit_stop_loss / hit_t1 / hit_t1_5 / chandelier / time_stop / thesis_invalid / discretionary`
  - `pnl_pct`（出場 P&L %）
  - `hold_days`（實際持倉天數）
  - `thesis_held: bool`（對照 `entry_thesis`：是否如預期發展）
  - `vs_expected_holding`（實際 vs `expected_holding_days`）
- **同步寫入 FTS5 索引**（v3 新增）：`journal_entries` 表,供 §15 LLM 復盤檢索
- **月底自動觸發 §15 LLM 復盤**（v3 升級;原 v2「自動產出統計報告」改為由 LLM 跑復盤迴圈,輸出 `reviews/<period>/report.md` + 可能的 `proposals/*.md`）

---

## 8. 連續虧損 + 勝率漸進降頻機制（v2 增強）

| 觸發條件 | 動作 | 解除條件 |
|---|---|---|
| 3 連敗 | 倉位減半（`per_trade_default_pct` 降為 10%） | 任一筆盈利 |
| 5 連敗 | 暫停新進場 5 個交易日 | 5 日後 + 大盤 trend 翻多 |
| **近 20 筆勝率 < 40%**（v2 新增） | 暫停新進場 | 近 10 筆勝率回升至 ≥ 50% |
| **單月 P&L ≤ -8%**（v2 新增） | 強制全平 + 停止新進場至月底 | 月底完成復盤檢討 |
| 任一筆盈利 | 連敗計數歸零 | — |

---

## 9. K 線型態庫（v3.1 SEPA 排序明確化）

### 9.1 動能聖杯（William O'Neil + Mark Minervini 系，**v3.1 排序明確化**：VCP > 杯柄 > 平台突破 > 經典）

> **§6.3 must_have_check 第三柱**只認可這三種型態 + Pivot Breakout 量價條件。經典看漲型態降為輔助訊號，不單獨觸發進場。

- **VCP（Volatility Contraction Pattern，最高優先）**：3-5 次回檔幅度遞減（典型 15% → 10% → 6% → 3%），每次振幅 ≤ 前次 50%；量能同步遞減 → 最後一次收縮量極低（供給耗盡）→ 突破當天爆量 ≥ 1.4× 20DMA。Pivot point = 整固期最後一個高點，進場區 Pivot ~ Pivot + 5%。
- **杯柄（Cup & Handle）**：U 型整理 7-65 週 + 5-25% 把手回檔。把手量能逐步乾枯 → 突破日量爆。
- **平台突破（Flat Base）**：5-7 週橫盤振幅 < 15% 後突破。Stage 2 加速期常見。

### 9.2 輔助看漲型態（單獨不夠，需配合 Trend Template + Stage 2）
紅三兵、底部翻揚、突破缺口、整理突破、吞噬、晨星、旗形 / 三角旗。

### 9.3 看跌出場型態
射擊之星、吊人線、烏雲罩頂、量增收黑、量價背離、布林 3σ 觸頂。

實作參考：`pyti` + `stockstats` + 自寫 detector（`src/ohmystock/strategies/_kpattern/`），詳細 VCP 量化輸出規格見 [`tools-contracts.md`](tools-contracts.md) `pattern_recognition_tool`。

---

## 10. 統一評分公式（v3.1 SEPA 完整版，與 §5 同步）

```
═════════════════════════════════════════════════════════════
技術面（/40）
  趨勢結構（均線多頭/EMA/布林）   10
  Trend Template 8/8 全過          5
  Stage 2 確認                     5
  K 線品質（VCP/杯柄/平台優先）    8
  RS Percentile（≥65=3 / ≥80=5 / ≥90=7）  7
  量價結構（OBV + 突破量 ≥ 1.4×）  5

籌碼面（/25）
  外資 5 日淨買超                  5
  投信 5 日淨買超                  4
  主力分點集中度 ≥ 25%（連 3 日）  7
  個股期 OI 變化                   3
  融資融券                         2
  集保戶數遞減                     2
  借券餘額變化                    -3 ~ +2

基本面（/25）
  季 EPS YoY ≥ 25%                 8
  季 EPS QoQ 加速（≥ 5pp）         5
  月營收 YoY ≥ 20% 且創歷史新高    6
  季營收 YoY ≥ 15%                 3
  機構持股遞增（外資/投信 30 日）  3

消息情緒面（/10）
  法人目標價 / 報告（7 日內）      3
  營收/財報優於預期 SUE > 1.0      3
  重訊正面（接單/擴產/購併）        2
  搜尋熱度（過熱反向）            -2 ~ +2
═════════════════════════════════════════════════════════════
基礎綜合分（滿分 100）+ 催化劑修正（+5 正面 / -10 法說會警示）
                       + 月營收動能加分（+5）
                     = 最終綜合分數

≥ 65：🟢 強力進場候選（回測驗證最佳門檻；待 SEPA 黃金樣本 WFA 校準後定稿）
50-64：🟡 持續觀察
< 50：🔴 暫不考慮

★ Risk-Off 期間天花板降為 50（綠燈一律降黃）
★ 個股 Stage 4 直接 hard reject（依 §0.4），不進評分
```

---

## 11. 關鍵風控與決策優先序速查 v3

- **決策優先序**：
  - **硬性閘**：Risk-Off > 月度熔斷 > 連敗管理 > 持倉 / 同產業上限
  - **執行**：停損 > 停利 / 出場 > 進場（**LLM Decider + Confirm Gate**） > 觀望
- **LLM 決策邊界**：LLM 提案 sizing 與系統公式取**較小**;ATR 停損價系統強算 LLM 不可覆寫;Risk Gate 拒單 LLM 無法覆蓋
- **Confirm Gate**：`OHMYSTOCK_AUTO_EXECUTE=false`（預設）人工 confirm;`true` 時仍須通過熔斷（單日筆數、單筆金額、confidence ≥ 0.7、sizing 偏離 ≤ 30%）
- **資金紀律**：總曝險 ≤ 80%、持倉 4-6 檔、**同產業最多 2 檔**、單筆 ≤ 25%、**Volatility Targeting**
- **時效鐵則**：所有報告/掃描的法人買賣超**必須是當日數據**（Phase 1 移至 17:30 確保分點齊全）
- **追高紅線**：價格距 EMA20 > 10% 嚴禁進場;> 5% 倉位減半
- **盤中觸發**：11:00 / 13:00 強勢股掃描,避免錯過當日訊號
- **時間停損**：7 日 / 10 日雙閘
- **月度熔斷**：-8% 全平 + 強制復盤(觸發 §15 LLM 復盤迴圈)

---

## 12. 回測驗證要求（v3.1 SEPA 強化）

任何策略改動上線前**必須揭露**：

| 項目 | 要求 |
|---|---|
| 樣本期間 | 2018-2024（含 2022 熊市） |
| 樣本內外切分 | 訓練 2018-2022 / 測試 2023-2024 / 紙上 2025+ |
| Walk-Forward Analysis | 5 年訓練 + 1 年測試，滾動 1 年 |
| 樣本內外 Sharpe 落差 | < 30%，否則視為過擬合 |
| 手續費 | 0.1425% × 0.28 折 |
| 證交稅 | 一般 0.3% / 當沖 0.15%（至 2027/12/31） |
| 滑價假設 | 0.3%（漲跌停日 1.0%） |
| 撮合假設 | 漲跌停且委買/委賣量 0 → 不成交 |
| 處置 / 警示股 | 排除回測標的池 |
| Robust 測試 | 每組最佳參數 ±10% 鄰域 Sharpe 衰減 < 50% |
| **SEPA 黃金樣本（v3.1 新增）** | **必須含**下列已知強勢股，新規則不得退化（命中突破日 ± 3 個交易日 × 後續 30 日報酬不低於 v3.0 規則 -10% 相對值）|

### 12.1 黃金樣本清單（v3.1 SEPA 校準用）

| 類別 | 標的 | 用途 |
|---|---|---|
| 既有大盤 / 龍頭 | 0050、2330、0056 | 確保新規則不偏掉藍籌動能（v3.0 沿用） |
| **2023–2024 SEPA 強勢股範例（v3.1 新增）** | 2454（聯發科）、3231（緯創）、3017（奇鋐）、2376（技嘉）、6669（緯穎） | AI 伺服器 / GPU 周邊概念股，2023-Q2 ~ 2024 全年皆呈 Stage 2 + 多次 VCP 形態 |
| **反向校驗（必須被擋）** | 任選 1–2 檔 2023 Stage 4 個股（如 2317 在 2022-2023 修復期前的 Stage 4 區段） | 驗證 §0.4 個股 Stage 4 一票否決確實啟動，不誤撈底 |

**校準目標**（待 Phase 5 復盤上線後由 LLM 從 trade journal 自動補充更多樣本）：
- SEPA 強勢股範例在 Pivot 突破日 ± 3 交易日內被新規則「進場」標記命中率 ≥ 60%
- Stage 4 反向校驗股 100% 被 §0.4 hard reject
- 整體 WFA Sharpe ≥ v3.0 規則 × 0.95（不退化超過 5%）

> **黃金樣本最終定稿規範**：v3.1 上線初期，黃金樣本由人工指定（本節）；Phase 5 復盤閉環啟用後，依 [`reviews/_golden/`](../reviews/) 自動更新。

---

## 13. 附：v3 訊號決策樹（含 LLM Decider 與閉環迴圈）

```
                    ┌─────────────────┐
                    │ Phase 0: Risk   │
                    │ Gate 檢查       │
                    └────────┬────────┘
                             │
                ┌────────────┴────────────┐
                │                         │
            Risk-Off                   Risk-On
                │                         │
        ┌───────┴───────┐                 │
        │ 禁止新進場     │                 ▼
        │ 停損上移 2%   │         ┌──────────────────┐
        │ 允許出場/避險 │         │ Phase 1/1.5/    │
        └───────────────┘         │ 2A/2B 評分      │
                                  └──────┬────────────┘
                                         │
                                final_score ≥ 65?
                                         │
                          ┌──────────────┼──────────────┐
                          │ Yes          │ No
                          ▼              ▼
                    ┌──────────┐    🟡/🔴 觀察
                    │ Phase 3  │
                    │ 前置硬檢 │
                    └────┬─────┘
                         │ Pass?
                  ┌──────┼──────┐
                  │ Yes         │ No
                  ▼             ▼
            ┌─────────────────┐  拒絕(寫 journal)
            │ LLM Decider      │
            │ entry_decision_  │
            │ team swarm       │
            │ 讀規則+數據+skill │
            │ 輸出 §6.5 schema │
            └────┬─────────────┘
                 │ decision?
        ┌────────┼────────┐
        │ enter           │ reject / reduce_size
        ▼                 ▼
  ┌──────────────┐   寫 journal
  │ 系統強制覆寫 │   結束
  │ Sizing公式取小│
  │ ATR 停損強算 │
  │ Risk Gate 硬擋│
  └──────┬───────┘
         │
         ▼
  ┌──────────────────────────┐
  │ Confirm Gate              │
  │ AUTO_EXECUTE=false → 人工 │
  │ AUTO_EXECUTE=true → 熔斷  │
  │ (筆數/金額/confidence)     │
  └──────┬───────────────────┘
         │ ack?
  ┌──────┼──────┐
  │ Yes         │ No(timeout/reject)
  ▼             ▼
  下單模擬倉   寫 journal
  + 寫 journal 結束
        │
        ▼
  ┌─────────────────────┐
  │ Phase 4 持倉檢視     │
  │ ① 停損 / 時間停損    │
  │ ② 核心+衛星出場      │
  │ ③ 論點失效檢查       │
  │ ④ 連敗/月度熔斷更新  │
  │ ⑤ 出場補完 journal  │
  └──────┬──────────────┘
         │ 月底 / 手動
         ▼
  ┌──────────────────────────┐
  │ Phase 5 (§15) LLM 復盤    │
  │ post_trade_review_team    │
  │ 資料→歸因→聚合→批判→提案  │
  └──────┬───────────────────┘
         │ proposals/*.md
         ▼
  ┌──────────────────────────┐
  │ §16 提案驗證閘            │
  │ WFA + Robust + 黃金回歸   │
  └──────┬───────────────────┘
         │ pass?
  ┌──────┼──────┐
  │ Yes         │ No
  ▼             ▼
  人工 PR     拒絕/重做
  review
        │
        ▼
  合併 cheatsheet & strategy code
  bump 版本(v3.0 → v3.1 …)
        │
        └──── 下一輪迴圈 ─────────► Phase 0
```

---

## 15. 【情境 5】Phase 5 — LLM 復盤迴圈（v3 新增）

**用途**：取代 v2「月底自動產出統計報告」。LLM 從 trade-journal 自動拆解過去交易,產出**自然語言復盤報告**與**策略改動提案**,作為 §16 優化迴圈的輸入。

### 15.1 觸發
- **自動**：每月 1 號 19:00、季底
- **手動**：使用者透過 CLI / UI 指定區間
  - CLI 範例:`uv run ohmystock review --from 2026-01-01 --to 2026-03-31`
  - 月度熔斷觸發後**強制觸發**(對應 §0「-8% 全平 + 強制復盤」)

### 15.2 LLM 流程（Swarm preset: `post_trade_review_team`）

五節點 DAG,每節點各自有獨立 LLM 子代理人:

| 節點 | 輸入 | 輸出 |
|---|---|---|
| **資料節點** | 區間內 trade-journal + entry_thesis + 後續價格(出場後 5/10/20 日報酬) | 結構化交易紀錄 + 後續走勢 |
| **歸因節點** | 資料節點輸出 | 逐筆分類:`thesis_held` / `thesis_failed_but_profit` / `thesis_failed_loss` / `stop_saved` / `time_stop_correct` / `time_stop_wrong` |
| **聚合節點** | 歸因節點輸出 | 進場條件命中率、stop 觸發後 N 日反彈率、催化劑後續發酵率、各 K 線型態勝率 |
| **批判節點** | 聚合節點輸出 + cheatsheet 全文 | 找出**勝率 / 期望值偏低**的條件、過度保守 / 過度激進的規則 |
| **提案節點** | 批判節點輸出 | 產出 `proposals/<YYYY-MM-DD>-<topic>.md`,內含目標章節、改動 diff、佐證資料、預期改善幅度 |

詳細評分 / 歸因 rubric 見 [`post-trade-review-rubric.md`](post-trade-review-rubric.md)。

### 15.3 輸出檔案

```
reviews/
└── 2026-04/                          # 月度復盤資料夾
    ├── report.md                     # 自然語言復盤報告(給人類讀)
    ├── metrics.json                  # 量化指標(勝率/PF/MDD/期望值/各條件命中率)
    └── attribution.json              # 逐筆歸因明細

proposals/
├── 2026-04-30-vcp-volume-threshold.md       # 提案:VCP 量能門檻 1.5×→1.3×
├── 2026-04-30-time-stop-relax-vcp.md        # 提案:VCP 型態時間停損放寬 7→10 日
└── ...
```

### 15.4 LLM Token 控管

- 單次復盤上限:Opus 4.7 主協調(批判 + 提案節點)+ Sonnet 4.6 子節點(資料/歸因/聚合)
- 對齊 design §14「Claude API 額度爆量」緩解策略
- 預估每月度復盤 ≈ 50K~150K input tokens(視交易筆數)

---

## 16. 策略改動提案 → 驗證 → 合併（v3 新增,閉環核心）

> **為何需要**：v2「Optuna 參數最佳化」只能調**現有規則的數字**;v3 加上**邏輯層改動**(條件、門檻、新增/移除規則)的演進通道。**LLM 不可直接 commit cheatsheet**,所有改動走以下流程。

### 16.0 適用範圍（v3 決策 #14 補充）

§16 流程**主管「strategy code / cheatsheet 文字 / 硬規則」改動**：
- Risk-Off / 月度熔斷 / ATR 停損 / Volatility Targeting sizing / §2.9 防線 9
- K 線型態檢測程式（`strategies/_kpattern/*.py`）
- cheatsheet §0、§6.6、§7、§9 等規則文字

**LLM prompt 改動**（Phase 3 Decider system prompt、Phase 5 復盤 swarm system prompt）走**另一通路**，詳 v3 決策 #14：
- Decider prompt → 回測 PnL/Sharpe 客觀閘 → 直接 merge `prompts/decider.md`
- Review prompt → `reviews/_golden/` 黃金集比對閘 → 直接 merge `prompts/review.md`

兩條通路互不干擾；硬規則改動進 `strategies/`、判斷層改動進 `prompts/`。

### 16.1 提案來源
- §15 復盤的提案節點(主要)
- 人工發現(任何時候手寫進 `proposals/`)
- 外部論文 / 研究報告(由人類整理)

### 16.2 提案 schema（`proposals/<YYYY-MM-DD>-<topic>.md`）

每份提案必含下列章節（Markdown 格式）:

```markdown
---
proposal_id: 2026-04-30-vcp-volume-threshold
target_section: cheatsheet §6.4 加分項
status: pending | validating | approved | rejected | merged
created_by: post_trade_review_team | <human>
created_at: 2026-04-30T19:30:00+08:00
---

## 改動描述
(targeting cheatsheet 的具體章節 + 改動內容)

## 動機與佐證
(連結 reviews/<period>/metrics.json 的相關指標)

## 改動 diff 草稿
```diff
- VCP 量能 ≥ 1.5× 5 日均量
+ VCP 量能 ≥ 1.3× 5 日均量(過去 30 筆 VCP 命中率僅 38%,放寬可提升 ≈ 12 檔/月)
```

## 預期影響範圍
(影響哪些 strategy 程式碼、哪些 skill)

## 風險評估
(可能的負面情境與緩解)
```

### 16.3 驗證閘（自動,WFA + Robust + 黃金樣本）

提案 status → `validating` 後,系統自動觸發:

| 驗證項 | 通過條件 |
|---|---|
| **WFA 樣本內外 Sharpe 落差** | < 30%(過擬合警示) |
| **Robust 測試** | ±10% 鄰域 Sharpe 衰減 < 50% |
| **黃金樣本回歸** | 不退化(0050 / 2330 / 0056 等基準) |
| **MDD 變化** | 不能比原版差超過 +20% 相對值 |

任一項失敗 → status = `rejected`,寫入 `reviews/<period>/rejected_proposals.md`。

### 16.4 人工 review

驗證閘通過後 → status = `approved`,進入人工 review:

- **本機開發**:`proposals/PENDING_REVIEW/<id>.md` 等待人工檢視
- **GitHub PR 模式**(若已 push):自動開 PR,標籤 `proposal:auto-approved`
- 人工檢視 diff、佐證資料、WFA 報告 → 同意則合併

### 16.5 合併 + 版本管理

- 合併動作 = **同步寫 cheatsheet + 對應 strategy code 註解**
  - cheatsheet 對應章節更新規則文字
  - `strategies/*.py` 檔案頂端 `# implements cheatsheet §X (v3.1)` 隨版本 bump
- **版本約定**:`v3.0` → 加單一提案後 `v3.1`、累積多項或語意重大調整後 `v4.0`
- 每次 bump 更新 cheatsheet 開頭 Changelog

### 16.6 回滾

- 每個版本對應 git tag,問題出現可 `git revert` 至特定版本
- 策略 code 註解 `# implements §X (v3.1)` 提供雙向追溯

---

## 17. 與 ohMyStock 系統其他文件的關係

- **本文件（workflow-cheatsheet.md）**：交易邏輯**權威來源（Single Source of Truth）**。所有選股 / 進場 / 停損 / 停利 / 部位 / 風控規則以此為準。
- **design-zh-TW.md §4.10 / §4.7.1 / §4.7.2**：策略架構 + LLM Decider swarm + 復盤 swarm 的程式介面說明,**具體邏輯參數引用本文件**。
- **`docs/llm-decision-schema.md`**(v3 新增):§6.5 LLM 輸出 schema 的 JSON Schema 與 Trade Journal 格式
- **`docs/post-trade-review-rubric.md`**(v3 新增):§15.2 復盤五節點的評分 / 歸因細則
- **`proposals/README.md`**(v3 新增):§16 策略改動提案模板與工作流
- **`reviews/README.md`**(v3 新增):§15.3 復盤輸出格式與歷史索引
- **`src/ohmystock/strategies/`**:本文件的程式碼實作。每支策略檔案頂端註解需標示「實作 workflow-cheatsheet.md §X(v3.x)」(版本號隨 §16 合併動作 bump)。
- **`src/ohmystock/skills/technical/` 等**:給 LLM 的策略「使用說明」,也以本文件為單一事實來源。

> **修訂須知**:本文件變動 → 同步更新版本號 + Changelog;對應修改 `strategies/` 程式碼與 `skills/` 說明;**§6 / §15 / §16 邏輯變動必須走 §16.3 驗證閘 + 人工 PR review**(LLM 不可直接 commit);重大邏輯變動需重跑回測(§12 規範)。
