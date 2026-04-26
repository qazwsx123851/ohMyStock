# Post-Trade Review Rubric — LLM 復盤五節點評分準則

> **版本**:v3.0 ｜ **更新日期**:2026-04-26
> **範圍**:`post_trade_review_team` swarm 五節點各自的評分 / 歸因細則
> **權威來源**:[`workflow-cheatsheet.md`](workflow-cheatsheet.md) §15
> **相關章節**:[`design-zh-TW.md`](design-zh-TW.md) §4.3.2 `post_trade_review_tool` / §4.7.2 `post_trade_review_team` swarm

---

## 0. 五節點 DAG 概覽

```
資料(data_loader)
    │ 區間 trade-journal + 後續 5/10/20 日報酬
    ▼
歸因(attributor)
    │ 逐筆分類為 6 類
    ▼
聚合(aggregator)
    │ 各維度命中率 / 期望值 / PF / MDD
    ▼
批判(critic)
    │ 標記勝率 / 期望值偏低的條件
    ▼
提案(proposer)
    │ 產出 proposals/<YYYY-MM-DD>-<topic>.md
```

每個節點都有獨立的 LLM 子代理人與 token 上限(見 design §4.7.2)。

---

## 1. 資料節點(`data_loader`)

### 任務
- 從 `trade_journal_tool.query` 撈出區間內所有 `kind=entry/exit` 條目
- 對每筆 `exit`,額外撈出**出場後 5/10/20 個交易日**的報酬
- 對每筆 `reject` / `expire` 收集理由統計

### 輸出格式

```json
{
  "period": {"from": "2026-04-01", "to": "2026-04-30"},
  "trades": [
    {
      "decision_id": "dec_2026-04-15T14-30-00_2330",
      "symbol": "2330",
      "entry_ts": "2026-04-15T14:36:18+08:00",
      "exit_ts": "2026-04-22T13:30:00+08:00",
      "entry_price": 845.0,
      "exit_price": 897.4,
      "pnl_pct": 6.2,
      "hold_days": 5,
      "exit_tag": "hit_t1",
      "thesis_held": true,
      "post_exit_return_5d": 1.8,
      "post_exit_return_10d": 4.3,
      "post_exit_return_20d": -2.1,
      "entry_thesis": "(完整 reasoning)",
      "cited_skills": ["technical/breakout", "..."],
      "risk_flags_at_entry": ["借券餘額 +18%"]
    }
  ],
  "rejected": [
    {"decision_id": "...", "reject_layer": "pre_check", "reject_reason": "..."}
  ],
  "expired": [
    {"decision_id": "...", "expire_reason": "30 分鐘 timeout"}
  ],
  "stats": {
    "total_entries": 23,
    "total_rejects": 8,
    "total_expires": 3,
    "expire_rate": 0.13
  }
}
```

### 品質檢查
- 後續報酬必須來自**真實市場資料**(透過 `market_data_tool.get_kline` 抓取),不可由 LLM 估算
- 若資料缺漏(個股下市 / 暫停交易) → 標記 `data_missing: true`,不參與聚合

---

## 2. 歸因節點(`attributor`)

### 任務
逐筆把交易分類為 6 類之一。LLM 必須對每筆寫**證據(evidence)**支持分類。

### 6 類歸因

| 類別 | 定義 | 期望比例(健康範圍) |
|---|---|---|
| `thesis_held` | 出場時 entry_thesis 仍有效,且**獲利或小虧** | 50–70% |
| `thesis_failed_but_profit` | thesis 失效但運氣好賺錢(警訊) | < 10% |
| `thesis_failed_loss` | thesis 失效且虧損(可學習) | 10–25% |
| `stop_saved` | 觸停損保本(若不停損會虧更多) | 5–15% |
| `time_stop_correct` | 7/10 日時間停損後續確實沒漲(正確判斷) | 5–10% |
| `time_stop_wrong` | 時間停損後**5/10 日內反彈 > 5%**(過早出場) | < 5% |

### 判斷依據

```python
# 對 attributor 的指引(prompt template 內注入)
def attribute_trade(trade):
    if trade.exit_tag == "time_stop":
        if trade.post_exit_return_5d > 0.05:
            return "time_stop_wrong"
        else:
            return "time_stop_correct"

    if trade.exit_tag == "hit_stop_loss":
        if trade.post_exit_return_10d < -0.05:  # 跌更多
            return "stop_saved"
        else:
            return "thesis_failed_loss"

    if trade.exit_tag in ["hit_t1", "hit_t1_5", "chandelier"]:
        if trade.thesis_held:
            return "thesis_held"
        else:
            return "thesis_failed_but_profit"  # 賺錢但 thesis 失效

    if trade.exit_tag == "thesis_invalid":
        return "thesis_failed_loss" if trade.pnl_pct < 0 else "thesis_failed_but_profit"

    # discretionary 由 LLM 主觀判斷
    return llm_classify(trade)
```

