# LLM Decision Schema — Phase 3 進場決策資料結構

> **版本**：v3.1 ｜ **更新日期**：2026-04-28
> **範圍**:Phase 3 LLM Decider 的輸入 / 輸出與 Trade Journal 的儲存格式
> **權威來源**:[`workflow-cheatsheet.md`](workflow-cheatsheet.md) §6.5 / §6.8
> **相關章節**:[`design-zh-TW.md`](design-zh-TW.md) §4.3.1 `trade_journal_tool` / §4.6.1 Trade Journal as Memory / §4.7.1 `entry_decision_team` swarm
>
> **v3.0 → v3.1 變動**：配合 [`workflow-cheatsheet.md`](workflow-cheatsheet.md) v3.1 引入 Mark Minervini SEPA 框架，新增 5 個 SEPA 欄位（`stage` / `rs_percentile` / `trend_template_passed` / `vcp_quality` / `pivot_price`）至 LLM 輸入候選快照、輸出 schema、Trade Journal entry。**僅追加，不刪改既有欄位**（依 §6 Schema 演進規範）。

---

## 1. LLM Decider 輸入 schema

由 `entry_decision_team` swarm 編排器自動組裝,送進 PM 結論節點。

```json
{
  "input_schema_version": "v3.1",
  "decision_id": "dec_2026-04-30T14-30-00_2330",
  "trigger_at": "2026-04-30T14:30:00+08:00",
  "candidate": {
    "symbol": "2330",
    "name": "台積電",
    "final_score": 78,
    "tech_score": 32,
    "chip_score": 18,
    "fundamental_score": 22,
    "sentiment_score": 6,
    "ema20_distance_pct": 3.2,
    "atr_14_pct": 2.4,
    "current_price": 845.0,
    "stage": 2,
    "rs_percentile": 87,
    "trend_template_passed": 8,
    "vcp_quality": "breakout",
    "pivot_price": 832.0,
    "distance_from_52w_high_pct": 4.1,
    "distance_from_52w_low_pct": 41.6
  },
  "market_context": {
    "risk_off": false,
    "monthly_pnl_pct": -1.8,
    "recent_20_winrate": 0.55,
    "consecutive_loss": 1,
    "existing_positions": [
      {"symbol": "2454", "sector": "半導體", "exposure_pct": 18.0},
      {"symbol": "2317", "sector": "電子組裝", "exposure_pct": 12.0}
    ],
    "total_exposure_pct": 30.0,
    "same_sector_count": 1
  },
  "rules_summary": {
    "must_have": [
      "Trend Template 8/8 全過（依 §2 第一層）",
      "Stage 2 確認（依 §0.4 / §2 第三層）",
      "VCP/杯柄/平台 + Pivot Breakout 量能（≥ 1.4× 20DMA、Pivot~Pivot+5%）"
    ],
    "bonus_items": [
      "季 EPS YoY ≥ 25%（且本季 > 前季加速）",
      "月營收 YoY ≥ 20% 且創歷史新高",
      "RS Percentile ≥ 80",
      "距 52 週高 ≤ 15%",
      "VCP 收縮 ≥ 4 次（每次振幅 ≤ 前次 50%）",
      "機構持股遞增（外資/投信 30 日 + 主力分點 ≥ 25%）",
      "產業 RS 領先（產業 RS Percentile ≥ 80）",
      "新高 + 量爆（突破 52 週新高 + 量 ≥ 1.5× 20DMA）"
    ]
  },
  "available_tools": [
    "market_data_tool",
    "chip_data_tool",
    "pattern_recognition_tool",
    "news_sentiment_tool",
    "fundamental_data_tool"
  ],
  "available_skills": [
    "technical/trend-template",
    "technical/stage-analysis",
    "technical/vcp-pivot",
    "technical/breakout",
    "chip/three-major-investors",
    "chip/broker-branch",
    "chip/securities-lending",
    "fundamental/eps-growth",
    "fundamental/revenue-growth",
    "tw_specific/momentum-swing",
    "tw_specific/rs-percentile"
  ]
}
```

