# Tools Contracts — 21 個工具的 I/O 規格

> 本檔為 **`@register_tool` 註冊工具**的 input/output schema 唯一權威。
> 對應 [`design-zh-TW.md` §4.3](design-zh-TW.md#43-tools-註冊表srcohmystocktools_registrypy)。
> 已有完整 schema 的 3 個工具（trade_journal / post_trade_review / proposal）保留在 design §4.3.1-§4.3.3，本檔只列引用。

**版本約定：** Schema 演進依 [llm-decision-schema.md §6](llm-decision-schema.md#6-schema-演進規範)（v1.0→v1.1 只加欄位不刪）。

---

## 0. 通用約定

### 0.1 共通回傳 envelope

所有 tool 回傳結構統一：

```python
{
    "ok": bool,                  # 失敗時為 false
    "elapsed_ms": int,           # 執行毫秒數
    "data": <tool-specific>,     # ok=true 才有
    "error": {                   # ok=false 才有
        "code": str,             # 例 "RATE_LIMIT" / "DATA_UNAVAILABLE"
        "message": str,          # 給人類的訊息
        "retriable": bool        # LLM 可否重試
    } | None
}
```

### 0.2 共通 error code

| code | 意義 | retriable |
|---|---|---|
| `INVALID_INPUT` | 參數型別 / 範圍錯 | false |
| `DATA_UNAVAILABLE` | 來源無資料（停牌、未來日期、KY 股） | false |
| `RATE_LIMIT` | API 配額用罄（FinMind / Shioaji） | true（90s 後） |
| `UPSTREAM_ERROR` | 上游 5xx / 超時 | true |
| `AUTH_FAILED` | 憑證 / 權限不足 | false |

### 0.3 日期格式

- 日期：`"2026-04-26"` (ISO-8601 YYYY-MM-DD)
- 時間戳：`"2026-04-26T14:30:00+08:00"` (台北時區)

---

## 1. `market_data_tool` — 行情資料

**用途：** 個股 / 大盤即時行情、歷史 K 線、即時 quote、產業指數、後續 N 日報酬。

```python
get_kline(
    symbol: str,                          # 台股代號 "2330" 或大盤 "TWSE"
    period: Literal["1m","5m","15m","60m","1d","1w","1M"] = "1d",
    bars: int = 250,                      # 取最近 N 根
    end_date: str | None = None,          # 預設今日；指定則回測用
) -> {
    bars: list[{
        ts: str,                          # ISO-8601
        o: float, h: float, l: float, c: float,
        v: int,                           # 成交張數
        amount: int,                      # 成交金額（元）
    }]
}

get_quote(
    symbols: list[str]                    # 最多 50 檔
) -> {
    quotes: list[{
        symbol: str,
        ts: str,
        last: float,
        bid: float, ask: float,
        bid_size: int, ask_size: int,
        change_pct: float,
        volume_today: int,
    }]
}

get_index(
    name: Literal["TAIEX","OTC","SOX","SPY","VIX","USDTWD"]
) -> {
    last: float, change_pct: float, ma60: float, ma200: float,
    ts: str
}

get_post_exit_returns(
    symbol: str,
    exit_date: str,
    horizons_days: list[int] = [5, 10, 20]   # 用於 post_trade_review_team data_loader
) -> {
    returns: dict[str, float]                # {"5d": 0.024, "10d": -0.011, "20d": 0.058}
}
```

**Errors:** `DATA_UNAVAILABLE`（停牌 / 處置全額交割）、`RATE_LIMIT`（Shioaji 60 req/sec）。
**呼叫方:** Phase 0 Risk Gate（大盤指數）、Phase 2A/2B 掃描、`entry_decision_team` 多空節點、Phase 5 data_loader。

---

## 2. `fundamental_data_tool` — 基本面

**用途：** 月營收、季財報、配息、本益比、股本變動。

```python
get_monthly_revenue(
    symbol: str,
    months: int = 24
) -> {
    rows: list[{
        ym: str,                          # "2026-04"
        revenue: int,                     # 元
        yoy: float,                       # 年增率
        mom: float,                       # 月增率
        is_historical_high_3y: bool,      # 近 3 年新高？(cheatsheet §3 用)
    }]
}

get_quarterly_financials(
    symbol: str,
    quarters: int = 8
) -> {
    rows: list[{
        period: str,                      # "2026Q1"
        gross_margin: float,
        operating_margin: float,
        net_margin: float,
        eps: float,
        rev: int,
        # 法說會展望（如有）
        guidance_text: str | None
    }]
}

get_corporate_actions(
    symbol: str,
    from_date: str
) -> {
    actions: list[{
        ts: str,
        kind: Literal["cash_dividend","stock_dividend","split","rights_issue"],
        amount: float,
        ex_date: str
    }]
}

get_pe_pb(
    symbol: str
) -> {
    pe_ttm: float, pb: float, dividend_yield: float
}
```

**Errors:** `DATA_UNAVAILABLE`（KY 股財報不齊）、`RATE_LIMIT`（FinMind 免費版）。
**呼叫方:** Phase 1.5 月營收掃描、`entry_decision_team` 評估節點。

---

## 3. `chip_data_tool` — 籌碼面

**用途：** 三大法人、融資融券、借券、主力分點、個股期 OI（Phase 2B 評分權重 45%）。

```python
get_three_major_investors(
    symbol: str,
    days: int = 30
) -> {
    rows: list[{
        date: str,
        foreign_net: int,                 # 外資淨買賣（張）
        invest_trust_net: int,            # 投信
        prop_dealer_net: int,             # 自營商（避險 + 自行買賣合計）
    }]
}

get_margin_short(
    symbol: str,
    days: int = 30
) -> {
    rows: list[{
        date: str,
        margin_balance: int,              # 融資餘額（張）
        margin_change: int,
        short_balance: int,               # 融券餘額
        short_change: int,
        short_to_margin_ratio: float,     # 券資比 %
    }]
}

get_securities_lending(
    symbol: str,
    days: int = 30
) -> {
    rows: list[{
        date: str,
        balance: int,                     # 借券餘額（張）
        change_pct_5d: float,             # 近 5 日變化（cheatsheet §6.4 風險旗標）
    }]
}

get_top_brokers(
    symbol: str,
    date: str,
    limit: int = 15
) -> {
    buy_top: list[{broker: str, branch: str, net: int, concentration_pct: float}],
    sell_top: list[...],
    main_force_concentration: float        # 前 15 大買超佔當日比 %
}

get_stock_futures_oi(
    symbol: str,
    days: int = 30
) -> {
    rows: list[{date: str, oi_total: int, oi_change_pct: float}]
}
```

**Errors:** `DATA_UNAVAILABLE`（FinMind 籌碼 API 須贊助會員 — 見 design §5.1 預算）。
**呼叫方:** Phase 1 / 1.5 / 2A / 2B 全部掃描階段、`entry_decision_team` 籌碼節點。

---

## 4. `screener_tool` — 通用篩選器

**用途：** 跑漏斗式四層篩選（cheatsheet §2）、月營收掃描（§3）、即時量價異常（§4）。

```python
run_screener(
    universe: Literal["TWSE","OTC","TWSE+OTC","top200","custom"],
    custom_symbols: list[str] | None = None,
    filters: list[ScreenerFilter],        # 漏斗每層條件
    sort_by: str = "score_desc",
    limit: int = 100
) -> {
    candidates: list[{
        symbol: str, name: str, sector: str,
        match_layer: int,                 # 通過到第幾層
        scores: dict[str, float],         # 各篩網的分數
    }]
}

# ScreenerFilter discriminated union 範例
{
    "kind": "negative_filter",            # 對應 cheatsheet §2 第 1 層
    "exclude": ["disposal","warning","fully_paid","KY"]
}
{
    "kind": "volume_filter",              # 第 2 層
    "min_avg_dollar_volume_5d": 50_000_000,
    "min_volume_ratio_15x": True
}
{
    "kind": "chip_filter",                # 第 3 層
    "foreign_net_5d_min": 0,
    "invest_trust_consec_buy_days": 3
}
{
    "kind": "technical_filter",           # 第 4 層
    "above_ema": [20, 60],
    "rs_above_index_pct": 5.0,
    "patterns": ["VCP","cup_handle","flat_base"]
}
```

**Errors:** `INVALID_INPUT`（filter kind 不認識）。
**呼叫方:** Phase 1 / 1.5 / 2A / 2B 各掃描排程器。

---

## 5. `portfolio_tool` — 持倉與曝險

**用途：** 查持倉、計算曝險、檢查單檔 / 同產業 / 總曝險上限。

```python
get_positions() -> {
    positions: list[{
        symbol: str, qty: int, avg_cost: float, last: float,
        pnl_unrealized: float, pnl_pct: float,
        sector: str, hold_days: int,
        stop_price: float, t1_price: float,
        sizing_pct: float,                # 占權益 %
    }],
    equity: float, available_cash: float, exposure_pct: float
}

check_concentration(
    proposed_symbol: str,
    proposed_sizing_pct: float
) -> {
    ok: bool,
    violations: list[Literal[
        "single_position_over_25pct",
        "sector_more_than_2",
        "total_exposure_over_80pct",
        "position_count_over_6"
    ]],
    current_sector_count: int
}

get_equity_curve(
    days: int = 30
) -> {
    points: list[{ts: str, equity: float, drawdown_pct: float}]
}

get_monthly_pnl_pct() -> {
    month_to_date: float,                 # 用於月度熔斷 -8% 檢查（cheatsheet §0）
    distance_to_lockout_pct: float
}
```

**Errors:** `INVALID_INPUT`。
**呼叫方:** Phase 4 持倉檢視、`entry_decision_team`（避免重複買進）、Phase 0 月度熔斷檢查。

---

## 6. `pattern_recognition_tool` — K 線型態辨識

**用途：** 跑 `strategies/_kpattern/` 內的偵測器（VCP / 杯柄 / 平台突破 / 倒 V / 高檔吊人等）。

```python
detect_patterns(
    symbol: str,
    patterns: list[Literal[
        "VCP","cup_handle","flat_base",
        "double_top","double_bottom","head_shoulders",
        "engulfing","morning_star","shooting_star","hanging_man",
        "three_white_soldiers","red_three_soldiers"
    ]],
    lookback_bars: int = 120
) -> {
    detections: list[{
        pattern: str,
        confidence: float,                # 0.0-1.0
        start_idx: int,                   # 在 lookback 內第幾根
        end_idx: int,
        params_match: dict,               # 該型態的具體量化參數通過情況
                                          # 例 VCP: {"contractions": 4, "depth_decline": [0.15,0.10,0.06,0.03]}
        invalidation_price: float | None  # 跌破此價 = 型態破壞
    }]
}
```

**Errors:** `INVALID_INPUT`（pattern 名不認識）、`DATA_UNAVAILABLE`（Bar 數不足）。
**呼叫方:** Phase 2B 評分（圖形項 12 分）、`entry_decision_team` 多方節點 evidence。

---

## 7. `news_sentiment_tool` — 新聞與社群熱度

**用途：** 新聞輿情、PTT / Google Trends 搜尋熱度（cheatsheet §5 情緒項 10 分）。

```python
get_news(
    symbol: str,
    days: int = 7,
    sources: list[Literal["chinatimes","udn","cnyes","ettoday","pttstock"]] | None = None
) -> {
    items: list[{
        ts: str, title: str, summary: str, url: str, source: str,
        sentiment: Literal["positive","negative","neutral"],
        relevance: float                  # 0.0-1.0
    }]
}

get_search_trend(
    keyword: str,                         # 通常 = 公司名
    days: int = 30
) -> {
    google_trends: list[{date: str, score: int}],   # 0-100
    ptt_mention_count: int,
    surge_detected: bool                  # 過去 3 日 vs 30 日均值 > 2x
}
```

**Errors:** `RATE_LIMIT`、`DATA_UNAVAILABLE`。
**呼叫方:** Phase 2B 情緒項評分、`entry_decision_team` 風控節點（過熱風險）。

---

## 8. `risk_check_tool` — Risk Gate 模擬器（不執行真實檢查）

> ⚠️ **這是 LLM swarm 用的「模擬」工具**（給 PM 節點看 Risk Gate 假如執行會怎樣），不是 `strategies/risk_gate.py` 系統 Gate。系統 Gate 在 LLM 決策**之後**真正執行。命名易混淆，未來考慮改 `risk_preview_tool`。

```python
preview_risk_gate(
    symbol: str,
    proposed_qty: int,
    proposed_price: float
) -> {
    would_pass: bool,
    blockers: list[Literal[
        "disposal_stock","warning_stock","fully_paid_stock",
        "limit_up","limit_down","ipo_honeymoon",
        "ky_stock_excluded","exposure_over_80pct",
        "sector_over_2","single_over_25pct"
    ]],
    risk_off_active: bool,
    risk_off_score: str                   # "5/5" / "4/5" 等
}
```

**Errors:** `INVALID_INPUT`。
**呼叫方:** `entry_decision_team` 風控節點（PM 節點輸入材料之一）。

---

## 9. `swarm_tool` — Swarm 啟動 / 查詢

**用途：** 啟動既定的 12 組 swarm preset、查詢執行狀態、取結果。

```python
start_swarm(
    preset: Literal[
        "investment_committee","day_trade_scan","chip_analysis_team",
        "earnings_research","monthly_revenue_team","sector_rotation",
        "vcp_breakout_team","short_squeeze_check","macro_risk_panel",
        "weekend_screening","entry_decision_team","post_trade_review_team"
    ],
    params: dict                          # 因 preset 而異；見 design §4.7
) -> {run_id: str, status: "running"}

get_swarm_status(run_id: str) -> {
    status: Literal["running","done","failed","cancelled"],
    progress: dict[str, Literal["pending","running","done","failed"]],
                                          # node_name → status
    elapsed_ms: int,
    cost_usd: float | None                # token 成本（done 後才有）
}

get_swarm_result(run_id: str) -> {
    nodes: dict[str, {
        output: dict,                     # 各 node 的結構化輸出
        elapsed_ms: int,
        tokens: {input: int, output: int}
    }],
    final: dict                           # PM / proposer 等最終節點輸出
}

cancel_swarm(run_id: str) -> {ok: bool}
```

**Errors:** `INVALID_INPUT`（preset 不存在）、`UPSTREAM_ERROR`（Anthropic API）。
**呼叫方:** 主 agent loop、CLI / Web UI、Phase 5 排程。

---

## 10. `memory_tool` — 跨 session 持久記憶

**用途：** 使用者偏好錨定（如「偏好高股息」「不交易 KY 股」）。對應 design §4.6 `~/.ohmystock/memory/profile.json`。

```python
remember(
    key: str,                             # 例 "preference.dividend"
    value: str,                           # 自然語言或結構化字串
    pinned: bool = False                  # ⭐ 永遠注入 system prompt
) -> {ok: bool}

recall(
    query: str | None = None,
    pinned_only: bool = False,
    limit: int = 50
) -> {
    items: list[{
        key: str, value: str, pinned: bool,
        created_at: str, last_referenced_at: str
    }]
}

forget(key: str) -> {ok: bool}
```

**Errors:** `INVALID_INPUT`。
**呼叫方:** 主 agent loop（每次 prompt assembly 注入 pinned items）、Web UI Memory 頁。

---

## 11. `session_search_tool` — 對話歷史 FTS5 搜尋

**用途：** 跨 session 全文檢索（design §4.6 sessions FTS5）。

```python
search_sessions(
    query: str,                           # FTS5 query syntax
    period_from: str | None = None,
    period_to: str | None = None,
    preset: str | None = None,            # 限定特定 swarm preset
    limit: int = 20
) -> {
    results: list[{
        session_id: str, started_at: str, preset: str | None,
        snippet: str,                     # 命中片段
        score: float                      # FTS5 rank
    }]
}

get_session(session_id: str) -> {
    messages: list[{role: str, content: str, ts: str, tool_calls: list | None}],
    metadata: dict
}
```

**Errors:** `INVALID_INPUT`（FTS5 syntax 錯）。
**呼叫方:** Web UI Sessions 頁、主 agent loop（找相似情境）。

---

## 12. `web_search_tool` — 一般網路搜尋

**用途：** Anthropic SDK 內建的 web search（非 Google API）。用於即時事件、官方公告（公開資訊觀測站新訊）。

```python
web_search(
    query: str,
    domain_whitelist: list[str] | None = None,    # 例 ["mops.twse.com.tw","cnyes.com"]
    max_results: int = 5
) -> {
    results: list[{
        url: str, title: str, snippet: str,
        domain: str, published_at: str | None
    }]
}
```

**Errors:** `RATE_LIMIT`、`UPSTREAM_ERROR`。
**呼叫方:** `entry_decision_team` 多空辯論、新聞驗證、`weekend_screening`。

---

## 13. `read_url_tool` — 抓取單一 URL 內容

**用途：** 抓特定公告、財報法說稿、研究報告。

```python
read_url(
    url: str,
    extract: Literal["text","markdown","raw_html"] = "markdown"
) -> {
    content: str,
    title: str,
    fetched_at: str,
    truncated: bool                       # 超過 50 KB 截斷
}
```

**Errors:** `UPSTREAM_ERROR`（404/5xx）、`AUTH_FAILED`（付費牆）。
**呼叫方:** `web_search_tool` 後續深讀、`read_document_tool` URL 模式。

---

## 14. `read_document_tool` — 讀取本地檔案

**用途：** 讀 PDF（法說簡報 / 研究報告）、Excel、JSON。

```python
read_document(
    path: str,                            # 相對於 ~/.ohmystock/documents/ 或絕對路徑
    pages: list[int] | None = None        # 僅 PDF；不指定則全文
) -> {
    content: str,                         # text / markdown
    page_count: int | None,
    extracted_tables: list[dict] | None,  # PDF 表格（如有）
    file_type: Literal["pdf","xlsx","csv","json","md","txt"]
}
```

**Errors:** `INVALID_INPUT`（路徑不存在 / 格式不支援）。
**呼叫方:** `entry_decision_team` 法說稿 evidence、人工上傳的研究報告。

---

## 15. `write_file_tool` — 寫入本地檔案（受限路徑）

**用途：** Phase 5 復盤產出 `reviews/<period>/*.md`、提案產出 `proposals/<id>.md`。

```python
write_file(
    path: str,                            # 必須在 ~/.ohmystock/{reviews,proposals,exports}/ 下
    content: str,
    mode: Literal["create","overwrite","append"] = "create"
) -> {ok: bool, written_bytes: int, path_resolved: str}
```

**約束（系統強制）：**
- 路徑必須以 `~/.ohmystock/reviews/`、`~/.ohmystock/proposals/`、`~/.ohmystock/exports/` 開頭，否則 `INVALID_INPUT`
- 不可覆蓋 `docs/`、`src/`、任何 `.py` 檔（防止 LLM 改自己的程式）

**Errors:** `INVALID_INPUT`（路徑越權）、`UPSTREAM_ERROR`（磁碟滿）。
**呼叫方:** `post_trade_review_team` proposer 節點、`proposal_tool.create_proposal`。

---

## 16. `skill_writer_tool` — Skill YAML/Markdown 編輯

**用途：** 新增 / 編輯 `src/ohmystock/skills/<category>/<name>/{skill.yaml, skill.md}`。

```python
list_skills(
    category: str | None = None,
    enabled_only: bool = True
) -> {
    skills: list[{
        path: str, name: str, category: str,
        description: str, enabled: bool, version: str
    }]
}

read_skill(path: str) -> {
    yaml: dict, markdown: str
}

write_skill(
    path: str,
    yaml: dict,
    markdown: str,
    bump_version: bool = True
) -> {ok: bool, new_version: str}
```

**Errors:** `INVALID_INPUT`。
**呼叫方:** Web UI Skill Editor、進階使用者 / LLM 自訂 skill。

---

## 17. `backtest_tool` — 回測

**用途：** 跑單一 / 多策略歷史回測。Phase 5 提案 WFA 驗證的底層工具。

```python
run_backtest(
    strategy: str,                        # 例 "tw_momentum_swing"
    universe: Literal["top200","TWSE","OTC","custom"],
    custom_symbols: list[str] | None = None,
    period: {from: str, to: str},
    initial_capital: int = 1_000_000,
    params_override: dict | None = None,
    enable_walk_forward: bool = False,
    walk_forward_train_months: int = 24,
    walk_forward_test_months: int = 6,
) -> {
    job_id: str,
    status: "running"
}

get_backtest_result(job_id: str) -> {
    status: Literal["running","done","failed"],
    metrics: {
        sharpe: float, sortino: float, calmar: float,
        max_drawdown: float, mdd_duration_days: int,
        win_rate: float, profit_factor: float, expectancy: float,
        max_consecutive_loss: int,
        is_oos_sharpe_ratio: float       # 樣本內 / 外 落差（WFA 啟用時）
    } | None,
    trades: list[BacktestTrade] | None,
    equity_curve: list[{date: str, equity: float}] | None,
    diagnostic: dict | None              # cheatsheet §12 五道體檢結果
}

list_backtests(limit: int = 50) -> {jobs: list[{job_id, strategy, period, status, created_at}]}
```

**Errors:** `INVALID_INPUT`（strategy 不存在）、`DATA_UNAVAILABLE`（資料不足）。
**呼叫方:** `proposal_tool.validate_proposal` 內部、回測 UI。

---

## 18. `paper_trade_tool` — 模擬下單

**用途：** 經 Confirm Gate 通過的決策實際送進 paper broker。

```python
submit_order(
    symbol: str,
    side: Literal["buy","sell"],
    qty: int,                             # 張
    order_type: Literal["ROD","IOC","FOK"] = "ROD",
    price: float | None = None,           # None = 市價
    confirm_token: str,                   # 由 ConfirmDialog / auto-execute breaker 產生
    decision_id: str | None = None        # 連結到 trade journal
) -> {
    order_id: str,
    status: Literal["pending","submitted","filled","partial","cancelled","rejected"]
}

cancel_order(order_id: str) -> {ok: bool}

get_orders(date_from: str | None = None, status: list[str] | None = None) -> {
    orders: list[{order_id, symbol, side, qty, price, status, ts, fill_price?, fill_qty?}]
}
```

**約束（系統強制）：**
- `confirm_token` 必須由 backend 簽發（5 分鐘內有效）；LLM 自造會拒絕
- Live 模式禁用此工具（若 broker = shioaji-live，直接 `INVALID_INPUT`）

**Errors:** `INVALID_INPUT`（token 過期 / 無效）、`UPSTREAM_ERROR`（Shioaji 異常）。
**呼叫方:** Confirm Gate 通過後（Web UI 點擊 / auto_execute_breaker.execute）、Phase 4 出場決策。

---

## 19. `trade_journal_tool` — 已定義

完整 schema 見 [`design-zh-TW.md` §4.3.1](design-zh-TW.md#431-trade_journal_tool-schemav3-擴充)。
Payload schema 見 [`llm-decision-schema.md` §4](llm-decision-schema.md#4-trade-journal-寫入-schemasqlite--fts5)（**SSOT**）。

---

## 20. `post_trade_review_tool` — 已定義

完整 schema 見 [`design-zh-TW.md` §4.3.2](design-zh-TW.md#432-post_trade_review_toolv3-新增)。
Rubric 見 [`post-trade-review-rubric.md`](post-trade-review-rubric.md)（**SSOT**）。

---

## 21. `proposal_tool` — 已定義

完整 schema 見 [`design-zh-TW.md` §4.3.3](design-zh-TW.md#433-proposal_toolv3-新增)。
驗證閘規則見 [`workflow-cheatsheet.md` §16](workflow-cheatsheet.md#16-策略改動提案--驗證--合併v3-新增閉環核心)。

---

## 附錄 A：哪些 Tool 不在這 21 個裡？

以下是 design 中**提及但不應該成為 tool**（屬於別的層）：

- ❌ `strategies/scoring.py` — 是 Strategy 內部函式，不是 tool（LLM 不直接呼叫，由 Phase 2B scheduler 呼叫）
- ❌ `strategies/sizing.py` — 同上，由系統覆寫流程呼叫
- ❌ `strategies/risk_gate.py` — 系統 gate，**不是** swarm 看到的 `risk_check_tool`（後者是 preview）
- ❌ `paper/auto_execute_breaker.py` — 系統 hook，不是 LLM 工具

## 附錄 B：未來可能新增

| 候選 | 觸發條件 |
|---|---|
| `optimization_tool`（Optuna） | 加入策略 hyperparameter 自動最佳化時 |
| `notification_tool`（Email/Telegram） | live 模式 + 出場通知需求 |
| `git_tool` | 自動 bump cheatsheet 版本 + tag 時 |

加新工具走 [`workflow-cheatsheet.md` §16 提案流程](workflow-cheatsheet.md#16-策略改動提案--驗證--合併v3-新增閉環核心)。
