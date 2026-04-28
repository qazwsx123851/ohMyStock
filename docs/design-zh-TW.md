# ohMyStock — 台股 AI 交易代理人系統設計書

> 版本：v1.0 草案 ｜ 撰寫日期：2026-04-26 ｜ 工作目錄：`D:\ohMyStock\`
> 參考專案：[HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading)
> 對象：技術主管 / Reviewer

---

## 1. 專案背景（Context）

### 1.1 緣起
主管希望打造一套**專為台股市場設計的 AI 交易研究代理人**，定位類似 HKUDS 的 Vibe-Trading 框架，但針對台灣證交所（TWSE）/ 櫃買中心（OTC）的市場結構、籌碼資料、法規限制做深度特化。

### 1.2 解決的問題
- 台股研究流程仍高度仰賴人工：技術面、基本面、籌碼面、三大法人、融資融券、產業輪動需要人工拼接資料源。
- 既有的對岸 / 美股交易代理（Vibe-Trading、FinGPT 等）**不支援台股市場結構**：T+2 交割、±10% 漲跌停、當沖證交稅減半、除權除息、處置股票、借券賣出 vs 融券差異。
- 散戶／自營交易者需要可重現、可回測、可審計的策略開發流程，而不是黑箱訊號。

### 1.3 預期成果
1. 一個本機可運行的多代理人（multi-agent）系統，用自然語言指令完成「選股 → 分析 → 回測 → 模擬下單 → 投資日記」全流程。
2. 模擬下單（Paper Trading）透過永豐 Shioaji 模擬倉執行，**第一階段不接實單**。
3. 完整可審計的 prompt / tool-call / order log（個人專案：用於事後 debug + 復盤；非金管會合規需求）。

---

## 2. 範圍與關鍵決策（Scope & Decisions）

| 議題 | 決策 | 備註 |
|---|---|---|
| 執行範圍 | **Paper Trading + 研究 / 回測** | 第一階段不接實單；架構保留 live 切換點 |
| 主要資料源 | **FinMind（主）+ Shioaji（即時報價/模擬下單）+ twstock / yfinance（fallback）** | FinMind 需贊助會員方能取得完整籌碼資料 |
| 技術棧 | **Python 3.11+ ＋ Claude Agent SDK** | 不使用 LangChain；改採 Anthropic 原生 SDK |
| 前端 | React 19 + Vite + TypeScript（對標 Vibe-Trading 的 `web/`） | MVP 以 CLI 為主，Web UI Phase 4 上線 |
| 部署 | Docker Compose | 本機開發為主 |
| 開發週期 | **約 13 週（3 個月）** 達 MVP，後續迭代 | 詳見 §10 路線圖 |
| 法律定位 | **僅供研究參考，不構成投資建議** | 全 UI / 報告皆需附此免責聲明 |

### 2.1 明確排除（Out of Scope, v1）
- 真實資金下單（live trading）
- MCP Server 對外（Phase 2 再加）
- 移動裝置 App
- 多用戶 SaaS（為個人/小團隊使用設計）
- 加密貨幣 / 海外股票（Vibe-Trading 已具備，本系統不重做）

---

## 3. 系統架構總覽（Architecture）

> **v3 變更**：新增 **LLM Decider Pipeline**（夾在 Agent 核心層與能力層之間）、**Trade Journal Service** 與 **Post-Trade Review Service**（服務層）。對應 [`docs/workflow-cheatsheet.md`](workflow-cheatsheet.md) §6 / §7 / §15 / §16 的閉環迴圈。

```
┌────────────────────────────────────────────────────────────────┐
│                      使用者介面層（v3 拆兩專案 monorepo）        │
│  CLI (typer)  │  web-admin (React, auth)  │  web-public (pixel) │
│  /api/admin/*（auth） + /api/public/*（masked SSE）              │
│  Backend EventBus → AdminSerializer / MaskedEventSerializer 兩通道│
└──────────────────────────┬─────────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────────┐
│              Agent 核心層（Claude Agent SDK）                    │
│  ┌────────────┐  ┌─────────────┐  ┌──────────────┐             │
│  │ Agent Loop │  │ System      │  │ Compaction   │             │
│  │ (async)    │  │ Prompt      │  │ (5-layer)    │             │
│  └─────┬──────┘  └──────┬──────┘  └──────┬───────┘             │
│        │                │                │                     │
│  ┌─────▼────────────────▼────────────────▼────────┐            │
│  │  PreToolUse / PostToolUse Hooks（稽核日誌）      │            │
│  └──────────────────────┬──────────────────────────┘           │
└─────────────────────────┼──────────────────────────────────────┘
                          │
┌─────────────────────────▼──────────────────────────────────────┐
│              LLM Decider Pipeline（v3 新增）                    │
│  ┌──────────────────────────────────────────────────────┐      │
│  │ Phase 2B 訊號 → entry_decision_team swarm            │      │
│  │   ↓ 系統覆寫 (Sizing 公式 / ATR 停損 / Risk Gate)     │      │
│  │   ↓ Confirm Gate (OHMYSTOCK_AUTO_EXECUTE 切換)        │      │
│  │   ↓ 寫 Trade Journal + 送 Broker                     │      │
│  └──────────────────────────────────────────────────────┘      │
└─────────────────────────┬──────────────────────────────────────┘
                          │
┌─────────────────────────▼──────────────────────────────────────┐
│                    能力層（Skills + Tools）                      │
│  Skills (~30, YAML+MD)        Tools (~20, Python)               │
│  ├ data/                      ├ market_data_tool                │
│  ├ technical/                 ├ chip_data_tool                  │
│  ├ fundamental/               ├ backtest_tool                   │
│  ├ chip/                      ├ paper_trade_tool                │
│  ├ tw_specific/               ├ screener_tool                   │
│  ├ quant/                     ├ swarm_tool                      │
│  └ portfolio/                 ├ memory_tool                     │
│                               ├ trade_journal_tool (v3 schema)  │
│                               ├ post_trade_review_tool (v3 新)  │
│                               ├ proposal_tool (v3 新)           │
│                               └ ...                             │
└─────────────────────────┬──────────────────────────────────────┘
                          │
┌─────────────────────────▼──────────────────────────────────────┐
│                       服務層                                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────┐        │
│  │ Backtest │ │ Paper    │ │ Memory + │ │ Swarm DAG   │        │
│  │ Engine   │ │ Broker   │ │ FTS5     │ │ Orchestrator│        │
│  └─────┬────┘ └────┬─────┘ └────┬─────┘ └──────┬──────┘        │
│        │           │            │              │                │
│  ┌─────▼───────────▼────────────▼──────────────▼─────┐         │
│  │ Trade Journal Service（v3 新增）                    │         │
│  │   - 寫 SQLite + FTS5 索引                          │         │
│  │   - LLM 決策、進場、出場、拒絕、過期 完整生命週期    │         │
│  ├─────────────────────────────────────────────────────┤        │
│  │ Post-Trade Review Service（v3 新增）                │         │
│  │   - post_trade_review_team swarm 編排               │         │
│  │   - 五節點 DAG:資料→歸因→聚合→批判→提案            │         │
│  │   - 輸出 reviews/<period>/ + proposals/*.md         │         │
│  ├─────────────────────────────────────────────────────┤        │
│  │ Proposal Validation Service（v3 新增）              │         │
│  │   - WFA + Robust + 黃金樣本回歸                     │         │
│  │   - 通過 → status=approved 等人工 PR review          │         │
│  └─────────────────────────────────────────────────────┘        │
└────────┬─────────────┬────────────┬───────────────────────────┘
         │             │            │
┌────────▼─────────────▼────────────▼───────────────────────────┐
│                     資料層 (Data Sources)                       │
│   FinMind  │  Shioaji  │  twstock  │  yfinance  │  TWSE OpenAPI │
│              │ MOPS scraper（重訊/季報）│ SQLite + Parquet 快取 │
└────────────────────────────────────────────────────────────────┘
```

---

## 4. 核心模組設計（Module Design）

### 4.1 Agent Loop（`src/ohmystock/agent/loop.py`）

採用 **Claude Agent SDK（`claude-agent-sdk` Python package）** 的 async 介面：

- 以 `ClaudeSDKClient` 包裝對話迴圈，`query()` 回傳 async iterator。
- **停用 SDK 內建 `Read/Write/Bash/Glob/Grep`**（透過 `allowed_tools=[]`），避免與我們的 Skill loader 衝突。
- 用 `PreToolUse` hook 紀錄所有 tool 呼叫（→ 稽核日誌）；`PostToolUse` 寫入 session DB。
- **不使用 SDK 內建 compactor**，自行實作五層上下文壓縮（micro / collapse / auto / manual / iterative），對標 Vibe-Trading `src/agent/context.py`。

> ⚠️ **與 Vibe-Trading 重要差異**：Vibe-Trading 採 LangChain，loop 是同步介面；改用 Claude Agent SDK 後 loop 必須**完全重寫為 async**，無法直接 port。Skills/Tools/Swarm 子系統可以照搬。

### 4.2 Skills 系統（`src/ohmystock/skills/`）

- 格式：YAML frontmatter + Markdown 內文（與 Vibe-Trading 完全相容）。
- Loader：`skills/_loader.py` 自動掃描，注入到 system prompt 的「skill catalog」段。
- 命名約定：每個 skill 一個檔案，例如 `chip/three-major-investors.md`。

#### 4.2.1 規劃 Skills 清單（共 ~30 個，分 7 類）

| 類別 | 數量 | 範例 |
|---|---|---|
| **資料來源（data/）** | 5 | finmind、shioaji-quote、twstock、yfinance、twse-openapi |
| **技術面（technical/）** | 6 | ma-crossover、kd-macd-rsi、bollinger、breakout、pattern-recognition、ichimoku |
| **基本面（fundamental/）** | 5 | financial-statement、valuation-pe-pb、eps-forecast、dividend-policy、mgmt-quality |
| **籌碼面（chip/）** | 6 | three-major-investors（外資/投信/自營）、margin-short（融資融券）、securities-lending（借券）、insider-holding（董監持股）、shareholder-count（集保戶數）、broker-branch（分點進出） |
| **台股特化（tw_specific/）** | 6 | day-trade-scanner（當沖）、corporate-action（除權息/現增減資）、etf-composition（0050/0056/00878）、concept-stock、warrant-analysis（權證）、sector-rotation |
| **量化／工具（quant/）** | 4 | ml-strategy（lightgbm）、screener、backtest-diagnose、report-generate |
| **組合／風控（portfolio/）** | 4 | portfolio-mvo、risk-parity、position-sizing、drawdown-monitor |

### 4.3 Tools 註冊表（`src/ohmystock/tools/_registry.py`）

- 用 decorator `@register_tool` 自動發現，對標 Vibe-Trading `src/agent/tools.py`。
- 每個 tool 為一個 Python module，提供 JSONSchema input/output。
- 規劃 **20 個 tool**(v3 由 17 → 20,新增 3 個閉環迴圈所需):

```
backtest_tool          paper_trade_tool         market_data_tool
fundamental_data_tool  chip_data_tool           screener_tool
portfolio_tool         pattern_recognition_tool swarm_tool
memory_tool            skill_writer_tool        session_search_tool
web_search_tool        read_url_tool            read_document_tool
write_file_tool        trade_journal_tool       risk_check_tool
news_sentiment_tool    post_trade_review_tool   proposal_tool   ← v3 新增
```

#### 4.3.1 `trade_journal_tool` schema（v3 擴充）

對應 cheatsheet §6.8 / §7.F。負責 LLM 決策、進場、出場、拒絕、過期的完整生命週期紀錄,寫 SQLite + FTS5。

```python
# 輸入動作分三類
record_decision(
    decision_id: str,
    kind: Literal["entry", "exit", "reject", "expire"],
    payload: dict  # 對應 cheatsheet §6.8 / §7.F 欄位
) -> {ok: bool, journal_id: str}

record_outcome(
    decision_id: str,        # 進場時寫的 ID
    outcome: dict            # exit_reason, exit_tag, pnl_pct, hold_days, thesis_held, vs_expected_holding
) -> {ok: bool}

query(
    filter: {
        period_from: ISO-8601,
        period_to: ISO-8601,
        symbol?: str,
        exit_tag?: list[str],
        thesis_held?: bool,
        ...
    }
) -> {trades: list[TradeJournalEntry]}
```

`payload` 欄位完整定義見 [`docs/llm-decision-schema.md`](llm-decision-schema.md)。

#### 4.3.2 `post_trade_review_tool`(v3 新增)

對應 cheatsheet §15。被 `post_trade_review_team` swarm 的各節點呼叫。

```python
start_review(
    period: {from: ISO-8601, to: ISO-8601},
    scope: Literal["stocks", "sectors", "patterns", "all"] = "all"
) -> {review_id: str, journal_count: int}

attribute_trade(
    trade_id: str
) -> {
    category: Literal[
        "thesis_held",
        "thesis_failed_but_profit",
        "thesis_failed_loss",
        "stop_saved",
        "time_stop_correct",
        "time_stop_wrong",
    ],
    evidence: str,
    counterfactual_5d: float,    # 出場後 5 日報酬
    counterfactual_10d: float,
    counterfactual_20d: float,
}

aggregate_metrics(
    review_id: str,
    by: list[Literal["entry_condition", "k_pattern", "sector", "exit_tag"]]
) -> {breakdown: dict[str, {win_rate: float, expectancy: float, n: int}]}

propose_change(
    target_section: str,         # 例 "cheatsheet §6.4"
    diff: str,                   # 改動 diff(unified format)
    evidence_refs: list[str]     # reviews/<period>/metrics.json 的 JSON pointer
) -> {proposal_id: str, path: str}
```

評分 / 歸因 rubric 見 [`docs/post-trade-review-rubric.md`](post-trade-review-rubric.md)。

#### 4.3.3 `proposal_tool`(v3 新增)

對應 cheatsheet §16。負責提案 CRUD + 觸發驗證閘 + 合併。

```python
create_proposal(
    title: str,
    target_section: str,
    diff: str,
    evidence_refs: list[str]
) -> {proposal_id: str, status: "pending"}

validate_proposal(
    proposal_id: str
) -> {
    status: Literal["validating", "approved", "rejected"],
    wfa_report: dict,            # 樣本內外 Sharpe、MDD、PF
    robust_report: dict,         # ±10% 鄰域 Sharpe 衰減
    golden_regression: dict,     # 0050 / 2330 / 0056 對照
    reasons?: list[str]          # rejected 時的失敗原因
}

merge_proposal(
    proposal_id: str,
    confirm_token: str           # 必須由 /api/proposals/{id}/merge 端點注入,LLM 不可自造
) -> {ok: bool, new_version: str}  # 例:"v3.1"

list_proposals(
    status?: Literal["pending", "validating", "approved", "rejected", "merged"]
) -> {proposals: list[Proposal]}
```

> ⚠️ **安全**：`merge_proposal` 必須由 REST API 端點 `/api/proposals/{id}/merge` 注入 `confirm_token`(來自人工 ConfirmDialog),LLM 直接呼叫 tool 會被拒絕。對應 §4.5 防線概念。

### 4.4 回測引擎（`src/ohmystock/backtest/`）

對標 Vibe-Trading `src/backtest/engines/a_shares.py`（A 股最接近台股結構），fork 後做台股特化。

#### 4.4.1 必須處理的台股市場細節

| 機制 | 處理方式 | 檔案 |
|---|---|---|
| **T+2 交割** | 買進當日不可賣出（除非當沖），帳上現金 T+2 才入帳 | `engine.py` |
| **±10% 漲跌停** | 限價單若打到漲跌停且委買/委賣量為 0 → 不成交。回測 fill 時用「成交量加權成交機率」模型 | `fills.py` |
| **IPO 蜜月期 5 日無漲跌幅** | 例外處理，無前一日收盤價，採承銷價計算 | `fills.py` |
| **盤中零股（09:10–13:30）** | 集合競價每分鐘撮合一次；vs 盤後零股（13:40–14:30）單次撮合。**MVP 僅支援整股，零股寫入 backlog** | — |
| **興櫃** | 議價、無漲跌停、無集合競價 → **回測標的池排除** | `universe.py` |
| **處置股票** | 預收款券 5 天 → 10 天 → 人工管制撮合（5/20 分鐘）→ 流動性大降，回測需限縮 fill | `fills.py` + `universe.py` |
| **全額交割股** | 100% 預收款券 → 模擬下單時瞬間扣減購買力 | `paper/state.py` |
| **除權（股數變動）vs 除息（現金）** | 必須**分別處理**：FinMind 還原股價只處理「除息」，「除權」需股數乘數調整 | `corporate_action.py` |
| **當沖稅率 0.15%（vs 一般 0.3%）** | 落日條款延長至 **2027/12/31**，硬編碼此日期並警示 | `costs.py` |
| **現股當沖券源** | 「先買後賣」一律可；「先賣後買」需 `Contract.day_trade` 旗標（Shioaji 提供） | `paper/shioaji_broker.py` |
| **平盤下放空限制** | 一般股已解除，但「注意 / 處置 / 警示股」仍受限 → 每日讀公告 gate | `universe.py` |
| **半日交易** | 除夕前一日、選舉日等，僅交易至 12:00。使用 TWSE 行事曆 | `calendar.py` |
| **暫停交易（重訊）** | FinMind 不標記 → 從 MOPS 公開資訊觀測站爬取 | `data/mops_scraper.py` |
| **早盤試撮（08:30–09:00）** | 產生「預估開盤價」，可作為策略訊號來源 | `engine.py` |

#### 4.4.1.1 Mark Minervini SEPA 在台股的本地化備註（v3.1 新增）

> 完整 SEPA 框架定義見 [`workflow-cheatsheet.md`](workflow-cheatsheet.md) §0.4 / §2 / §6.3 / §9.1（業務邏輯 SSOT）。本節僅記載與台股市場結構衝突 / 不對應的本地化決策，給後續 phase 寫程式時對照。

| Minervini 美股原版 | 台股本地化決策 | 理由 |
|---|---|---|
| RS Rating 門檻 ≥ 70（IBD 商業數據） | **RS Percentile ≥ 65**，自建（依 `market_data_tool.get_rs_percentile`） | 台股無 IBD 商業 RS，自建依 252 日加權（63d/126d/189d/252d 各 25%）；門檻下調是因台股流動股池較小（~1500 vs 美股 ~18000） |
| 流動性以 $ADV（美元日均成交額）計 | **5 日均成交額 ≥ NT$ 100M** 替代 | NT$ 100M ≈ USD $3M，等效 IBD 對小型成長股的流動性下限 |
| 停損 -7~8% | **沿用既有 §6.6 公式 -6% 下限**（`max(price × 0.94, price - 2 × ATR)`） | 台股 ±10% 漲跌停下，-7~8% 停損遇強波動可能因跌停打不出單 → 預留 4% 緩衝 |
| Earnings season 季 1/4/7/10 月 | **季報 8/2 月、月營收每月 10 號前公佈** | Phase 3 進場 SHALL 避開季報前 10 個交易日（防止財報前突發跳空）；月營收動能保留為 §3 Phase 1.5 觸發 |
| Position sizing 以 1% Fixed-Risk | **保留 §6.6 Volatility Targeting** | Vol Targeting 依個股 ATR% 反向縮放，台股漲跌停下對極端波動股自帶保護；Minervini Fixed-Risk 在小型高 ATR 股會下太重（v3 決策 #16） |
| Stage 4 個股可做空 | **不做空**（v1 paper trading + 後續即使 live 亦不做空） | Shioaji 模擬倉做空券源限制 + 平盤下放空法規限制；Stage 4 一律 hard reject 不進場 |

> **設計用意**：Minervini SEPA 三柱（Trend Template / Stage / VCP+Pivot）的**判讀邏輯不變**，只調整門檻與市場機制適配。Phase 5 復盤的提案閘（§16）會持續驗證這些本地化參數是否最佳。

#### 4.4.2 成本模型（`backtest/costs.py`）
- 手續費：0.1425% × 折扣率（預設 0.28，可調）
- 證交稅：賣出 0.3%（一般）/ 0.15%（當沖，至 2027/12/31）
- 滑價：依成交量百分比模擬

### 4.5 模擬下單（`src/ohmystock/paper/`）

> ⚠️ **本節已搬到** [`safety-and-simulation.md`](safety-and-simulation.md)（2026-04-26 docs reorg）
>
> 完整內容（防線 1-9 + verify_simulation + Shioaji SDK 限制 + 對賬機制）請見該檔。
>
> 章節對應：
> - 原 §4.5.0（防線 1-9 + 防線總表 + 給主管書面承諾）→ `safety-and-simulation.md` §1 + §2
> - 原 §4.5.0.1（verify_simulation.py 規格）→ `safety-and-simulation.md` §3
> - 原 §4.5.1（Shioaji 模擬倉真實限制）→ `safety-and-simulation.md` §4
> - 原 §4.5.2（對賬機制）→ `safety-and-simulation.md` §5

### 4.6 記憶與 Session（`src/ohmystock/memory/`）

- **跨 session 持久記憶**：檔案式（`~/.ohmystock/memory/`），對標 Vibe-Trading `src/memory/persistent.py`。
- **對話歷史搜尋**：SQLite + FTS5（直接 port Vibe-Trading `src/memory/sessions.py` schema）。
- **使用者偏好錨定**：例如「我偏好低本益比 + 高股息」自動回填到 system prompt。

#### 4.6.1 Trade Journal as Memory（v3 新增）

> 對應 cheatsheet §6.8 / §7.F / §15.2。每筆 trade-journal 條目寫入 FTS5 索引,**讓復盤 LLM 可以回查歷史相似情境**。

**FTS5 表結構** (`~/.ohmystock/memory/journal.db`):

> 📎 **完整 schema、欄位定義、entry/exit/reject/expire 4 種 record 範例見 [`llm-decision-schema.md` §4](llm-decision-schema.md#4-trade-journal-寫入-schemasqlite--fts5)（唯一權威 SSOT）。** 本節只說明 memory 層的整合語意。

**典型查詢場景**(由 `post_trade_review_team` 的歸因節點呼叫):

```python
# 找過去類似情境(VCP 突破 + 外資連買)
journal.search("VCP 突破 外資 連買", limit=20)

# 找全部 thesis 失效但賺錢的案例(學習矛盾訊號)
journal.query(thesis_held=False, pnl_pct__gt=0)

# 找特定型態的歷史命中率
journal.query(entry_pattern="VCP", exit_tag__in=["hit_t1", "hit_t1_5"])
```

**寫入時機**:
- LLM Decider 產出 decision → 寫 `kind=entry|reject`(待 confirm 期間 status=pending)
- Confirm Gate 通過 / 拒絕 → 更新 status
- Phase 4 出場 → 寫 `kind=exit` + 補完 outcome 欄位
- Confirm Gate timeout → 寫 `kind=expire`

### 4.7 Swarm 多代理人編排（`src/ohmystock/swarm/`）

- DAG 執行引擎；port Vibe-Trading `src/swarm/orchestrator.py`，把 LLM 呼叫端從 LangChain 換成 `ClaudeSDKClient` 子實例（每個子代理人持有 scoped tool subset）。
- **規劃 12 組預設 swarm**（YAML 在 `src/ohmystock/swarm/presets/`,v3 新增 2 組閉環迴圈用):

| 預設 | 流程 | 用途 |
|---|---|---|
| 投資委員會 | 多方/空方辯論 → 風控 → PM 結論 | 個股論點 |
| 當沖機會掃描團 | 即時量價異常 → 籌碼 → 風控 | 盤中 |
| 籌碼分析團 | 三大法人 + 融資融券 + 借券 + 分點 | 主力動向 |
| 季報研究團 | 財報解讀 + 修正 + 估值 | 財報季 |
| 產業輪動團 | 類股強弱 + 概念股 + ETF 成分 | 產業輪動 |
| 量化選股團 | 因子篩選 + 回測 + 風險審計 | 量化 |
| 技術分析合議團 | 古典 TA + 一目 + 諧波 + Elliott | 短線共識 |
| 風控委員會 | Drawdown + 尾端風險 + 政治經濟 | 風控簽核 |
| ETF 配置團 | 0050/0056/00878 等成分 + 配置 | 資產配置 |
| 主力跟單團 | 分點集中度 + 三大法人 + 借券 | 跟單策略 |
| **進場決策團** `entry_decision_team` (v3) | 多/空辯論 → cheatsheet §6.3/§6.4 條文比對 → Risk Gate 模擬 → PM 結論(輸出 §6.5 schema) | Phase 3 LLM Decider(自動觸發) |
| **交易復盤團** `post_trade_review_team` (v3) | 資料 → 歸因 → 聚合 → 批判 → 提案(對應 cheatsheet §15.2 五節點) | Phase 5 月度/季度復盤 |

#### 4.7.0 Phase 2B → Swarm Input Assembler

> 🔖 **本節為 Phase 2B 候選 → entry_decision_team 輸入組裝邏輯的唯一權威。**
> Output 型別 = [`llm-decision-schema.md` §1](llm-decision-schema.md#1-llm-decider-輸入-schema)（嚴格符合）。

**Owner：** `src/ohmystock/swarm/runner.py::build_entry_decision_input()`

**Signature：**

```python
def build_entry_decision_input(
    candidate: Phase2BCandidate,           # Phase 2B scoring 輸出（score ≥ 65）
    portfolio_state: PortfolioSnapshot,    # 來自 portfolio_tool.get_positions()
    market_state: MarketSnapshot,          # 來自 market_data_tool.get_index() 多檔
    rules_summary: RulesDigest,            # 從 cheatsheet §6.3/§6.4 預先抽出的 LLM 可讀摘要
) -> EntryDecisionInput:                   # 等於 llm-decision-schema.md §1 的 JSON
    """
    把 Phase 2B 篩出的候選 + 當下市場狀態 + 投組狀態組成一份 LLM 看得懂的 prompt context。
    嚴格產生符合 llm-decision-schema §1 的物件，由 entry_decision_team 各 node 共享。
    """
```

**欄位來源對照表：**

| `EntryDecisionInput` 欄位 | 來源 |
|---|---|
| `candidate_snapshot.symbol / score / pattern / pattern_evidence` | `Phase2BCandidate`（`strategies/_phase2b/scoring.py` 輸出） |
| `candidate_snapshot.chip_summary / news_summary` | 預先呼叫 `chip_data_tool` + `news_sentiment_tool` 並摘要（避免每個 LLM node 都重複 fetch） |
| `market_context.index_state` | `market_data_tool.get_index("TAIEX")` |
| `market_context.risk_off_active` | `strategies/risk_gate.py::evaluate()` preview |
| `market_context.existing_positions` | `portfolio_tool.get_positions()` 過濾出 sector + symbol + sizing_pct |
| `market_context.consecutive_loss_streak` | `trade_journal_tool.query` 近 N 筆 exit + 計算 |
| `rules_summary.must_have / bonus / sizing_formula_ref` | 從 cheatsheet §6.3/§6.4/§6.6 抽出（可在啟動時 cache） |
| `available_tools` | 從 `tools/_registry.py` 動態列舉（讓 LLM 知道能呼叫什麼） |
| `available_skills` | 從 `skills/` YAML frontmatter 抽 name + description |

**呼叫時機：** `swarm/runner.py::start_swarm("entry_decision_team", params={"candidate_id": ...})` 內部第一步。

**契約測試：** 產出物必須通過 `pydantic` validation 對 `EntryDecisionInput`（`models/decision.py` 待建）；schema 與 `llm-decision-schema.md` §1 範例 JSON 等價。

---

#### 4.7.1 進場決策團 `entry_decision_team`(v3)

對應 cheatsheet §6。Phase 2B 篩出 ≥ 65 候選後**系統自動觸發**(非使用者手動)。

```yaml
# src/ohmystock/swarm/presets/entry_decision_team.yaml
nodes:
  bull_analyst:        # 多方分析
    model: claude-sonnet-4-6
    skills: [technical/breakout, technical/ma-crossover, chip/three-major-investors]
    output: 多方論點 + 引用條文

  bear_analyst:        # 空方反方
    model: claude-sonnet-4-6
    skills: [chip/securities-lending, chip/insider-holding]
    output: 空方反證 + 風險因子

  rule_checker:        # cheatsheet 條文逐項比對
    model: claude-haiku-4-5  # 規則比對不需大模型
    inputs_from: [bull_analyst, bear_analyst]
    output: must_have_check[3] + bonus_score(0-8)

  risk_simulator:      # 模擬 Risk Gate / Sizing 結果
    model: claude-haiku-4-5
    tools: [risk_check_tool, portfolio_tool]
    output: risk_flags + projected_sizing

  pm_conclusion:       # PM 收斂為 §6.5 schema
    model: claude-opus-4-7  # 最終決策用最強模型
    inputs_from: [rule_checker, risk_simulator]
    output: LLMDecision(§6.5 完整 schema)

dag:
  - [bull_analyst, bear_analyst]    # 並行
  - rule_checker
  - risk_simulator
  - pm_conclusion                    # 收斂

token_budget:
  max_input_tokens: 30000
  max_output_tokens: 4000
```

#### 4.7.2 交易復盤團 `post_trade_review_team`(v3)

對應 cheatsheet §15。月底自動 + 人工任意觸發。

```yaml
# src/ohmystock/swarm/presets/post_trade_review_team.yaml
nodes:
  data_loader:
    model: claude-haiku-4-5
    tools: [trade_journal_tool, market_data_tool]
    output: 區間 trade-journal + 出場後 5/10/20 日報酬

  attributor:
    model: claude-sonnet-4-6
    inputs_from: [data_loader]
    tools: [post_trade_review_tool.attribute_trade]
    output: 逐筆歸因(6 類)

  aggregator:
    model: claude-sonnet-4-6
    inputs_from: [attributor]
    tools: [post_trade_review_tool.aggregate_metrics]
    output: 各維度命中率 / 期望值 / PF / MDD

  critic:
    model: claude-opus-4-7   # 批判需要深度推理
    inputs_from: [aggregator]
    skills: [全部 cheatsheet 章節作為知識庫]
    output: 標記勝率/期望值偏低的條件

  proposer:
    model: claude-opus-4-7
    inputs_from: [critic]
    tools: [post_trade_review_tool.propose_change]
    output: proposals/*.md(diff + 佐證)

dag:
  - data_loader
  - attributor
  - aggregator
  - critic
  - proposer

token_budget:
  max_input_tokens: 100000
  max_output_tokens: 16000
```

### 4.8 Backend：FastAPI 服務（`src/ohmystock/api/`）

對標 Vibe-Trading `agent/api_server.py`，重新以 FastAPI + Claude Agent SDK async 介面設計。

#### 4.8.1 服務分層架構

```
┌──────────────────────────────────────────────────────────┐
│              Routers（路由層）                            │
│  /runs   /sessions   /swarm   /backtest   /paper         │
│  /skills /tools      /memory  /market     /system        │
└────────────────────────────┬─────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────┐
│              Services（業務邏輯層）                       │
│  RunService  SessionService  SwarmService                │
│  BacktestService  PaperService  MarketService            │
└────────────────────────────┬─────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────┐
│              Adapters（適配層）                           │
│  ClaudeSDKAdapter  ShioajiAdapter  FinMindAdapter        │
└────────────────────────────┬─────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────┐
│              Repositories（資料層）                       │
│  SQLite (sessions/runs/orders) + Parquet (價量歷史)       │
└──────────────────────────────────────────────────────────┘
```

#### 4.8.2 REST API 端點清單

| Method | Path | 說明 | 回傳 |
|---|---|---|---|
| `POST` | `/api/runs` | 建立新對話回合（建立 run id，啟動 agent loop） | `{run_id, session_id}` |
| `GET` | `/api/runs/{run_id}` | 取得 run 元資料與最終訊息 | `Run` |
| `GET` | `/api/runs/{run_id}/stream` | **SSE** 串流 token / tool-call / tool-result | event-stream |
| `POST` | `/api/runs/{run_id}/cancel` | 中止執行中的 run | `204` |
| `GET` | `/api/sessions` | 列出 session（分頁、可搜尋） | `Page<Session>` |
| `GET` | `/api/sessions/{id}` | 單 session 完整訊息歷史 | `Session` |
| `DELETE` | `/api/sessions/{id}` | 刪除 session | `204` |
| `GET` | `/api/sessions/search?q=...` | FTS5 全文搜尋 | `Hit[]` |
| `POST` | `/api/swarm/{preset}` | 啟動 swarm（如 `investment_committee`） | `{run_id, dag}` |
| `GET` | `/api/swarm/{run_id}/dag` | 取得 DAG 狀態樹 | `DagState` |
| `POST` | `/api/backtest` | 提交回測任務（背景執行） | `{job_id}` |
| `GET` | `/api/backtest/{job_id}` | 回測進度 / 結果 | `BacktestResult` |
| `POST` | `/api/paper/orders` | 模擬下單（**需先呼叫 confirm**） | `Order` |
| `POST` | `/api/paper/orders/confirm` | 人工確認下單 token | `{confirmed: true}` |
| `GET` | `/api/paper/positions` | 目前模擬部位 | `Position[]` |
| `GET` | `/api/paper/orders` | 委託單清單 | `Order[]` |
| `GET` | `/api/paper/equity?from=&to=` | 權益曲線 | `EquityPoint[]` |
| `GET` | `/api/skills` | 列出全部 skill（含分類） | `Skill[]` |
| `GET` | `/api/skills/{name}` | 取得 skill YAML 原文 | `SkillDetail` |
| `POST` | `/api/skills` | 使用者新增 skill | `Skill` |
| `GET` | `/api/tools` | 列出已註冊 tool | `Tool[]` |
| `GET` | `/api/memory` | 列出長期記憶條目 | `Memory[]` |
| `POST` | `/api/memory` | 新增記憶 | `Memory` |
| `DELETE` | `/api/memory/{id}` | 刪除記憶 | `204` |
| `GET` | `/api/market/quote?symbol=2330` | 即時報價（Shioaji） | `Quote` |
| `GET` | `/api/market/kline?symbol=2330&tf=D` | K 線歷史 | `Bar[]` |
| `GET` | `/api/market/chip?symbol=2330&from=&to=` | 三大法人 / 融資融券 | `Chip[]` |
| `GET` | `/api/market/universe?market=TWSE` | 標的清單（含處置/警示旗標） | `Stock[]` |
| `GET` | `/api/system/health` | 健康檢查（DB / Shioaji / FinMind） | `HealthStatus` |
| `GET` | `/api/system/audit?date=` | 取當日 audit log（管理員） | `AuditEntry[]` |
| `GET` | `/api/decisions?status=pending` | **(v3)** LLM 待 confirm 決策清單 | `Decision[]` |
| `GET` | `/api/decisions/{id}` | **(v3)** 單筆決策 + reasoning + tool calls | `DecisionDetail` |
| `POST` | `/api/decisions/{id}/confirm` | **(v3)** 人工 confirm 送單(必須 isTrusted + ConfirmDialog token) | `Order` |
| `POST` | `/api/decisions/{id}/reject` | **(v3)** 人工拒單 + 拒絕原因 | `204` |
| `GET` | `/api/decisions/{id}/journal` | **(v3)** 取得對應 journal 條目 | `JournalEntry` |
| `POST` | `/api/reviews` | **(v3)** 觸發復盤(指定區間 + scope) | `{review_id}` |
| `GET` | `/api/reviews/{id}` | **(v3)** 復盤結果(report.md + metrics + 提案) | `ReviewResult` |
| `GET` | `/api/reviews?period=` | **(v3)** 列出歷史復盤 | `Review[]` |
| `GET` | `/api/proposals?status=` | **(v3)** 提案列表(可依 status 過濾) | `Proposal[]` |
| `GET` | `/api/proposals/{id}` | **(v3)** 提案詳情 + WFA 結果 | `ProposalDetail` |
| `POST` | `/api/proposals/{id}/validate` | **(v3)** 觸發 WFA + Robust 驗證閘 | `{job_id}` |
| `POST` | `/api/proposals/{id}/merge` | **(v3)** 合併 cheatsheet(必須 confirm_token + ConfirmDialog) | `{new_version}` |
| `POST` | `/api/proposals/{id}/reject` | **(v3)** 拒絕提案 + 原因 | `204` |

#### 4.8.3 SSE 串流協定（`/api/runs/{run_id}/stream`）

事件型別與 Claude Agent SDK 訊息對齊，前端按 `event:` 分流：

```
event: token
data: {"text": "根據 2330 最新一季..."}

event: tool_call
data: {"id": "tu_1", "name": "chip_data_tool", "input": {"symbol": "2330"}}

event: tool_result
data: {"id": "tu_1", "ok": true, "output": {...}, "elapsed_ms": 312}

event: thinking
data: {"text": "..."}

event: swarm_node
data: {"node": "bull", "status": "running", "progress": 0.3}

event: error
data: {"code": "RATE_LIMIT", "message": "FinMind 額度耗盡"}

event: done
data: {"finish_reason": "stop", "usage": {"in": 4521, "out": 832}}
```

> 為避免 SSE 連線在企業 Proxy 被截斷，每 15 秒送 `event: ping`。

#### 4.8.4 SQLite Schema（核心表）

```sql
-- 對話 session
CREATE TABLE sessions (
  id           TEXT PRIMARY KEY,
  title        TEXT,
  created_at   INTEGER,
  updated_at   INTEGER,
  preset       TEXT,           -- swarm preset 或 NULL
  meta_json    TEXT
);

-- run（單次對話回合）
CREATE TABLE runs (
  id           TEXT PRIMARY KEY,
  session_id   TEXT REFERENCES sessions(id) ON DELETE CASCADE,
  status       TEXT,           -- queued|running|done|error|cancelled
  started_at   INTEGER,
  ended_at     INTEGER,
  in_tokens    INTEGER,
  out_tokens   INTEGER,
  error        TEXT
);

-- 訊息（含 tool_use / tool_result）
CREATE TABLE messages (
  id           TEXT PRIMARY KEY,
  run_id       TEXT REFERENCES runs(id) ON DELETE CASCADE,
  role         TEXT,           -- user|assistant|tool
  content_json TEXT,
  ts           INTEGER
);

-- FTS5 全文索引（對 messages.content 建立）
CREATE VIRTUAL TABLE messages_fts USING fts5(
  content, run_id UNINDEXED, ts UNINDEXED,
  tokenize='unicode61'
);

-- 模擬部位（本地為 source of truth）
CREATE TABLE paper_positions (
  symbol       TEXT PRIMARY KEY,
  qty          INTEGER,
  avg_cost     REAL,
  realized_pnl REAL,
  updated_at   INTEGER
);

-- 模擬委託 / 成交
CREATE TABLE paper_orders (
  id           TEXT PRIMARY KEY,
  symbol       TEXT,
  side         TEXT,           -- buy|sell
  order_type   TEXT,           -- ROD|IOC|FOK
  qty          INTEGER,
  price        REAL,
  status       TEXT,           -- pending|filled|cancelled|rejected
  shioaji_id   TEXT,
  is_day_trade INTEGER,
  ts_submit    INTEGER,
  ts_fill      INTEGER
);

-- 稽核日誌（同時 append-only JSONL，雙寫）
CREATE TABLE audit_log (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  ts           INTEGER,
  kind         TEXT,           -- prompt|tool_call|tool_result|order|login
  payload_json TEXT
);

-- 回測結果快取
CREATE TABLE backtest_jobs (
  id           TEXT PRIMARY KEY,
  spec_json    TEXT,
  status       TEXT,
  metrics_json TEXT,
  equity_path  TEXT,           -- Parquet 檔案路徑
  created_at   INTEGER
);
```

#### 4.8.5 背景任務模型

| 任務類型 | 執行方式 | 理由 |
|---|---|---|
| Agent run（短，<5 分鐘） | `asyncio.create_task` + SSE 推送 | 互動性，無需 queue |
| Backtest（長，可能 >5 分鐘） | **`arq`（Redis-backed async queue）** | 可分散、可重試、可中止；避免阻塞 FastAPI worker |
| 每日資料 ETL（FinMind 收盤後抓） | `arq` cron + 自寫 scheduler fallback | 收盤後 19:00 / 20:00 觸發 |
| Shioaji 對賬 | APScheduler（每日 14:30 收盤後） | 輕量、不需 Redis |
| MOPS 重訊監控 | 獨立 worker，SSE push 給前端 | 盤中即時 |

> **MVP 簡化**：Phase 2 前可以全用 `asyncio` + APScheduler；Redis/arq 在 Phase 4 引入。

#### 4.8.6 鑑權與設定

- **個人 localhost 使用**：FastAPI bind `127.0.0.1` 即可，不暴露外網；可選擇加 `X-API-Key` header（自己定義）防止本機其他程式誤呼叫，但個人單機無此需求。
- **不引入 OAuth2 / ToS 同意彈窗**（無多人 / 對外場景；若未來真的要對外，再評估 SITC 投顧執照 + PDPA 等議題，那是另一個專案）。
- **設定管理**：`pydantic-settings` 從 `.env` 讀取，型別安全；機敏欄位（Shioaji secret、CA 密碼）走 `cryptography.fernet` + OS keyring。

#### 4.8.7 錯誤處理 / 觀測性（個人版）

- **統一錯誤 envelope**：`{"code": "...", "message": "...", "details": {...}}`，HTTP 狀態碼語意正確（400/401/403/404/409/500）。
- **不加 IP rate limit**（單一使用者；保留 Shioaji / FinMind / Anthropic 各 SDK 自帶的 client-side throttling 即可）。
- **結構化日誌**：`structlog` JSON 寫到 `~/.ohmystock/logs/*.jsonl`，每行帶 `request_id` / `run_id` / `session_id`。Tail + grep 即可，不需要 OpenTelemetry / Jaeger / Datadog（個人專案；若未來成本 / 效能成議題再評估）。
- **OpenAPI 文件**：FastAPI 自動產出，路徑 `/docs`（Swagger）與 `/redoc`。

---

### 4.9 Frontend：兩專案 monorepo（`web-admin/` + `web-public/`）

> ⚠️ **2026-04-27 update：** v3 把網頁拆為**前後台兩專案 monorepo**：
>
> | 專案 | 文件 | 對象 | 範圍 |
> |---|---|---|---|
> | **`web-admin/`** | [`frontend.md`](frontend.md) | 用戶本人（auth） | 18 頁完整工作介面（Dashboard / Chat / Backtest / Paper / Settings / Audit 等） |
> | **`web-public/`** | [`frontend-public-pixel.md`](frontend-public-pixel.md) | 任何訪客（無認證、masked） | pixel 像素辦公室 demo（9 角色擬人化呈現 LLM 工作流） |
>
> 對應 backend：[`backend-eventbus.md`](backend-eventbus.md)（EventBus + AdminEventSerializer / MaskedEventSerializer 雙通道）
> 認證與 mask 策略：[`auth-and-mask.md`](auth-and-mask.md)
>
> ---
>
> **舊 §4.9 完整內容已搬到** [`frontend.md`](frontend.md)（2026-04-26 docs reorg）。
> 章節對應：原 §4.9.1 → `frontend.md` §1；§4.9.2 → §2；§4.9.3 → §3；§4.9.4 → §4；§4.9.5 → §5；§4.9.6 → §6；§4.9.7 → §7；§4.9.8 → §8；§4.9.9 → §9；§4.9.10 → §10；§4.9.11 → §11；§4.9.12 → §12；§4.9.13 → §13；§4.9.14 → §14；§4.9.15 → §15；§4.9.16 → §16；§4.9.17 → §17；§4.9.18 → §18。


### 4.10 交易策略（Trading Strategies）— `src/ohmystock/strategies/`

> 🔖 **權威來源（Single Source of Truth）**：
> 本節說明策略**架構與介面設計**（Protocol / Sizing / Risk Gate / 目錄結構）。
> **具體交易邏輯**（選股漏斗、進場條件、停損停利、部位管理、風險閘、評分公式、排程觸發）一律以 [`docs/workflow-cheatsheet.md`](workflow-cheatsheet.md) 為準。
>
> 程式實作時，每支 `strategies/*.py` 檔案頂端**必須註解標示**對應 `workflow-cheatsheet.md` 章節（如「實作 §6 Phase 3 進場條件」），確保程式 ↔ 文件雙向可追溯。

策略是整套系統的「業務核心」，獨立於 Skills（給 LLM 讀的說明）與 Tools（API 包裝）之外，**直接對接回測引擎與模擬下單**。

#### 4.10.1 兩種策略表達方式

| 形式 | 路徑 | 描述 | 適用情境 |
|---|---|---|---|
| **Code-based 策略** | `src/ohmystock/strategies/` | Python 類別實作 `Strategy` Protocol，**確定性、可重現、可回測** | 量化策略、需嚴格回測的長期持倉 |
| **LLM-driven 策略** | `src/ohmystock/skills/technical/` 等 | YAML+Markdown，描述邏輯供 Agent 動態組合與決策 | 主觀分析、跨資料源綜合判斷、對話式交易 |
| **混合（Hybrid）** | LLM 呼叫 code-based 策略產出訊號，自己做最後過濾 | 兩者橋接 | 「給我外資連買 5 日 + 月營收年增 > 20% 的標的」 |

> **設計含義**：兩者並非二選一。Code 策略提供「可審計的訊號函式」；Skill 提供「LLM 怎麼用這個訊號的說明」。同一概念（如均線交叉）通常**同時存在**：`strategies/technical/ma_crossover.py`（程式）+ `skills/technical/ma-crossover.md`（給 LLM 的提示）。

#### 4.10.2 Strategy Protocol（介面）

```python
# src/ohmystock/strategies/base.py
from typing import Protocol, runtime_checkable
from dataclasses import dataclass

@dataclass
class Bar:
    symbol: str
    ts: int                  # epoch ms
    open: float; high: float; low: float; close: float
    volume: int

@dataclass
class Signal:
    symbol: str
    side: str                # 'long' | 'short' | 'flat'
    strength: float          # 0~1，供 sizing 使用
    reason: str              # 必填，會寫入 audit log
    meta: dict | None = None

@runtime_checkable
class Strategy(Protocol):
    name: str
    params: dict             # 可序列化參數（dataclass / pydantic 皆可）

    def on_init(self, ctx: "StrategyContext") -> None: ...
    def on_bar(self, bar: Bar, ctx: "StrategyContext") -> list[Signal]: ...
    def on_fill(self, order, ctx: "StrategyContext") -> None: ...
    def on_close(self, ctx: "StrategyContext") -> None: ...
```

`StrategyContext` 提供：universe（標的池）、portfolio（當前部位）、capital（可用資金）、risk_limits（風控上限）、data（歷史視窗存取）、logger。

#### 4.10.3 信號 → 下單管線(v3 重構,加入 LLM Decider 與 Confirm Gate)

```
┌──────────┐  raw_signal  ┌─────────────────────┐  decision  ┌──────────┐
│ Strategy │ ───────────▶ │ LLM Decider          │ ─────────▶ │ Sizing   │
│ on_bar() │              │ entry_decision_team  │            │ Policy   │
└──────────┘              │ swarm (§4.7.1)       │            │ (覆寫    │
                          │ 輸出 §6.5 schema     │            │ LLM 提案)│
                          └─────────────────────┘            └────┬─────┘
                                                                   │ target%
                                                                   ▼
                                                            ┌──────────────┐
                                                            │ Risk Gate    │
                                                            │ (處置/警示/  │
                                                            │  漲跌停/上限)│
                                                            └──────┬───────┘
                                                                   │ approved
                                                                   ▼
                                                            ┌──────────────────┐
                                                            │ Confirm Gate     │
                                                            │ AUTO_EXECUTE     │
                                                            │ false → 人工 UI  │
                                                            │ true → 防線9熔斷 │
                                                            └──────┬───────────┘
                                                                   │ ack
                                                                   ▼
                                                            ┌──────────┐
                                                            │ Broker   │
                                                            │ (paper / │
                                                            │  live)   │
                                                            └────┬─────┘
                                                                 │ ack
                                                                 ▼
                                                ┌──────────────────────────┐
                                                │ Trade Journal Service    │
                                                │ SQLite + FTS5 索引       │
                                                │ (decision/order/outcome) │
                                                └──────────────────────────┘
```

**各層責任**：
- **LLM Decider**(v3 新增,`swarm/presets/entry_decision_team.yaml`)：讀規則 + 看數據 + 引用 skill,輸出 cheatsheet §6.5 嚴格 schema(decision / confidence / must_have_check / bonus_score / proposed_sizing_pct / reasoning / cited_skills / invalidation_conditions / risk_flags)。
- **Sizing Policy**（`strategies/sizing.py`）：實作 [`workflow-cheatsheet.md` §6.6 Volatility Targeting 公式](workflow-cheatsheet.md#position-sizingvolatility-targeting系統公式)（**唯一權威**）；LLM 提案 vs 公式取**較小**者(LLM 不可放大)；ATR 停損價系統強算 LLM 不可覆寫（公式同上 §6.6）。
- **Risk Gate**（`strategies/risk_gate.py`）：硬性過濾——處置股 / 警示股 / 全額交割股 / 漲跌停無法成交 / 違反單檔上限 / 違反總槓桿上限 → **直接拒單,原因寫 audit log + Trade Journal**。LLM 無法覆蓋。
- **Confirm Gate**(v3 新增)：依 `OHMYSTOCK_AUTO_EXECUTE` 切換。false 寫入 pending decisions 佇列等人工 confirm;true 過 §4.5 防線 9 熔斷後直接送單。Live 模式強制 false。
- **Broker Adapter**：Paper（Shioaji simulation）或 Backtest（回測引擎內建撮合）。同一支策略**毋須改碼**即可在回測 / 模擬 / 實單之間切換。
- **Trade Journal Service**(v3 新增,§4.6.1)：每階段都寫 SQLite + FTS5,供 §4.7.2 復盤 swarm 回查。

#### 4.10.4 內建策略庫（v1 MVP 主軸 + v2 擴充）

> ⚙️ **MVP 主軸策略**：`tw_momentum_swing`（短線動能 swing），完整實作 [`workflow-cheatsheet.md`](workflow-cheatsheet.md) 全部 17 章節邏輯（含 v3 §15 LLM 復盤 / §16 提案合併迴圈）。其他策略視業務需求迭代加入。

| 類別 | 策略 | 核心邏輯 | 對應 Skill | 狀態 |
|---|---|---|---|---|
| **MVP 主軸** | `tw_momentum_swing` | **依 workflow-cheatsheet.md 全文實作**（漏斗篩選 + 評分 + 三 must-have + ATR 停損 + 核心衛星出場 + 風險閘 + 月度熔斷 + **LLM Decider 自動決策 + Confirm Gate + 月度復盤迴圈**） | `tw_specific/momentum-swing` | **必做** |
| **技術面** | `ma_crossover` | 20/60 日均線金叉買、死叉賣（baseline 對照組） | `technical/ma-crossover` | P1 |
| | `vcp_breakout` | VCP / 杯柄 / 平台突破（William O'Neil 系） | `technical/breakout` | P1 |
| | `turtle_breakout` | 海龜 20/55 日突破 + ATR 加碼 | `technical/breakout` | P2 |
| **基本面** | `low_pe_high_yield` | 低本益比 + 高殖利率 + ROE > 10% | `fundamental/valuation-pe-pb` | P2 |
| | `earnings_surprise` | SUE > 1.5σ 後持有 60 日 | `fundamental/eps-forecast` | P2 |
| **籌碼面** | `foreign_buy_streak` | 外資連買 N 日 + 量能放大 | `chip/three-major-investors` | P1 |
| | `broker_concentration` | 主力分點集中度 ≥ 25%（cheatsheet §2 量化定義） | `chip/broker-branch` | P1 |
| | `securities_lending_squeeze` | 借券餘額爆增 + 強制回補逼近（**空頭策略**） | `chip/securities-lending` | P2 |
| **台股特化** | `monthly_revenue_momentum` | 月營收 YoY > 30% + MoM > 10% + 新高（cheatsheet §3） | `tw_specific/monthly-revenue` | **必做** |
| | `dividend_run` | 除權息前布局 + 填息機率 | `tw_specific/corporate-action` | P2 |
| | `disposal_rebound` | 處置解除後反彈（高風險、嚴格停損） | `tw_specific/day-trade-scanner` | P3 |
| **機器學習** | `lgbm_multifactor` | LightGBM 多因子（價量 + 籌碼 + 基本面）月頻 rebalance | `quant/ml-strategy` | P3 |

> 每支策略 **必備**：`README.md`（中文說明 + 對應 cheatsheet 章節）、`params.py`（可調參數）、`tests/`（黃金樣本回測）、`notebooks/`（研究底稿）。

#### 4.10.5 參數管理 / 最佳化 / Walk-Forward / LLM 邏輯最佳化（v3 擴充）

##### 參數最佳化(沿用)
- **參數**：`pydantic.BaseModel`，自動產出 JSON Schema 給前端表單渲染。
- **回測網格**：`backtest_tool` 接受 `param_grid`，內部用 `itertools.product` 展開。
- **最佳化**：`Optuna` TPE，目標函式可選 Sharpe / Sortino / Calmar / 自訂。
- **Walk-Forward Analysis（WFA）**：避免過度擬合的核心防線。預設 5 年訓練 / 1 年測試、滾動 1 年；報告**樣本內 vs 樣本外**績效落差，落差 > 30% 視為過擬合警示。
- **Robust 測試**：每組最佳參數套 ±10% 鄰域擾動，看 Sharpe 衰減；衰減 > 50% 表參數不穩。

##### LLM 邏輯最佳化迴圈(v3 新增)

> **定位差異**:Optuna 只能調**現有規則的數字**(如 ATR 倍數 1.5→2.0);LLM 邏輯最佳化處理**規則本身**的演進(條件、門檻、新增 / 移除規則)。兩者互補。

```
Trade Journal(§4.6.1)
    │
    ▼
Post-Trade Review Service(§3 / §4.7.2)
    │ post_trade_review_team swarm
    │ 五節點:資料→歸因→聚合→批判→提案
    ▼
proposals/<YYYY-MM-DD>-<topic>.md
    │ status=pending
    ▼
Proposal Validation Service(§3)
    │ WFA + Robust + 黃金樣本回歸(沿用上方參數最佳化的驗證閘)
    ▼
status=approved | rejected
    │
    ▼ (approved)
人工 PR review(透過 /api/proposals/{id}/merge)
    │ confirm_token + ConfirmDialog
    ▼
合併 cheatsheet & 對應 strategy code 註解 + bump 版本
    │
    └─── (下一輪迴圈) ───►  Phase 0 Risk Gate
```

**安全約束**:
- LLM **不可** 直接 commit cheatsheet(`proposal_tool.merge_proposal` 必須由 REST API 注入 confirm_token)
- 自動寫入會被 hook 攔截,只能寫 `proposals/` 與 `reviews/` 目錄
- 人工 review 與 merge 都會寫 audit log,可回溯

**LLM 邏輯最佳化的觸發**:
- 自動:每月 1 號 / 季底
- 手動:CLI `uv run ohmystock review --from <date> --to <date>`
- 強制:月度熔斷觸發後(對應 cheatsheet §0「-8% 全平 + 強制復盤」)

詳見 cheatsheet §15(復盤迴圈)、§16(提案 → 驗證 → 合併工作流)。

#### 4.10.6 策略 ↔ Skill ↔ Tool ↔ Swarm 對應關係

```
┌─────────────────┐         ┌──────────────────┐
│ Strategy (code) │◀────────│ backtest_tool    │ ← LLM 呼叫
│ on_bar()        │         │ paper_trade_tool │ ← LLM 呼叫
└─────────────────┘         └────────┬─────────┘
       ▲                             │
       │ 描述 / 使用說明               │ 透過 Tool
       │                             ▼
┌─────────────────┐         ┌──────────────────┐
│ Skill (.md)     │◀────────│ Agent (Claude)   │
│ 自然語言提示     │         │  讀 Skill，呼叫   │
└─────────────────┘         │  Tool 跑策略      │
                            └────────┬─────────┘
                                     │ 多代理人時
                                     ▼
                            ┌──────────────────┐
                            │ Swarm DAG        │
                            │ 例：投資委員會    │
                            │ 多人辯論同一策略  │
                            └──────────────────┘
```

**具體例子（使用者：「跑外資連買策略找標的」）**：
1. Agent 讀 `skills/chip/three-major-investors.md` 知道有此策略
2. Agent 呼叫 `screener_tool` + `chip_data_tool` 找候選池
3. Agent 呼叫 `backtest_tool` 並指定 `strategy="foreign_buy_streak"`
4. 回測引擎載入 `strategies/chip/foreign_buy_streak.py` 執行
5. 結果經 Risk Gate 過濾後產出建議清單
6. 使用者在前端 `<OrderForm>` 二次確認後，`paper_trade_tool` 送 Shioaji 模擬倉

#### 4.10.7 策略目錄結構

```
src/ohmystock/strategies/
├── base.py                      # Strategy Protocol、Bar、Signal、Context
├── registry.py                  # @register_strategy decorator + 自動發現
├── sizing.py                    # SizingPolicy（固定/ATR/Kelly/Risk Parity）
├── risk_gate.py                 # 硬性風控閘
├── optimize.py                  # Optuna / WFA wrapper
├── technical/
│   ├── ma_crossover.py
│   ├── kd_divergence.py
│   ├── bollinger_breakout.py
│   ├── turtle_breakout.py
│   └── atr_channel.py
├── fundamental/
│   ├── low_pe_high_yield.py
│   ├── roe_gross_margin.py
│   └── earnings_surprise.py
├── chip/
│   ├── foreign_buy_streak.py
│   ├── trust_pick_up.py
│   ├── margin_decrease_price_up.py
│   ├── broker_concentration.py
│   └── securities_lending_squeeze.py
├── tw_specific/
│   ├── dividend_run.py
│   ├── monthly_revenue_momentum.py
│   ├── quarter_window_dressing.py
│   ├── disposal_rebound.py
│   └── ipo_honeymoon_fade.py
├── ml/
│   ├── lgbm_multifactor.py
│   └── features/                # 因子產生器
└── _docs/                       # 每支策略的 README + notebook
```

#### 4.10.8 策略開發 SOP（給開發者）

1. 在 `strategies/<category>/<name>.py` 新增繼承 `Strategy` 的類別
2. `@register_strategy("name")` 裝飾器自動納入登錄表
3. 同步在 `skills/<category>/<name>.md` 寫對應 LLM 使用說明
4. `tests/strategies/test_<name>.py` 寫至少 3 組黃金樣本（牛市 / 熊市 / 盤整）
5. `notebooks/strategies/<name>.ipynb` 放研究底稿與圖表
6. 跑 `uv run ohmystock backtest --strategy <name> --wfa` 通過 WFA 才合併
7. 列入下次 swarm preset 的候選池

---

### 4.11 Shioaji API 整合計畫（永豐金證券）

> 📚 **文件來源**：[sinotrade.github.io](https://sinotrade.github.io/) ｜ **SDK 版本**：Shioaji ≥ 1.2 ｜ **語言**：Python（C# 另有，本專案採 Python）

#### 4.11.1 Shioaji 能力總覽 → 專案需求對應

| Shioaji 模組 | 我方使用點 | 對應專案檔案 |
|---|---|---|
| **Login（api_key + secret_key）** | 啟動時連線、簽署狀態檢查 | `paper/shioaji_broker.py` |
| **Contracts（股 / 期 / 選 / 權證）** | 標的池、`day_trade` 旗標、處置/警示 | `data/universe.py` + `paper/shioaji_broker.py` |
| **Quote.subscribe（Tick / BidAsk）** | 即時行情、盤中強勢股掃描（§4.10 Phase 2A） | `data/shioaji_quote.py` |
| **Quote-Binding Mode** | 高頻場景 batch 訂閱 | 同上 |
| **Snapshot API** | 一次撈多檔即時快照（dashboard） | `data/shioaji_quote.py` |
| **Scanners（漲跌幅 / 量能排行）** | Phase 2A 11:00/13:00 強勢股掃描 | `tools/screener_tool.py` |
| **Disposition / Attention 公告** | universe 處置警示旗標、Risk Gate | `data/universe.py` |
| **Short Stock Source** | 借券券源檢查、Phase 3 進場前置 | `data/chip_data.py` |
| **Credit Enquiries** | 融資融券餘額即時查詢 | 同上 |
| **place_order（Stock / Future）** | Paper 階段：模擬下單；Live 階段：真實下單 | `paper/shioaji_broker.py` |
| **Touch Price Order** | 預掛停損 / 突破單 | `paper/shioaji_broker.py` |
| **Combo Order / Reserve Order** | 期貨價差單、預約單（Phase 5+） | 同上 |
| **on_quote / on_event 回調** | 即時行情推送、斷線重連 | `data/shioaji_quote.py` |
| **on_order / on_filled 回調** | 委託 / 成交事件 → 寫入本地部位帳本 | `paper/state.py` + 稽核 hook |
| **list_accounts / set_default_account** | 多帳戶切換（股票 / 期貨） | `paper/shioaji_broker.py` |
| **account_balance / margin / position** | 部位 / 權益對賬 | `paper/reconcile.py` |
| **kbars（歷史 K 線）** | 個股頁回放、即時補資料 | `data/shioaji_quote.py` |

#### 4.11.2 認證與登入流程

```python
# src/ohmystock/paper/shioaji_broker.py
import shioaji as sj
from ohmystock.config import settings

class ShioajiBroker:
    def __init__(self, simulation: bool = True):
        self.api = sj.Shioaji(simulation=simulation)
        self._connected = False

    async def login(self):
        # v1.0+ 使用 api_key / secret_key（非身分證）
        accounts = self.api.login(
            api_key=settings.SHIOAJI_API_KEY.get_secret_value(),
            secret_key=settings.SHIOAJI_SECRET_KEY.get_secret_value(),
            fetch_contract=True,        # 開機載合約
            contracts_timeout=10_000,
            subscribe_trade=True,        # 自動訂閱 Order/Deal 事件
            receive_window=30_000,
        )
        # 檢查「signed」狀態（已同意服務條款）
        for acc in accounts:
            if not acc.signed:
                raise RuntimeError(f"帳戶 {acc.account_id} 未簽署服務條款")
        self._connected = True
        return accounts

    async def activate_ca(self, person_id: str, ca_password: str):
        """僅 Live 階段需要；模擬倉不需"""
        self.api.activate_ca(
            ca_path=settings.CA_PFX_PATH,
            ca_passwd=ca_password,
            person_id=person_id,
        )
```

**重要設計約束**：
- `api_key` / `secret_key` / `ca_password` 一律經 `cryptography.fernet` 加密 + OS keyring 管 master key（§6 合規）
- 模擬倉（`simulation=True`）**不需** `activate_ca`，可在 dev / CI 全自動執行
- Live 階段 `activate_ca` 為**手動步驟**，不可自動化（合規要求）
- `receive_window` 預設 30 秒；遇 `Sign data is timeout` 錯誤先校時 NTP 再考慮放寬

#### 4.11.3 Contracts 載入策略（解決冷啟動慢）

Shioaji 開機 `fetch_contract=True` 會抓全市場合約（股票 / 期貨 / 選擇權 / 權證），約 2-5 秒。

```python
# 我們的優化：
# 1. 開機背景載入，不阻塞 API server 啟動
# 2. 合約 cache 30 分鐘，避免每次重啟都打 Shioaji
# 3. day_trade 旗標寫入 universe.py，給策略 risk_gate 用

class ContractRegistry:
    def __init__(self, broker: ShioajiBroker):
        self.broker = broker
        self._stock: dict[str, sj.contracts.Stock] = {}
        self._future: dict[str, sj.contracts.Future] = {}
        self._loaded_at: float | None = None

    async def load(self):
        for code, contract in self.broker.api.Contracts.Stocks.iteritems():
            self._stock[code] = contract
            # 寫入 universe DB，含 day_trade 旗標
            await universe_db.upsert(
                symbol=code, name=contract.name,
                day_trade_short=contract.day_trade == "Yes",  # 是否可現股當沖（先賣後買）
                limit_up=contract.limit_up, limit_down=contract.limit_down,
                category=contract.category,
            )
        self._loaded_at = time.monotonic()
```

#### 4.11.4 即時行情訂閱（Tick / BidAsk / 盤中零股）

```python
# src/ohmystock/data/shioaji_quote.py
class ShioajiQuoteFeed:
    MAX_SUBSCRIPTIONS = 200  # 保守值，文件未明說但社群實測上限約 500
    
    def __init__(self, broker: ShioajiBroker):
        self.api = broker.api
        self._subs: set[str] = set()
        self.api.quote.set_quote_callback(self._on_quote)
        self.api.quote.set_event_callback(self._on_event)
    
    async def subscribe(
        self, symbol: str, 
        quote_type: str = "tick",   # 'tick' | 'bidask'
        intraday_odd: bool = False,  # 盤中零股需 True
    ):
        if len(self._subs) >= self.MAX_SUBSCRIPTIONS:
            raise RuntimeError("超過訂閱上限")
        contract = self.api.Contracts.Stocks[symbol]
        self.api.quote.subscribe(
            contract, quote_type=quote_type, intraday_odd=intraday_odd
        )
        self._subs.add(f"{symbol}:{quote_type}:{intraday_odd}")
    
    def _on_quote(self, topic: str, quote: dict):
        """
        Tick: AmountSum, Close, Date, TickType, Time, VolSum, Volume
        BidAsk: AskPrice, AskVolume, BidPrice, BidVolume, Date, Time
        """
        # 推送到 SSE / WebSocket → 前端即時更新
        # 同時寫入 ring buffer 供策略 on_bar 用
        market_bus.publish(topic, quote)
    
    def _on_event(self, resp_code, event_code, info, event):
        # event_code 100 = subscribe ok / 200 = system / 300 = disconnect
        if event_code == 300:  # 斷線
            asyncio.create_task(self._reconnect())
    
    async def _reconnect(self):
        """每日 03:00 Shioaji 後端重啟必觸發"""
        await asyncio.sleep(5)
        for sub in list(self._subs):
            symbol, qtype, odd = sub.split(":")
            await self.subscribe(symbol, qtype, odd == "True")
```

**訂閱配額管理**：
- MVP 期：訂閱**持倉 (≤ 6 檔) + watchlist Top 20 + 大盤指數**（≈ 30 檔）
- 盤中強勢股掃描 (Phase 2A) 用 **Snapshot API 一次撈** 而非長期訂閱（避免吃完配額）
- 凌晨 03:00 主動重連（Shioaji 後端重啟）

#### 4.11.5 委託下單流程（State Machine）

```python
# src/ohmystock/paper/shioaji_broker.py
async def place_order(
    self,
    symbol: str,
    side: Literal["Buy", "Sell"],
    qty: int,                    # 張數，1 張 = 1000 股
    price: float | None = None,  # None = 市價
    order_type: str = "ROD",     # ROD | IOC | FOK
    order_lot: str = "Common",   # Common | IntradayOdd | Odd | Fixing
    is_day_trade: bool = False,
) -> "Trade":
    # 1. Risk Gate（Risk-Off / 處置股 / 漲跌停 / 部位上限）
    await self.risk_gate.check(symbol, side, qty, price)

    contract = self.api.Contracts.Stocks[symbol]
    order = self.api.Order(
        action=sj.constant.Action.Buy if side == "Buy" else sj.constant.Action.Sell,
        price=price or 0,
        quantity=qty,
        price_type=sj.constant.StockPriceType.LMT if price else sj.constant.StockPriceType.MKT,
        order_type=getattr(sj.constant.OrderType, order_type),
        order_lot=getattr(sj.constant.StockOrderLot, order_lot),
        order_cond=sj.constant.StockOrderCond.Cash,  # 現股；Live 階段可改 MarginTrading
        daytrade_short=is_day_trade and side == "Sell",  # 先賣後買當沖
        custom_field=f"r{run_id[:5]}",  # 最多 6 字元，記錄 LLM run_id
        account=self.api.stock_account,
    )
    # 2. 送出
    trade = self.api.place_order(contract, order, timeout=5000)
    # 3. 寫入本地 SQLite（source of truth）
    await paper_state.insert_order(trade, run_id=run_id)
    return trade

# 委託狀態機：透過 callback 接收
@self.api.set_order_callback
def _on_order_status(stat: sj.constant.OrderState, msg: dict):
    # PendingSubmit → PreSubmitted → Submitted →
    #   Filled / PartFilled / Cancelled / Failed
    asyncio.create_task(paper_state.update_status(msg["order"]["id"], msg))
    # 同時寫入稽核日誌（PostToolUse hook 對齊）
    audit.log("order_status", msg)
```

**重要規則**：
- `quantity` 單位是**張**（1 張 = 1000 股），`order_lot=Common`；零股用 `IntradayOdd` 且單位變股
- `daytrade_short=True` 需 `Contract.day_trade == "Yes"`（先賣後買）；違反會被 Shioaji 拒單
- `custom_field` 最多 6 字元 → 用來嵌入 `run_id` 前綴，方便事後 trace 哪筆 LLM run 觸發
- 即使 simulation 也要走 risk gate；不可跳過

#### 4.11.6 帳戶與部位查詢

```python
async def reconcile(self):
    """每日 14:30 收盤後與 Shioaji 對賬"""
    sj_balance = self.api.account_balance()              # 帳戶餘額
    sj_positions = self.api.list_positions(self.api.stock_account)
    sj_trades = self.api.list_trades()                   # 當日委託 + 成交
    
    local_positions = await paper_state.get_all_positions()
    diffs = compare(sj_positions, local_positions)
    if diffs:
        audit.log("reconcile_diff", diffs)
        await alert.send(f"對賬差異 {len(diffs)} 筆，已寫入稽核日誌")
```

> ⚠️ **Shioaji 模擬倉部位不持久化**（後端重啟會清空）→ 本地 SQLite 為 source of truth；對賬僅用於偵測 Shioaji 端異常或本地 bug。

#### 4.11.7 進階功能採用優先序

| 功能 | Phase | 用途 |
|---|---|---|
| **Snapshot API**（多檔即時快照） | Phase 1 | Dashboard、Phase 2A 盤中掃描 |
| **Scanners**（漲跌幅 / 量能排行） | Phase 2 | Phase 2A 11:00/13:00 強勢股掃描 |
| **Touch Price Order**（觸價單） | Phase 2 | 預掛停損 / 突破單；模擬倉支援 |
| **Quote-Binding Mode** | Phase 3 | 高頻場景批次訂閱（>50 檔同時） |
| **Non-blocking Mode** | Phase 3 | async loop 不阻塞 |
| **Combo Order**（期貨價差） | Phase 5+ | 跨月份套利（暫不規劃） |
| **Reserve Order**（預約單） | Phase 5+ | 隔日盤前掛單（暫不規劃） |

#### 4.11.8 Wrapper 抽象設計（為未來 Live / Fugle 切換預留）

```python
# src/ohmystock/paper/_protocol.py
from typing import Protocol

class BrokerAdapter(Protocol):
    """所有 broker 共用介面，便於 Shioaji ↔ Fugle ↔ MockBroker 切換"""
    async def login(self) -> None: ...
    async def place_order(self, ...) -> Trade: ...
    async def cancel_order(self, order_id: str) -> bool: ...
    async def get_positions(self) -> list[Position]: ...
    async def get_balance(self) -> Balance: ...
    async def subscribe_quote(self, symbol: str, qtype: str) -> None: ...
    
class ShioajiBroker(BrokerAdapter): ...   # 此檔
class MockBroker(BrokerAdapter): ...      # 測試用，無外部依賴
class FugleBroker(BrokerAdapter): ...     # 預留，Phase 5+
```

#### 4.11.9 風險、速率限制、重連策略

| 議題 | 處理 |
|---|---|
| **API rate limit**（文件未明說） | 自我節流：下單 ≤ 5 req/sec、訂閱 ≤ 60 req/sec、Snapshot ≤ 10 req/sec；超過 backoff exponential |
| **訂閱配額** | `MAX_SUBSCRIPTIONS = 200`（保守）；超過自動 LRU 退訂最舊的 |
| **每日 03:00 後端重啟** | `on_event` 偵測 `event_code=300` 斷線 → asyncio task 5 秒後重連 + 重訂閱 |
| **`Sign data is timeout`** | 開機自動 NTP 同步系統時間；仍失敗則放寬 `receive_window` 至 60 秒 |
| **CA 憑證過期**（Live 階段） | 啟動時檢查到期日，30 天內到期跳警告；7 天內到期阻止登入 |
| **Shioaji SDK 版本鎖定** | `pyproject.toml` 鎖 `shioaji>=1.2,<2.0`，避免破壞性升級 |
| **模擬倉與 Live 環境變數混淆** | Settings 強制兩組 env：`SHIOAJI_SIMULATION=true/false`；UI 啟動時若連到 live 跳紅色警示橫幅 |
| **下單失敗 retry** | **不自動 retry**；交給 LLM 看到 error 後決定是否重試（避免重複下單） |

#### 4.11.10 整合驗證自我 Demo（個人驗收清單）

1. `uv run ohmystock shioaji login` → 顯示帳戶清單 + signed 狀態
2. `uv run ohmystock quote subscribe 2330` → 即時 tick 串流到 stdout
3. CLI：「在模擬倉買 1 張 2330 限價 980」→ Shioaji ack + 本地部位更新 + audit log 一筆
4. CLI：「查 2330 是否可現股當沖」→ 讀 contract.day_trade 回覆
5. 14:30 自動觸發 reconcile → 差異報告寫到 `~/.ohmystock/reconcile/2026-04-26.json`
6. 凌晨 03:00 模擬斷線 → 5 秒後自動重連 + 重訂閱（log 可查）

#### 4.11.11 開發順序建議

加入 §9 路線圖 Phase 2「回測引擎 + 模擬下單」之內，順序：
1. 第 1 週：Login + Contracts 載入 + 1 檔 quote 訂閱（POC）
2. 第 2 週：BrokerAdapter 抽象 + place_order + 狀態機 + SQLite 部位鏡射
3. 第 3 週：Snapshot / Scanners + 自我速率限制 + 重連邏輯 + reconcile + Risk Gate 整合

---

## 5. 資料來源策略（Data Sources）

### 5.1 FinMind 額度／贊助門檻（必須跟主管核對預算）

| 等級 | 額度 | 必要資料 |
|---|---|---|
| **免費** | 600 req/hr，部分 endpoint 限 30 天回溯 | 基本價量、財報摘要 |
| **贊助會員（NT$ 2,000/年）** | 6,000 req/hr，全歷史 | **`TaiwanStockShareholding`、`TaiwanStockMarginShortReportContent`、`TaiwanStockTradingDailyReport`（分點）、`TaiwanStockSecuritiesLending`（借券）** |

> 🚨 **籌碼面 skills 全數依賴贊助會員資料**。MVP 必須採購贊助會員，否則 §4.2「籌碼面」六個 skill 全部殘廢。

### 5.2 Fallback 鏈（`src/ohmystock/data/`）
1. FinMind →（失敗）→ TWSE OpenAPI →（無此 endpoint）→ twstock →（失敗）→ yfinance
2. 即時報價：Shioaji（唯一選項，實時 L1/L2）
3. 重訊／季報：MOPS 爬蟲（rate-limit 自我節制，被 ban 後切備援代理）

### 5.3 快取策略（`src/ohmystock/data/cache.py`）
- **日 K** 收盤後一次抓全市場，存 Parquet（按月分區）
- **籌碼資料** 收盤後 19:00 後抓（FinMind 更新時間）
- **即時報價** 不快取（直接走 Shioaji）
- **基本面** SQLite，每季更新

---

## 6. 風險與合規（TW Compliance）

| 議題 | 處理方式 |
|---|---|
| **本系統定位** | **個人研究工具，僅本機 localhost 使用**；不對外發布，不收費，不提供他人使用。因此**無 SITC 投顧執照、PDPA、外部稽核**等議題。若未來真要對外，那是另一個專案的範疇。 |
| **強制免責聲明（自律）** | 所有報告 / UI 頁尾固定顯示：「本系統內容僅供個人研究參考，不構成投資建議。」即使只給自己看，也提醒自己決策獨立判斷。 |
| **稽核日誌（個人歸檔）** | `PostToolUse` hook → append-only JSONL → `~/.ohmystock/audit/*.jsonl`；保留 90 天 hot；舊資料手動移到外接備份 / 雲端冷存（不限平台、不必每日打包） |
| **個資保護** | Shioaji 帳號密碼、CA 憑證 → `cryptography.fernet` 加密 + OS keyring 管 master key；嚴禁明文落盤（即使是個人使用，避免不慎 commit 到 git） |
| **下單雙重確認（自律）** | 即使 paper 階段，下單前必觸發 `<ConfirmDialog>` 二次確認 + isTrusted 檢查（防自己手滑點到，或 LLM 自動模式幻覺）；live 階段 hook 強制執行 |
| **暫停／處置股自動降級** | `data/universe.py` 每日同步公告，命中清單自動禁止策略下單 |

---

## 7. 技術選型（Tech Stack）

| 領域 | 選擇 | 理由 |
|---|---|---|
| Agent SDK | **claude-agent-sdk**（Python） | Anthropic 原生，工具呼叫 / 記憶 / 流式為一等公民；少一層 LangChain 抽象 |
| 主 LLM | Claude Opus 4.7 / Sonnet 4.6 | Swarm 主節點用 Opus，子節點用 Sonnet（成本/效能平衡） |
| 套件管理 | **uv** | 比 pip / poetry 快 10x，鎖檔穩定 |
| Web framework | FastAPI | 與 Vibe-Trading 一致，SSE 原生支援 |
| 資料儲存 | SQLite + FTS5 + Parquet | 本機輕量；Parquet 處理價量歷史最有效 |
| 前端 | React 19 + Vite + TS + Zustand | 與 Vibe-Trading 一致，避免重學 |
| 容器 | Docker Compose | 本機開發即可上手 |
| 設定 | pydantic-settings + `.env` | type-safe 設定 |
| 測試 | pytest + hypothesis | hypothesis 對回測引擎 fuzz |
| 觀測性 | structlog + opentelemetry | 稽核日誌雙寫 |

---

## 8. 目錄結構（Directory Layout）

```
D:\ohMyStock\
├── pyproject.toml                  # uv 管理
├── .env.example                    # 設定範本
├── docker-compose.yml
├── README.md
├── CLAUDE.md                       # Claude Code 專案指引
│
├── src/ohmystock/
│   ├── agent/
│   │   ├── loop.py                 # ⭐ ClaudeSDKClient 主迴圈
│   │   ├── system_prompt.py
│   │   ├── compaction.py           # 5-layer context manager
│   │   └── hooks.py                # PreToolUse/PostToolUse 稽核
│   ├── prompts/                    # 系統 prompt 片段（*.md）
│   ├── skills/
│   │   ├── _loader.py              # ⭐ skill 自動發現
│   │   ├── data/*.md
│   │   ├── technical/*.md
│   │   ├── fundamental/*.md
│   │   ├── chip/*.md
│   │   ├── tw_specific/*.md
│   │   ├── quant/*.md
│   │   └── portfolio/*.md
│   ├── tools/
│   │   ├── _registry.py            # ⭐ tool decorator
│   │   ├── market_data.py
│   │   ├── chip_data.py
│   │   ├── backtest.py
│   │   ├── paper_trade.py
│   │   ├── screener.py
│   │   ├── swarm.py
│   │   ├── memory.py
│   │   ├── risk_check.py
│   │   └── ...
│   ├── data/
│   │   ├── base.py                 # DataSource Protocol
│   │   ├── finmind.py
│   │   ├── shioaji_quote.py
│   │   ├── twstock.py
│   │   ├── yfinance.py
│   │   ├── twse_openapi.py
│   │   ├── mops_scraper.py
│   │   ├── cache.py                # Parquet + SQLite
│   │   └── universe.py             # 上市/櫃/興櫃 + 處置/警示 旗標
│   ├── strategies/                 # ⭐ 交易策略實作層（詳 §4.10；邏輯以 docs/workflow-cheatsheet.md 為準）
│   │   ├── base.py                 # Strategy Protocol / Bar / Signal
│   │   ├── registry.py             # @register_strategy
│   │   ├── sizing.py               # Volatility Targeting（cheatsheet §6）
│   │   ├── risk_gate.py            # 全域風險閘 + 月度熔斷（cheatsheet §0/§8）
│   │   ├── scoring.py              # 35+45+10+10 評分公式（cheatsheet §10）
│   │   ├── _kpattern/              # VCP / 杯柄 / 平台突破 偵測器（cheatsheet §9）
│   │   ├── optimize.py             # Optuna + WFA
│   │   ├── tw_momentum_swing/      # ⭐ MVP 主軸：實作 cheatsheet 全文
│   │   │   ├── strategy.py
│   │   │   ├── phase1_screening.py
│   │   │   ├── phase15_revenue.py
│   │   │   ├── phase2a_intraday.py
│   │   │   ├── phase2b_scoring.py
│   │   │   ├── phase3_entry.py
│   │   │   └── phase4_exit.py
│   │   ├── technical/              # vcp_breakout / ma_crossover / turtle ...
│   │   ├── fundamental/            # low_pe_high_yield / earnings_surprise
│   │   ├── chip/                   # foreign_buy_streak / broker_concentration / lending_squeeze
│   │   ├── tw_specific/            # monthly_revenue_momentum / dividend_run / disposal_rebound
│   │   └── ml/                     # lgbm_multifactor + features/
│   ├── backtest/
│   │   ├── engine.py               # ⭐ 回測主引擎（呼叫 strategies/）
│   │   ├── fills.py                # 漲跌停 / 處置 / 零股 fill model
│   │   ├── costs.py                # 手續費 + 證交稅
│   │   ├── corporate_action.py     # 除權 / 除息 / 現增減資
│   │   └── calendar.py             # TWSE 交易行事曆 + 半日
│   ├── paper/
│   │   ├── shioaji_broker.py       # ⭐ Shioaji wrapper
│   │   ├── state.py                # SQLite 部位鏡射
│   │   └── reconcile.py            # 每日對賬
│   ├── memory/
│   │   ├── files.py                # 檔案式持久記憶
│   │   └── sessions_fts.py         # SQLite FTS5
│   ├── swarm/
│   │   ├── dag.py                  # DAG 執行
│   │   ├── presets/*.yaml          # 10 個預設 swarm
│   │   └── runner.py
│   ├── ca/                         # Shioaji 憑證 vault（加密）
│   ├── config/
│   │   └── settings.py             # pydantic-settings
│   ├── api/                        # FastAPI + SSE
│   │   ├── server.py
│   │   ├── routes_runs.py
│   │   ├── routes_sessions.py
│   │   └── routes_swarm.py
│   └── cli/                        # typer 進入點
│       └── main.py
│
├── web/                            # React 19 + Vite（Phase 4）
│   └── src/{pages,components,stores}
│
├── tests/
│   ├── test_backtest.py
│   ├── test_fills.py               # 漲跌停 / 處置股 fuzz
│   ├── test_corporate_action.py
│   └── ...
├── eval/                           # skill 回歸測試集
│   └── golden/
├── notebooks/                      # Jupyter 實驗區
└── docs/
    └── design-zh-TW.md             # 本文件正式版
```

---

## 9. 開發路線圖（Roadmap, ~20 週,v3 由 13 週擴充至 20 週）

> **2026-04-26 拍板**:Phase 3.5 確定 v1 同時做 `OHMYSTOCK_AUTO_EXECUTE=true/false` 兩模式,工期由 2 週擴至 **3 週**;總期程 15 → 16 週;Phase 4 / 5 順延一週。
> **2026-04-27 thread D 誠實調整**:Phase 0 = 2 週(Shioaji+FinMind 接通實境吃時間)、Phase 4 = 4 週(拆 4a/4b/4c/4d 四子階段)、Phase 5 = 3 週(含模擬 1 週緩衝);總期程 16 → 20 週;完成日 2026-08-18 → 2026-09-15。

| 階段 | 週數 | 範圍 | 驗收 |
|---|---|---|---|
| **Phase 0: Scaffold** | **2** | 專案骨架、`uv` 環境、Claude Agent SDK Hello World、Docker、CI（pytest + ruff）;**Shioaji 模擬倉 / FinMind / Anthropic 三方連線測試**;**LLM cost tracking decorator** | `uv run ohmystock --version` 可執行;三方 ping 通 |
| **Phase 1: 核心 Agent + 基礎 skills** | 2 | Agent loop（async）、5 層壓縮、skill loader、5 個基線 skill（finmind / ma-crossover / kd-macd-rsi / valuation-pe-pb / three-major-investors）、FinMind loader + 快取 | CLI 對話可查詢個股 + 三大法人 |
| **Phase 2: 回測引擎 + 模擬下單** | 3 | TWSE 回測引擎（含 §4.4.1 全部市場細節）、Shioaji 模擬倉 wrapper、SQLite 部位鏡射、稽核 hook | 跑通 0050 雙均線策略 5 年回測；Shioaji 模擬下單成功 |
| **Phase 3: 完整 skill 庫 + Swarm** | 3 | 補齊 30 個 skill、Swarm DAG、10 組 preset(不含 v3 兩組閉環 swarm)、`risk_check_tool`、`trade_journal_tool` 基本版 | 「投資委員會」preset 對 2330 出具完整論點 |
| **Phase 3.5: 閉環 LLM 決策 + 復盤(v3 新增)** | **3** | LLM Decider pipeline(§3 + §4.10.3)、`entry_decision_team` swarm(§4.7.1)、**Confirm Gate 雙模式(human + auto)**、**防線 9 全套熔斷 + 整合測試**(§4.5)、`trade_journal_tool` v3 schema + FTS5 索引(§4.6.1)、`post_trade_review_team` swarm(§4.7.2)、`proposal_tool` 工作流(§16)、`/api/decisions` `/api/reviews` `/api/proposals` 端點(§4.8.2)、wireframe Q/R/S(§4.9.17)、`OHMYSTOCK_AUTO_EXECUTE` 兩種旗標下的 e2e 測試 | **完整跑通「Phase 2B 訊號 → LLM 決策 → 人工 confirm OR 自動執行(經熔斷) → 出場 → 月度復盤 → 提案 → WFA 驗證 → 人工 PR → 合併」一輪;雙模式皆需通過** |
| **Phase 4: Web UI 後台**(admin only) | **2** | 4a admin 18 頁 + 4c-half Bearer auth;React 19 UI、SSE 串流、跨 session 記憶、FTS5 對話搜尋(整合 v3 journal 索引) | admin 18 頁 wireframe 全部實作;localhost 全流程可用(含決策審核 / 復盤 / 提案頁) |
| **Phase 4.5: Web UI 公網**(pixel + mask) | **2** | 4b public pixel 9 角色 + 4c-half Mask serializer + 4d E2E mask 滲透測試;**ship admin 後啟動,視 admin 跑況決定是否砍掉**(thread E 決策) | mask 滲透測試零洩漏;9 角色動畫狀態機運作 |
| **Phase 5: 強化 / 文件 / 部署** | **3** | 測試覆蓋率 ≥70%、`docs/` 完整、Docker 一鍵部署、自我端對端 demo;**第 3 週為「自跑 1 週模擬」緩衝** | 自己跑模擬倉滿 1 週無 crash |

> 並行 Side Tracks（不阻塞主路線）：產業 / 概念股對照表整理、TWSE 行事曆爬蟲、MOPS 公告監控守護程序。

---

## 10. 關鍵實作參考檔案（Reference: Vibe-Trading）

實作對應功能時，**優先閱讀** Vibe-Trading 對應檔案：

| 我們要做的 | 參考 Vibe-Trading 路徑 | 動作 |
|---|---|---|
| Agent loop | `src/agent/loop.py` | **重寫**（LangChain → Claude SDK async） |
| 5 層壓縮 | `src/agent/context.py` | port 邏輯，型別換 SDK Message |
| Skill loader | `src/agent/skills.py` + frontmatter parser | **可直接搬** |
| Tool registry | `src/agent/tools.py` | **可直接搬**（auto-discovery decorator） |
| Swarm 編排 | `src/swarm/orchestrator.py` + `config/swarm/investment_committee.yaml` | port DAG，LLM 呼叫端換 |
| Session FTS5 schema | `src/session/sessions.py` | **schema 直接複製** |
| 回測 base | `src/backtest/engines/a_shares.py` | **fork** 後台股特化（A 股最接近） |
| Web UI baseline | `web/src/components/ChatStream.tsx` + `pages/` | port |
| 部署 | `docker-compose.yml` + `Dockerfile` | port |

---

## 11. 關鍵檔案路徑（待建立）

優先建立／修改的核心檔案：

- `D:\ohMyStock\pyproject.toml`
- `D:\ohMyStock\src\ohmystock\agent\loop.py`
- `D:\ohMyStock\src\ohmystock\agent\hooks.py`
- `D:\ohMyStock\src\ohmystock\skills\_loader.py`
- `D:\ohMyStock\src\ohmystock\tools\_registry.py`
- `D:\ohMyStock\docs\workflow-cheatsheet.md` ⭐ **交易邏輯權威來源**
- `D:\ohMyStock\src\ohmystock\strategies\base.py`
- `D:\ohMyStock\src\ohmystock\strategies\registry.py`
- `D:\ohMyStock\src\ohmystock\strategies\sizing.py`
- `D:\ohMyStock\src\ohmystock\strategies\risk_gate.py`
- `D:\ohMyStock\src\ohmystock\strategies\scoring.py`
- `D:\ohMyStock\src\ohmystock\strategies\tw_momentum_swing\strategy.py` ⭐ MVP 主軸
- `D:\ohMyStock\src\ohmystock\backtest\engine.py`
- `D:\ohMyStock\src\ohmystock\backtest\fills.py`
- `D:\ohMyStock\src\ohmystock\backtest\corporate_action.py`
- `D:\ohMyStock\src\ohmystock\paper\_protocol.py` — BrokerAdapter Protocol（§4.11.8）
- `D:\ohMyStock\src\ohmystock\paper\shioaji_broker.py` — Shioaji wrapper（§4.11）
- `D:\ohMyStock\src\ohmystock\data\shioaji_quote.py` — 即時行情訂閱 + 重連
- `D:\ohMyStock\src\ohmystock\paper\state.py`
- `D:\ohMyStock\src\ohmystock\data\finmind.py`
- `D:\ohMyStock\src\ohmystock\data\universe.py`
- `D:\ohMyStock\src\ohmystock\swarm\dag.py`
- `D:\ohMyStock\src\ohmystock\swarm\presets\investment_committee.yaml`
- `D:\ohMyStock\src\ohmystock\config\settings.py`
- `D:\ohMyStock\src\ohmystock\cli\main.py`

---

## 12. 驗證計畫（Verification）

### 12.1 單元 / 整合測試
- `pytest tests/` 覆蓋率目標 ≥ 70%
- `tests/test_fills.py` 用 hypothesis fuzz 漲跌停 / 處置 / IPO 蜜月期邊界
- `tests/test_corporate_action.py` 用台積電 2330 過去 10 年除權息事件回放驗證
- `tests/test_paper.py` 用 Shioaji simulation 啟動下單 → 對賬

### 12.2 回測黃金集（Golden Set）
- 0050 雙均線（20/60）2015–2024 → 對標 XQ／TradingView 結果，誤差 < 0.5%
- 2330 季報行情策略 → 與手動回測一致
- 0056 季配息再投入 → 確認除息調整正確

### 12.3 Skill 回歸（`eval/golden/`）
- 30 個 skill 各備 3 個黃金 prompt + 預期輸出片段
- CI 每次推送跑全套，flake 率追蹤

### 12.4 端對端自我 Demo（個人驗收）
1. CLI：「幫我分析 2330 最近一個月的籌碼面」→ 多代理人協作出具報告
2. CLI：「跑 0050 雙均線 2020–2024 回測」→ Sharpe / Max DD / 資金曲線圖
3. CLI：「在模擬倉買 1 張 2330」→ Shioaji ack + 本地部位更新 + 稽核日誌可查
4. Web UI：開啟 `localhost:8899`，重複上述流程，串流即時呈現
5. 翻 `~/.ohmystock/audit/2026-04-26.jsonl`，每筆 tool call / order 完整可追溯

---

## 13. 開放議題 / 個人 backlog（已轉移至 v3-decisions.md）

> 詳細決策見 [`v3-decisions.md`](v3-decisions.md)。本節保留為簡略條列，避免重複維護。

1. **FinMind 贊助會員預算**（NT$ 2,000/年）是否核可？— 影響籌碼面 skill 是否上線。
2. **Shioaji 模擬倉帳號**由誰申請、開戶？需身分證 / 雙證件。
3. **Web UI 對外 / 對內**？若對外需評估 SITC 投顧執照風險。
4. **Live trading 時程**：Phase 5 之後若評估上線，是否需先做合規審查？
5. **Audit log 5 年儲存空間**：是否提供 S3 / B2 / 自架 MinIO？
6. **多人使用**：是否需多帳號？目前設計為單一使用者。
7. **Anthropic Claude API 月預算**(v3 新增,2026-04-26):每月 LLM 成本預估 USD $31-36(NT$ 960-1,120),啟用 prompt cache + batch API 後可降至 $20-25/月(NT$ 620-775)。建議預算上限 USD $50/月(NT$ 1,500),超過自動降階為全 Sonnet。**主要驅動**:Phase 3 LLM Decider PM 結論(Opus 4.7)+ Phase 5 復盤 Critic/Proposer(Opus 4.7)。
8. **LLM 模型配置**(v3 新增,2026-04-26 拍板):採**混合分層**配置:
   - Opus 4.7 → PM 結論(Phase 3)、Critic 與 Proposer(Phase 5)
   - Sonnet 4.6 → Bull/Bear 分析(Phase 3)、Attributor/Aggregator(Phase 5)
   - Haiku 4.5 → Rule Checker、Risk Simulator(Phase 3)、Data Loader(Phase 5)
9. **`OHMYSTOCK_AUTO_EXECUTE` v1 範圍**(v3 新增,2026-04-26 拍板):**v1 同時支援 true/false 兩模式**;Phase 3.5 工期 2→3 週;§4.5 防線 9 全套熔斷邏輯與整合測試為必交付項目;Live 模式仍強制 disabled(防線 4)。
10. **`proposals/` 與 `reviews/` 進 git**(v3 新增,2026-04-26 拍板):**進 git**;支援跨機 sync 與 §16 提案佐證連結追溯;預估每年 ~3MB,不需特別 archive。
11. **Confirm Gate timeout**(v3 新增,2026-04-26 拍板):**30 分鐘 expire**;搭配 cheatsheet §4 Phase 2A 盤中 11:00/13:00 訊號節奏;逾期寫 trade-journal `kind=expire`。
12. **復盤頻率**(v3 新增,2026-04-26 拍板):**月度自動 + 任意手動觸發**;月度熔斷強制觸發;季度復盤每季 1 次;不採週度。

---

## 14. 風險登記（Risk Register）

| 風險 | 衝擊 | 緩解 |
|---|---|---|
| Shioaji API 變動或斷線 | 高 | 抽象為 `BrokerAdapter` Protocol，預留 Fugle 替代 |
| FinMind 服務中斷 / 額度耗盡 | 中 | Fallback 鏈到 TWSE OpenAPI / twstock；Parquet 快取兜底 |
| Claude API 額度爆量 | 中 | Swarm 子節點用 Sonnet 4.6 / Haiku 4.5,Opus 4.7 僅主協調 + 批判 + 提案;prompt cache 開好;復盤頻率上限月度 |
| LLM 給出投資建議造成爭議 | 高 | 強制免責聲明 + 不直接推薦個股的 system prompt 約束 + 人工確認 hook |
| 稽核日誌外洩 | 高 | 加密落盤、權限最小化、定期輪替金鑰 |
| MOPS 反爬 | 低 | 自我節流 + 隨機 UA + 快取；不行則改人工檔案匯入 |
| **LLM Decider 幻覺造成下單失誤(v3)** | 高 | Confirm Gate 預設人工(`OHMYSTOCK_AUTO_EXECUTE=false`);自動模式經 §4.5 防線 9 熔斷(confidence < 0.7 / 單日 > 5 筆 / 單筆 > 25% / sizing 偏離 > 30% 任一觸發 fallback 人工);每筆 sizing 經系統公式覆寫;ATR 停損價 LLM 不可覆寫;Live 模式強制 disabled |
| **LLM 自動寫入 cheatsheet 造成漂移(v3)** | 中 | LLM 不可直接 commit;改 cheatsheet 一律走 `proposals/*.md` → WFA / Robust / 黃金樣本三道驗證閘 → 人工 PR review → 注入 confirm_token 才合併;`proposal_tool.merge_proposal` REST API 僅接受人工 ConfirmDialog 來源 |
| **復盤 LLM 過擬合歷史交易(v3)** | 中 | 提案必經 WFA 樣本外驗證(落差 > 30% 拒絕);Robust 測試 ±10% 鄰域 Sharpe 衰減 > 50% 拒絕;黃金樣本不退化才核准;每次 merge 對應 git tag 可回滾 |
| **Confirm Gate 過期未處理累積(v3)** | 低 | 預設 30 分鐘 expire,寫 journal `kind=expire`;UI 顯示倒數計時;月度復盤統計 expire 比例,過高可能訊號質量不佳 |

---

> 📌 **下一步**：本文件經主管 review 後，依 §10 路線圖排程 Phase 0 環境建置。需要時可進一步拆出 epic / story 至 issue tracker。