### 輸出

```json
{
  "attribution": [
    {
      "decision_id": "dec_2026-04-15T14-30-00_2330",
      "category": "thesis_held",
      "evidence": "出場 +6.2% 觸 T1,thesis 中提到的『外資連買 + 杯柄突破』整段持倉期間維持成立",
      "post_exit_return_5d": 1.8
    }
  ]
}
```

---

## 3. 聚合節點(`aggregator`)

### 任務
依多個維度做統計分析,產出 `metrics.json`。

### 必算指標

| 維度 | 指標 |
|---|---|
| **整體** | 勝率、PF、期望值、MDD、最大連敗、平均持倉天數 |
| **依進場條件** | 各 `cited_skill` 的命中率、期望值、樣本數 |
| **依 K 線型態** | VCP / 杯柄 / 平台突破 / 紅三兵 等命中率 |
| **依出場類型** | 各 `exit_tag` 的占比與平均報酬 |
| **依 confidence 區間** | LLM confidence 0.6-0.7 / 0.7-0.8 / 0.8-0.9 / 0.9+ 各區間勝率 |
| **依產業** | 各 sector 的命中率(找出該月強勢/弱勢產業) |
| **拒絕分析** | `pre_check / llm / risk_gate / human` 各層拒絕筆數 + 主因 |

### 輸出範例

```json
{
  "overall": {
    "win_rate": 0.565,
    "profit_factor": 1.84,
    "expectancy_pct": 4.2,
    "max_drawdown_pct": -3.8,
    "max_consecutive_loss": 2,
    "avg_hold_days": 6.2
  },
  "by_skill": {
    "technical/breakout": {"n": 12, "win_rate": 0.583, "expectancy": 5.1},
    "chip/three-major-investors": {"n": 18, "win_rate": 0.611, "expectancy": 4.8}
  },
  "by_pattern": {
    "VCP": {"n": 8, "win_rate": 0.375, "expectancy": -0.4},
    "杯柄突破": {"n": 5, "win_rate": 0.6, "expectancy": 6.3},
    "紅三兵": {"n": 6, "win_rate": 0.667, "expectancy": 5.9}
  },
  "by_exit_tag": {
    "hit_t1": {"count": 8, "avg_pnl": 6.0},
    "hit_stop_loss": {"count": 5, "avg_pnl": -5.7},
    "time_stop": {"count": 3, "avg_pnl": -1.2},
    "chandelier": {"count": 4, "avg_pnl": 12.4}
  },
  "by_confidence": {
    "0.6-0.7": {"n": 4, "win_rate": 0.25},
    "0.7-0.8": {"n": 11, "win_rate": 0.545},
    "0.8-0.9": {"n": 6, "win_rate": 0.833},
    "0.9-1.0": {"n": 2, "win_rate": 1.0}
  },
  "rejection_breakdown": {
    "pre_check": {"count": 5, "top_reason": "同產業已有 2 檔"},
    "llm": {"count": 2, "top_reason": "confidence < 0.6"},
    "risk_gate": {"count": 1, "top_reason": "處置股"},
    "human": {"count": 0}
  }
}
```

---

## 4. 批判節點(`critic`)

### 任務
對比 cheatsheet 各條規則,標記**勝率 / 期望值偏低**的條件。輸出文字批評(自然語言),作為提案節點的依據。

### 批判規則(LLM 必須檢查)

| 警示 | 觸發條件 | 處理 |
|---|---|---|
| **某 skill 拖累** | `by_skill` 中某項 win_rate < 40% 且 n ≥ 5 | 標記為「考慮放寬條件 / 移除」 |
| **某 K 線型態失效** | `by_pattern` 中某項 win_rate < 40% 且 n ≥ 5 | 提議改門檻或移除 |
| **低 confidence 反向有利** | confidence 0.6-0.7 區間 win_rate > 0.7-0.8 | LLM 過度自信,需校準 |
| **時間停損誤判率高** | `time_stop_wrong` / `time_stop_*` 比例 > 30% | 提議延長 7→10 日 |
| **拒絕率異常高** | `pre_check` 拒絕 > 進場數 1.5× | 過濾條件可能過嚴 |
| **expire 比例高** | `expire_rate > 0.20` | UI / 流程需檢討,訊號可能反應太慢 |
| **特定產業表現差** | 某 sector win_rate < 40% 且 n ≥ 3 | 提議短期排除該產業 |

### 輸出格式

