# Reviews — LLM 復盤輸出(自我改進迴圈的記憶體)

> **版本**:v3.0 ｜ **建立日期**:2026-04-26
> **權威來源**:[`docs/workflow-cheatsheet.md`](../docs/workflow-cheatsheet.md) §15
> **相關章節**:[`docs/post-trade-review-rubric.md`](../docs/post-trade-review-rubric.md) / [`docs/design-zh-TW.md`](../docs/design-zh-TW.md) §4.7.2 / [`proposals/README.md`](../proposals/README.md)

---

## 1. 此資料夾用途

存放 **`post_trade_review_team` swarm 產出的歷史復盤資料**。每次復盤(月度自動 / 季底自動 / 人工觸發 / 月度熔斷強制)產出一個資料夾,包含五節點 DAG 的所有輸出。

**這是系統「自我改進迴圈」的記憶體**:每份復盤都對應一次「我們從這段交易學到了什麼 + 我們提出了哪些改動」。沒有它,系統無法跨時間累積經驗,也無法給下一輪 LLM 復盤足夠的歷史 context。

對應 cheatsheet §15.3 輸出規範。

---

## 2. 觸發來源(對應 cheatsheet §15.1)

| 觸發 | 路徑 | 命名 |
|---|---|---|
| 月度自動 | 每月 1 號 19:00 | `reviews/2026-04/` |
| 季度自動 | 季底(3/31、6/30、9/30、12/31) 19:00 | `reviews/2026-Q1/` |
| 月度熔斷強制 | cheatsheet §0 觸發 -8% 熔斷後 | `reviews/forced-2026-04/` |
| 人工觸發 | CLI / UI 指定區間 | `reviews/manual-2026-04-15-to-2026-04-22/` |

---

## 3. 目錄結構

```
reviews/
├── README.md                            # 本檔
├── _index.json                          # 全部復盤的索引(自動維護)
├── 2026-04/                             # 月度復盤
│   ├── data.json                        # 資料節點輸出(原始 trade-journal 快照 + 後續報酬)
│   ├── attribution.json                 # 歸因節點輸出(逐筆 6 類分類)
│   ├── metrics.json                     # 聚合節點輸出(各維度指標)
│   ├── critique.md                      # 批判節點輸出(自然語言批評)
│   ├── report.md                        # 給人類讀的復盤總報告
│   ├── proposals_created.md             # 本次復盤產生的提案清單(連結到 proposals/)
│   └── rejected_proposals.md            # 驗證閘失敗的提案 + 原因
│
├── 2026-Q1/                             # 季度復盤
│   └── (同上結構,但範圍更大)
│
├── forced-2026-04/                      # 月度熔斷強制復盤
│   └── (同上,priority=high,需在月底前完成)
│
└── manual-2026-04-15-to-2026-04-22/     # 人工觸發
    └── (同上)
```

---

## 4. 必產出檔案規範

每個 review 資料夾**必須**包含以下檔案(由 swarm 各節點順序產出):

### 4.1 `data.json`(資料節點)
- 完整 trade-journal 快照 + 出場後 5/10/20 日報酬
- Schema 見 [`docs/post-trade-review-rubric.md`](../docs/post-trade-review-rubric.md) §1

### 4.2 `attribution.json`(歸因節點)
```json
{
  "review_id": "2026-04",
  "attribution": [
    {
      "decision_id": "dec_2026-04-15T14-30-00_2330",
      "category": "thesis_held",
      "evidence": "出場 +6.2% 觸 T1...",
      "post_exit_return_5d": 1.8
    }
  ],
  "category_distribution": {
    "thesis_held": 12,
    "thesis_failed_but_profit": 3,
    "thesis_failed_loss": 5,
    "stop_saved": 2,
    "time_stop_correct": 1,
    "time_stop_wrong": 0
  }
}
```