---

## 2. LLM Decider 輸出 schema(嚴格 JSON,PM 結論節點必須輸出)

```json
{
  "output_schema_version": "v3.1",
  "decision_id": "dec_2026-04-30T14-30-00_2330",
  "decided_at": "2026-04-30T14:34:22+08:00",
  "model": "claude-opus-4-7",
  "decision": "enter",
  "confidence": 0.83,
  "stage": 2,
  "rs_percentile": 87,
  "trend_template_passed": 8,
  "vcp_quality": "breakout",
  "pivot_price": 832.0,
  "must_have_check": [
    {
      "name": "trend_template_8_of_8",
      "pass": true,
      "evidence": "(1) 845 > MA50(810) ✓ (2) MA50 > MA150(782) ✓ (3) MA150 > MA200(745) ✓ (4) 845 > MA150 ✓ (5) 845 > MA200 ✓ (6) MA200 過去 65 日上升 ✓ (7) 距 52W 高 870 為 -2.9% (≤25%) ✓ (8) RS Percentile 87 ≥ 65 ✓"
    },
    {
      "name": "stage_2_confirmed",
      "pass": true,
      "evidence": "多頭排列 + MA200 ≥ 65 日上升 + 30 日內振幅 14% (≤20%, 非 Stage 3)"
    },
    {
      "name": "vcp_pivot_breakout_with_volume",
      "pass": true,
      "evidence": "杯柄突破，Pivot=832；當日收 845 在 Pivot~Pivot+5% (832~873.6) 內；量 38,420 張 / 20DMA 22,140 張 = 1.74× (≥1.4×) ✓；收 > 20MA(820) ✓"
    }
  ],
  "bonus_score": 6,
  "bonus_breakdown": [
    {"name": "eps_yoy_25", "pass": true, "evidence": "Q1 EPS YoY +32% 且 vs Q4 +28% 加速 +4pp（接近門檻）"},
    {"name": "revenue_yoy_20_new_high", "pass": true, "evidence": "3 月營收 YoY +24%、創歷史新高"},
    {"name": "rs_percentile_80", "pass": true, "evidence": "RS Percentile 87 ≥ 80"},
    {"name": "distance_52w_high_15", "pass": true, "evidence": "距 52W 高 -2.9% ≤ 15%"},
    {"name": "vcp_contractions_4plus", "pass": false, "evidence": "本次為杯柄非教科書級 VCP，僅 2 次回檔"},
    {"name": "institutional_buy_increasing", "pass": true, "evidence": "外資 30 日持股 +0.8%、主力分點集中度 28.4%"},
    {"name": "industry_rs_leadership", "pass": true, "evidence": "半導體產業 RS Percentile 92 ≥ 80"},
    {"name": "new_high_volume_burst", "pass": false, "evidence": "突破未創 52 週新高 (854 仍距 870 約 -1.0%)"}
  ],
  "proposed_sizing_pct": 18.0,
  "expected_holding_days": 8,
  "reasoning": "2330 滿足 Must-have 三項 SEPA 三柱全過：(a) Trend Template 8/8 全過、(b) Stage 2 確認 + 多頭排列健康、(c) 杯柄突破 Pivot=832 量能 1.74× 20DMA。加分項通過 6/8（季 EPS 加速 + 月營收創高 + RS Percentile 87 + 距 52W 高 -2.9% + 機構買增 + 產業 RS 領先；VCP 收縮次數不足 4 次 + 未創 52W 新高）。...(≥ 200 字的完整論點)",
  "cited_skills": [
    "technical/trend-template",
    "technical/stage-analysis",
    "technical/vcp-pivot",
    "chip/three-major-investors",
    "fundamental/eps-growth",
    "tw_specific/momentum-swing",
    "tw_specific/rs-percentile"
  ],
  "invalidation_conditions": [
    "綜合分數降 > 15",
    "RS 由正轉負",
    "投信連 3 日賣超",
    "借券餘額 5 日 +30%",
    "外資轉賣超 + 收盤跌破突破點"
  ],
  "risk_flags": [
    "借券餘額近 10 日 +18%(接近警戒)",
    "融資增幅 +12.3% 略高於 10% 門檻"
  ],
  "tool_calls_summary": [
    {"tool": "chip_data_tool", "action": "get_three_major_investors", "elapsed_ms": 412},
    {"tool": "pattern_recognition_tool", "action": "detect_cup_handle", "elapsed_ms": 890},
    {"tool": "market_data_tool", "action": "get_kline", "elapsed_ms": 230}
  ]
}
```

