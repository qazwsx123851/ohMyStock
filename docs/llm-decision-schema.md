# LLM Decision Schema — Phase 3 進場決策資料結構

> **版本**：v3.0 ｜ **更新日期**：2026-04-26
> **範圍**:Phase 3 LLM Decider 的輸入 / 輸出與 Trade Journal 的儲存格式
> **權威來源**:[`workflow-cheatsheet.md`](workflow-cheatsheet.md) §6.5 / §6.8
> **相關章節**:[`design-zh-TW.md`](design-zh-TW.md) §4.3.1 `trade_journal_tool` / §4.6.1 Trade Journal as Memory / §4.7.1 `entry_decision_team` swarm

---

## 1. LLM Decider 輸入 schema

由 `entry_decision_team` swarm 編排器自動組裝,送進 PM 結論節點。

```json
{
  "input_schema_version": "v3.0",
  "decision_id": "dec_2026-04-30T14-30-00_2330",
  "trigger_at": "2026-04-30T14:30:00+08:00",
  "candidate": {
    "symbol": "2330",
    "name": "台積電",
    "final_score": 78,
    "tech_score": 28,
    "chip_score": 36,
    "industry_score": 8,
    "sentiment_score": 6,
    "ema20_distance_pct": 3.2,
    "atr_14_pct": 2.4,
    "current_price": 845.0
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
      "站穩突破/收盤陽 K 確認",
      "量能 ≥ 1.5× 5 日均量",
      "近 5 日 RS > 大盤"
    ],
    "bonus_items": [
      "看漲 K 線型態",
      "週線確認",
      "RSI 35-75",
      "EMA 多頭排列",
      "外資/投信當日買超",
      "主力分點 ≥ 25% 或集保遞減",
      "近 5 日融資增幅 < 10%",
      "7 日內正面催化劑"
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
    "technical/breakout",
    "technical/ma-crossover",
    "chip/three-major-investors",
    "chip/broker-branch",
    "chip/securities-lending",
    "tw_specific/momentum-swing"
  ]
}
```

---

## 2. LLM Decider 輸出 schema(嚴格 JSON,PM 結論節點必須輸出)

```json
{
  "output_schema_version": "v3.0",
  "decision_id": "dec_2026-04-30T14-30-00_2330",
  "decided_at": "2026-04-30T14:34:22+08:00",
  "model": "claude-opus-4-7",
  "decision": "enter",
  "confidence": 0.83,
  "must_have_check": [
    {
      "name": "breakout_close",
      "pass": true,
      "evidence": "當日收 845 > 開 838 > 突破點 832,符合"
    },
    {
      "name": "volume_15x",
      "pass": true,
      "evidence": "當日量 38,420 張 / 5 日均量 22,140 張 = 1.74×"
    },
    {
      "name": "rs_above_index",
      "pass": true,
      "evidence": "近 5 日 2330 +4.2% vs TAIEX +1.1%"
    }
  ],
  "bonus_score": 6,
  "bonus_breakdown": [
    {"name": "bullish_pattern", "pass": true, "evidence": "形成杯柄突破"},
    {"name": "weekly_confirm", "pass": true, "evidence": "週線站上 20MA"},
    {"name": "rsi_in_range", "pass": true, "evidence": "RSI(14) = 62.4"},
    {"name": "ema_aligned", "pass": true, "evidence": "EMA5 > EMA10 > EMA20"},
    {"name": "institutional_buy", "pass": true, "evidence": "外資 +12,400 張、投信 +1,820 張"},
    {"name": "broker_concentration", "pass": true, "evidence": "前 15 大買超佔 28.4%"},
    {"name": "margin_modest", "pass": false, "evidence": "近 5 日融資 +12.3%(略高)"},
    {"name": "catalyst_recent", "pass": false, "evidence": "近 7 日無重大重訊"}
  ],
  "proposed_sizing_pct": 18.0,
  "expected_holding_days": 8,
  "reasoning": "2330 滿足 Must-have 三項全過,加分項通過 6/8。...(≥ 200 字的完整論點)",
  "cited_skills": [
    "technical/breakout",
    "chip/three-major-investors",
    "tw_specific/momentum-swing"
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
| `bonus_score` | int | 0~8;< 4 系統強制改為 `reject` |
| `proposed_sizing_pct` | float | 0.0~25.0;系統會與 Volatility Targeting 公式取較小者 |
| `reasoning` | str | ≥ 200 字;低於則拒收 |
| `cited_skills` | list[str] | ≥ 1 項;空陣列拒收 |
| `expected_holding_days` | int | 1~30;用於 §7.B 時間停損校準 |

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
  "thesis_invalidation": ["綜合分數降 > 15", "RS 轉負", "..."],
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
  "risk_flags": ["借券餘額近 10 日 +18%", "融資增幅 +12.3%"]
}
```

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