### 4.3 `metrics.json`(聚合節點)
- 各維度指標(整體、by_skill、by_pattern、by_exit_tag、by_confidence、by_sector、rejection_breakdown)
- 完整 schema 見 rubric §3
- **此檔是 proposals 佐證連結的目標**(JSON pointer:`reviews/2026-04/metrics.json#/by_pattern/VCP`)

### 4.4 `critique.md`(批判節點)
- 自然語言批評,標記高/中/低警示
- 必須引用 `metrics.json` 的具體指標

### 4.5 `report.md`(總報告,給人類讀)
- 復盤期間概覽
- 頂層摘要(2-3 段)
- 連結到 attribution / metrics / proposals
- 給主管 / 自己定期回顧用

### 4.6 `proposals_created.md`
本次復盤產生的提案清單:
```markdown
# 2026-04 月度復盤產生的提案

| Proposal | Status | Priority | Target |
|---|---|---|---|
| [2026-04-30-vcp-volume-threshold](../../proposals/2026-04-30-vcp-volume-threshold.md) | pending | high | cheatsheet §6.4 |
| [2026-04-30-time-stop-extend-vcp](../../proposals/2026-04-30-time-stop-extend-vcp.md) | pending | medium | cheatsheet §7.B |
```

### 4.7 `rejected_proposals.md`
驗證閘失敗或重複的提案 + 原因(供之後不要再重複提相同改動)。

---

## 5. `_index.json`(全部復盤的索引,自動維護)

```json
{
  "schema_version": "v3.0",
  "last_updated": "2026-04-30T19:45:00+08:00",
  "reviews": [
    {
      "review_id": "2026-04",
      "kind": "monthly",
      "period": {"from": "2026-04-01", "to": "2026-04-30"},
      "trade_count": 23,
      "win_rate": 0.565,
      "pf": 1.84,
      "proposals_created": 3,
      "proposals_merged": 0,
      "completed_at": "2026-04-30T19:42:18+08:00"
    },
    {
      "review_id": "2026-Q1",
      "kind": "quarterly",
      "period": {"from": "2026-01-01", "to": "2026-03-31"},
      "trade_count": 71,
      "win_rate": 0.620,
      "pf": 2.10,
      "proposals_created": 6,
      "proposals_merged": 2,
      "completed_at": "2026-04-01T20:14:00+08:00"
    }
  ]
}
```

由 `post_trade_review_tool` 每次完成復盤後自動 append 一筆。

---

## 6. 自我改進迴圈中的角色

```
Phase 3 LLM Decider(產生決策)
    │
    ▼
Trade Journal(SQLite + FTS5)
    │
    ▼
[本資料夾] reviews/<period>/
    │ 五節點輸出
    ▼
proposals/<id>.md(改動提案)
    │
    ▼ WFA + Robust + 黃金樣本驗證閘
    │
    ▼ 人工 PR review + ConfirmDialog
    │
    ▼
合併回 cheatsheet & strategy code(bump 版本)
    │
    ▼
下一輪 Phase 3 用更新後的規則跑
```

**復盤是迴圈的「記憶體」**:沒有它,系統無法知道過去哪些規則表現好/不好,也無法給 LLM 足夠的歷史 context 來提案改動。因此 `reviews/` 必須:
- **永久保存**(不可刪除單一 review,僅可整檔加上 `archived` 標記)
- **進 git**(允許跨機 sync + 復原)
- **可被 LLM FTS5 全文搜尋**(`session_search_tool` 整合 review 內容)

---

## 7. 與 git 的關係

- `reviews/<period>/` 一律 commit 進 git
- 每個 review 完成後自動產生 commit:`chore: review 2026-04 (3 proposals created)`
- review 內容**不可在事後修改**;若發現錯誤 → 寫新的 review (如 `reviews/2026-04-corrected/` ) + 在原 review 加 `superseded_by` 註記

---

## 8. 容量管理