### 2.1 欄位約束(系統強制驗證)

| 欄位 | 型別 | 約束 |
|---|---|---|
| `decision` | enum | `enter / reject / reduce_size` 三選一 |
| `confidence` | float | 0.0~1.0;< 0.6 系統強制改為 `reject` |
| `must_have_check` | list | 必須 3 項;任一 `pass=false` 系統強制改為 `reject` |
| `must_have_check[*].name` | enum | v3.1 SEPA 三柱：`trend_template_8_of_8` / `stage_2_confirmed` / `vcp_pivot_breakout_with_volume`（v3.0 三項已 deprecated） |
| `bonus_score` | int | 0~8;< 4 系統強制改為 `reject` |
| `proposed_sizing_pct` | float | 0.0~25.0;系統會與 Volatility Targeting 公式取較小者 |
| `reasoning` | str | ≥ 200 字;低於則拒收 |
| `cited_skills` | list[str] | ≥ 1 項;空陣列拒收 |
| `expected_holding_days` | int | 1~30;用於 §7.B 時間停損校準 |
| **`stage`**（v3.1 新增） | enum | `1 \| 2 \| 3 \| 4`；若 `stage=4` 則系統強制改為 `reject`（依 [`workflow-cheatsheet.md`](workflow-cheatsheet.md) §0.4）；`stage=3` LLM 可仍 `enter` 但 sizing 上限降至 10% |
| **`rs_percentile`**（v3.1 新增） | int | `0~99`；< 65 時 must_have_check `trend_template_8_of_8` 自動 fail（LLM 不可繞過） |
| **`trend_template_passed`**（v3.1 新增） | int | `0~8`；< 8 時 must_have_check `trend_template_8_of_8` 自動 fail |
| **`vcp_quality`**（v3.1 新增） | enum | `none \| forming \| textbook \| breakout`；若 `none` 或 `forming` 則 must_have_check `vcp_pivot_breakout_with_volume` 自動 fail（須等型態完成） |
| **`pivot_price`**（v3.1 新增） | float \| null | 僅當 `vcp_quality ∈ {textbook, breakout}` 時必為 float（> 0）；否則應為 `null`。進場價必須在 `[pivot_price, pivot_price × 1.05]` 內，否則 must_have_check 第三柱自動 fail |

---

## 3. 系統覆寫後的最終決策(Confirm Gate 看到的內容)

LLM 輸出 → 系統 Sizing Service / ATR Service / Risk Gate 處理後產出:

```json
{
  "final_decision_id": "dec_2026-04-30T14-30-00_2330",
  "decision": "enter",
  "llm_confidence": 0.83,
  "llm_proposed_sizing_pct": 18.0,
  "system_calculated_sizing_pct": 16.5,
  "final_sizing_pct": 16.5,
  "sizing_overridden": true,
  "sizing_override_reason": "Volatility Targeting 公式取較小值",
  "final_qty_lots": 19,
  "final_notional_twd": 1605500,
  "stop_loss_price": 822.4,
  "stop_loss_method": "max(進場×0.94, 進場-2×ATR(14))",
  "t1_target": 895.7,
  "t1_5_target": 946.4,
  "chandelier_atr_22": 18.6,
  "risk_gate_status": "approved",
  "auto_execute_eligible": false,
  "auto_execute_blocker": null,
  "confirm_gate_mode": "human",
  "confirm_expires_at": "2026-04-30T15:04:22+08:00"
}
```