```markdown
## 批判摘要

### 高警示(建議立即處理)
1. **VCP 型態命中率僅 37.5%(8 筆)**:遠低於整體 56.5%。檢視 evidence 發現多數失敗案例量能僅勉強達 1.5×,建議放寬至 1.3× 但要求收盤站穩 EMA10。
2. **time_stop_wrong 占 time_stop 75%**(3/4):動能股需要更長發酵時間,建議 7 日減半改為 9 日。

### 中警示
3. **confidence 0.7-0.8 win_rate 0.545,vs 0.8-0.9 為 0.833**:LLM 在中等信心區間判斷力不足,可能需要更多 tool calls 或縮小決策空間。

### 觀察項(尚不需動規則)
4. 半導體產業本月 win_rate 50%,樣本不足。
```

---

## 5. 提案節點(`proposer`)

### 任務
將批判轉換為**結構化提案**(`proposals/*.md`),供 §16 驗證閘 + 人工 PR review。

### 提案輸出規範

每個高/中警示產出 1 份 proposal,寫到 `proposals/<YYYY-MM-DD>-<topic>.md`。topic 命名規則:`<area>-<change>`,例:
- `vcp-volume-threshold`
- `time-stop-extend-vcp`
- `confidence-calibration`

### 必填欄位
見 [`proposals/README.md`](../proposals/README.md) 模板。

### 範例

```markdown
---
proposal_id: 2026-04-30-vcp-volume-threshold
target_section: cheatsheet §6.4 加分項 + §9 K 線型態庫
status: pending
created_by: post_trade_review_team
created_at: 2026-04-30T19:30:00+08:00
review_id: 2026-04
---

## 改動描述
VCP 型態量能門檻 1.5× → 1.3× 五日均量,但**新增條件**「收盤站穩 EMA10」。

## 動機與佐證
- reviews/2026-04/metrics.json `by_pattern.VCP`:n=8, win_rate=0.375, expectancy=-0.4%
- 失敗案例 6 筆中 5 筆量能勉強達 1.5×(平均 1.58×),但收盤未站穩 EMA10
- 通過案例 2 筆量能 1.4×, 1.3× 但都收盤站穩 EMA10
- 假設改門檻為「1.3× + 站穩 EMA10」,過去 8 筆中 5 筆會被過濾,剩 3 筆假設都通過,prospective win_rate 0.667

## 改動 diff 草稿
\`\`\`diff
--- workflow-cheatsheet.md §6.4 加分項
- 看漲 K 線型態(吞噬 / 晨星 / 紅 K 站上 20MA / VCP / 杯柄突破)
+ 看漲 K 線型態(吞噬 / 晨星 / 紅 K 站上 20MA / VCP【收盤站穩 EMA10 + 量能 ≥ 1.3×】 / 杯柄突破)
\`\`\`

## 預期影響範圍
- `src/ohmystock/strategies/_kpattern/vcp.py`(detector 邏輯)
- `src/ohmystock/strategies/tw_momentum_swing/scoring.py`(加分邏輯)
- `skills/technical/breakout.md`(描述更新)

## 風險評估
- 過於嚴格可能漏掉真正的 VCP 突破(歷史 2 檔通過案例都符合新條件,風險可控)
- 若 EMA10 過於敏感,可能在震盪市產生雜訊 → 需 WFA 在 2022 熊市段驗證
```

---

## 6. Token 預算與模型分配

對應 design §4.7.2 設定:

| 節點 | 模型 | Input Budget | Output Budget |
|---|---|---|---|
| data_loader | Haiku 4.5 | 4K | 4K |
| attributor | Sonnet 4.6 | 30K | 4K |
| aggregator | Sonnet 4.6 | 30K | 2K |
| critic | Opus 4.7 | 50K(含全部 cheatsheet) | 4K |
| proposer | Opus 4.7 | 30K | 8K(每份提案 ≈ 2K) |

預估每月度復盤總成本:約 50K~150K input tokens(視交易筆數)。

---

## 7. 品質檢查 / 自我評估

每次復盤完成後,系統自動驗證:

- 攻擊性檢查:每個批判 / 提案是否引用了具體的 metrics.json 路徑(JSON pointer)?無引用則標記 `unevidence` 退回 critic 重做
- 一致性檢查:同一份復盤產出的 proposals 不可互相矛盾(例如同時提議「放寬 VCP」與「移除 VCP」)
- 重複檢查:若提案內容與**過去 3 個月已合併**的提案相同 → 標記 `duplicate`,提示人工審視

---

## 8. 變更管理

本 rubric 變動需:
1. bump 文件 Changelog
2. 對齊 cheatsheet §15 與 design §4.7.2 swarm 設定
3. 重跑黃金樣本驗證(2026-Q1 復盤的歸因不可大幅變動)