- 每個月度 review 約 50KB-200KB(視交易筆數)
- 每年 ≈ 12 月度 + 4 季度 + 若干熔斷 / 人工 = ~3MB
- 5 年累積 < 20MB,不需特別 archive
- 若超過 100MB:可將 5 年前的 review 移到 cold storage(S3 / B2),保留 `_index.json` 與 `report.md`,移除原始 `data.json`

---

## 9. 與 proposals 的關聯

review **產生** proposals(寫到 `../proposals/<YYYY-MM-DD>-<topic>.md`)。
proposals **引用** review 的 metrics(JSON pointer 格式)。

```
reviews/2026-04/metrics.json#/by_pattern/VCP
                             ─────────────
                             ↑
                             proposal 的「動機與佐證」段落引用此路徑
```

確保「為何提案」永遠可追溯到具體歷史數據。

---

## 10. 查詢範例(LLM 在下一輪復盤時可用)

```python
# 找最近 6 個月的整體 win_rate 趨勢
reviews.timeseries(metric="overall.win_rate", last_n_months=6)

# 找過去所有「VCP 表現不佳」的批判,看是否反覆出現
reviews.search_critique("VCP 命中率")

# 找過去類似情境的復盤(月度熔斷後的)
reviews.filter(kind="forced")

# 找已合併的提案歷史影響
reviews.proposal_impact(proposal_id="2026-02-28-vcp-criteria-tightening")
```

---

## 11. FAQ

**Q: 復盤頻率太低會錯失改進機會嗎?**
A: v3.0 設定為月度自動 + 任意人工觸發。若覺得需要更頻繁,可手動觸發週度復盤(會多燒 token)。月度熔斷會強制觸發,確保大虧損後立刻檢討。

**Q: 復盤可以跨機共用嗎?**
A: 可以。reviews/ 進 git,任何 clone 都拿到完整歷史。FTS5 索引可由 `_index.json` 重建。

**Q: 如果 LLM 復盤本身有偏誤怎麼辦?**
A: 三層防護:(1) 提案必經 WFA 樣本外驗證(rubric §6);(2) 人工 PR review;(3) 跨復盤一致性檢查(rubric §7)。

---

## 12. `_golden/` 子目錄 — Review prompt 演進的驗閘集（v3 決策 #14）

`reviews/_golden/` 存放 3-5 份**手挑的典型月度復盤** + 對應的 reference answer，作為改動 `prompts/review.md` 時的回歸驗閘。

### 12.1 用途

每次想修 Phase 5 復盤 swarm 的 system prompt 時：
1. 用新版 prompt 重跑 `_golden/` 內每份月度的 swarm 五節點
2. 比對新版產出的 `proposals_created.md` vs reference answer
3. 通過閘（提案重點命中 + 沒有明顯漏判 / 誤判）才能 merge prompt

這是 thread B「自說自話」的解法：Review prompt 改動沒有快速 PnL ground truth，黃金集是退而求其次的客觀閘。

### 12.2 結構

```
reviews/_golden/
├── README.md                              # 黃金集挑選原則 + 各份代表的情境
├── 2026-04-monthly/                       # 「強多頭月」代表
│   ├── (一份完整 review 結構,同 §3)
│   └── reference.md                       # 你當時認可的「合理提案應長這樣」
├── 2026-08-forced-drawdown/               # 「月度熔斷月」代表
│   └── ...
└── 2026-11-quarterly-correction/          # 「回檔月」代表
    └── ...
```

### 12.3 挑選原則

- 涵蓋至少 3 種市場情境（強多頭 / 回檔 / 熔斷）
- 每份要有可區辨的「對 vs 錯」提案（不能太模糊）
- v1 上線後累積 6 個月實戰再回頭挑;**v1 啟動時可空著**（先用人工 review 把關 prompt 改動）

### 12.4 reference answer 的維護

- reference 由你在事後（merge 提案 → 跑 6 個月 → 驗證有效後）回填
- 若一個提案實戰證明是錯的 → 把對應 review 從黃金集移除（避免帶錯閘）
- reference.md 不可被 LLM 自動修改