`confirm_gate_mode` 取值:
- `human`:`OHMYSTOCK_AUTO_EXECUTE=false` 預設
- `auto`:`OHMYSTOCK_AUTO_EXECUTE=true` 且通過防線 9 全部熔斷
- `auto_fallback_human`:自動模式但任一熔斷觸發,改人工 confirm

---

## 4. Trade Journal 寫入 schema(SQLite + FTS5)

> 🔖 **本檔為 Trade Journal schema 的唯一權威**（SSOT）。
> design-zh-TW.md §4.6.1 / 其他文件**只能 reference 本節**，不可重複定義欄位或 CREATE TABLE。
> Schema 演進依 §6 規範（v3.0 → v3.1 只加欄位不刪）。

每個生命週期階段都寫一筆:

### 4.1 `kind=entry` (進場確認後)

```json
{
  "journal_id": "j_20260430_001",
  "decision_id": "dec_2026-04-30T14-30-00_2330",
  "kind": "entry",
  "symbol": "2330",
  "ts": "2026-04-30T14:34:22+08:00",
  "llm_decision_id": "dec_2026-04-30T14-30-00_2330",
  "llm_model": "claude-opus-4-7",
  "llm_confidence": 0.83,
  "llm_reasoning": "(完整 reasoning 文字)",
  "cited_skills": ["technical/breakout", "chip/three-major-investors", "tw_specific/momentum-swing"],
  "tool_calls": [
    {"tool": "chip_data_tool", "input": {...}, "output_summary": "..."},
    "..."
  ],
  "llm_input_tokens": 18420,
  "llm_output_tokens": 1240,
  "llm_cost_usd": 0.0276,
  "entry_thesis": "(可全文檢索的論點摘要)",
  "thesis_invalidation": ["綜合分數降 > 15", "RS Percentile 跌破 50", "Stage 由 2 轉 3", "VCP pivot 跌破", "..."],
  "atr_at_entry": 20.3,
  "risk_regime_at_entry": "risk_on",
  "proposed_sizing_pct": 18.0,
  "final_sizing_pct": 16.5,
  "stop_loss_price": 822.4,
  "auto_executed": false,
  "human_confirmed_by": "user@example.local",
  "human_confirmed_at": "2026-04-30T14:36:18+08:00",
  "decision_status": "confirmed",
  "expected_holding_days": 8,
  "risk_flags": ["借券餘額近 10 日 +18%", "融資增幅 +12.3%"],
  "stage": 2,
  "rs_percentile": 87,
  "trend_template_passed": 8,
  "vcp_quality": "breakout",
  "pivot_price": 832.0
}
```

> **v3.1 SEPA 欄位（追加，向後相容）**：`stage` / `rs_percentile` / `trend_template_passed` / `vcp_quality` / `pivot_price` 五欄寫入 `kind=entry` journal。`kind=exit` 不重複寫（出場時 SEPA 狀態已變動，不具 snapshot 價值）；Phase 5 復盤的 data_loader 從 entry record 取此 5 欄做歸因（依 §4.5）。

> **v3 決策 #15**：所有 `kind=*` 紀錄中**只要該決策呼叫過 LLM**，都必含 `llm_input_tokens` / `llm_output_tokens` / `llm_cost_usd` 三欄；單純由系統規則觸發的 `kind=reject`（如 Risk Gate 硬擋）不含 LLM 成本欄。月成本由 Admin Dashboard 即時聚合（詳 [`frontend.md`](frontend.md) §17.B），達 80% 預算（USD $40）警示、達 100% 觸發軟熔斷（詳 [`safety-and-simulation.md`](safety-and-simulation.md) §2.11）。

### 4.2 `kind=exit` (Phase 4 出場後)

```json
{
  "journal_id": "j_20260507_002",
  "decision_id": "dec_2026-04-30T14-30-00_2330",
  "kind": "exit",
  "symbol": "2330",
  "ts": "2026-05-07T13:30:00+08:00",
  "exit_reason": "T1 +6% 觸及,出場 50%",
  "exit_tag": "hit_t1",
  "pnl_pct": 6.2,
  "hold_days": 5,
  "thesis_held": true,
  "vs_expected_holding": -3,
  "remaining_lots": 9,
  "remaining_strategy": "T1.5 + Chandelier 衛星倉"
}
```

### 4.3 `kind=reject` (硬性檢查或 LLM 拒絕)

```json
{
  "journal_id": "j_20260430_003",
  "decision_id": "dec_2026-04-30T15-00-00_3008",
  "kind": "reject",
  "symbol": "3008",
  "ts": "2026-05-01T14:30:00+08:00",
  "reject_layer": "pre_check",
  "reject_reason": "同產業已有 2 檔(3008 屬光學;持倉已有 6488/3406)",
  "decision_status": "rejected"
}
```

`reject_layer` 取值:
- `pre_check`:cheatsheet §6.1 前置硬性檢查擋下,**未送 LLM**
- `llm`:LLM 自己決定 reject(`decision=reject` 或 `confidence < 0.6`)
- `risk_gate`:LLM 通過但 Risk Gate 拒絕(處置/警示/漲跌停)
- `human`:人工 confirm 階段被使用者拒絕

### 4.4 `kind=expire` (Confirm Gate 過期未處理)

```json
{
  "journal_id": "j_20260430_004",
  "decision_id": "dec_2026-04-30T14-30-00_4904",
  "kind": "expire",
  "symbol": "4904",
  "ts": "2026-04-30T15:04:22+08:00",
  "expire_reason": "30 分鐘 timeout 未 confirm",
  "decision_status": "expired"
}
```

---

## 4.5 衍生 / Join 欄位（Phase 5 復盤需要）

> 🔖 **本節為 `post_trade_review_team` data_loader 節點需要、但不直接寫在 journal_entries 表內的衍生欄位**之規範。data_loader 必須做 entry/exit 配對 + 外部資料補回，產出符合 [`post-trade-review-rubric.md` §1](post-trade-review-rubric.md) 期望的 trade record。

### 4.5.1 必備衍生欄位

| 欄位 | 來源 | 計算方式 |
|---|---|---|
| `entry_price` | `kind=entry` 條目 | 從 `actual_entry_price`（confirm 通過後寫入 entry record）取；若進場路徑 = paper_trade_tool，則從對應的 `order.fill_price` 補 |
| `exit_price` | `kind=exit` 條目 | `actual_exit_price`（已在 §4.2 schema） |
| `entry_pattern` | `kind=entry`.`bonus_breakdown.bullish_pattern.evidence` 文本 | LLM 進場時引用的型態名（VCP / 杯柄 / 平台突破）— 若 evidence 文本含明確型態名就抽出；否則 fallback `cited_skills` 內 `technical/breakout` / `technical/vcp` 等 |
| `sector` | `market_context.existing_positions[].sector` 或 universe 表 | 進場當下查 `data/universe.py` 的 sector mapping；寫入 entry record 時 snapshot |
| `post_exit_return_5d / 10d / 20d` | `market_data_tool.get_post_exit_returns(symbol, exit_date)` | exit 後 N 日股價漲跌 — data_loader 跑時即時查（如 N 日尚未滿足則回 `null`） |
| `holding_days` | (`exit_ts` − `entry_ts`) | 已含於 `kind=exit`.`hold_days`，但 data_loader 必須驗證一致性 |
| `expected_holding_days` | `kind=entry`.`expected_holding_days` | 用於計算 §2 attributor 的 `vs_expected_holding` ratio |

### 4.5.2 Entry / Exit 配對邏輯

**Join key:** `decision_id`（一筆 entry 必有對應的 0 或 1 筆 exit）。

**配對狀態機：**
- `entry` 寫入 → `confirm` 通過 → `paper_trade.fill` → 更新 entry 的 `actual_entry_price`、`actual_qty`
- `Phase 4` 出場觸發 → 寫 `exit`，含 `decision_id` 連結 → entry 標記 closed
- 若同 `decision_id` 有 entry 但無 exit → 視為 **open position**（不進入 review 樣本）
- 若有 entry + exit_tag = `expire` → 不算交易，計入 §3 aggregator 的 `expire_count`

### 4.5.3 Snapshot 寫入時機（避免 race / 資料漂移）

| 欄位 | 寫入時機 | 為什麼 snapshot |
|---|---|---|
| `sector` | entry 寫入時 | 公司可能改類別（如 KY 股回台、產業重分類），事後查會錯 |
| `entry_pattern` | entry 寫入時 | 後續價格走勢會改變型態判讀，但決策當下的引用必須鎖定 |
| `cited_skills` | entry 寫入時 | skill 版本可能 bump，需鎖當下版本 |

### 4.5.4 給 data_loader 實作者的 Pydantic 草稿

```python
# src/ohmystock/memory/review_loader.py
class TradeRecord(BaseModel):
    """post_trade_review_team data_loader 節點輸出的單筆紀錄"""
    decision_id: str
    symbol: str
    sector: str                       # 4.5.3 snapshot
    entry_ts: datetime
    exit_ts: datetime | None
    entry_price: float                # 4.5.1
    exit_price: float | None
    qty: int
    entry_pattern: str | None         # 4.5.1
    entry_thesis: str                 # FTS5 全文用
    cited_skills: list[str]
    bonus_score: int
    confidence: float
    pnl_pct: float | None
    holding_days: int | None
    expected_holding_days: int
    exit_tag: Literal["hit_t1","hit_t1_5","stopped","time_stopped","thesis_invalid","expire","other"] | None
    thesis_held: bool | None
    post_exit_return_5d: float | None  # 4.5.1
    post_exit_return_10d: float | None
    post_exit_return_20d: float | None
    # v3.1 SEPA 欄位（snapshot at entry）
    stage: Literal[1, 2, 3, 4]
    rs_percentile: int                # 0~99
    trend_template_passed: int        # 0~8
    vcp_quality: Literal["none", "forming", "textbook", "breakout"]
    pivot_price: float | None
```

---

## 5. FTS5 查詢範例

```python
# 找過去類似情境(VCP 突破 + 外資連買)
journal.fts_search("VCP 突破 外資 連買", limit=20)

# 找全部 thesis 失效但賺錢的案例(學習矛盾訊號)
journal.query(thesis_held=False, pnl_pct__gt=0)

# 找特定型態的歷史命中率
journal.query(
    cited_skills__contains="technical/breakout",
    exit_tag__in=["hit_t1", "hit_t1_5"]
)

# 找復盤批判用:過去 30 筆 VCP 命中率
journal.aggregate(
    where={"entry_pattern": "VCP"},
    group_by="exit_tag",
    metrics=["count", "avg_pnl_pct"]
)
```

---

## 6. Schema 演進規範

- 新增欄位需 bump `schema_version`(例 v3.0 → v3.1)
- **不得移除既有欄位**(向後相容);不再使用的欄位標記 `deprecated`
- 欄位語意變動需在本文件 Changelog 註記
- FTS5 表 schema 變動必須提供 migration script(寫於 `src/ohmystock/memory/migrations/`)
