# Proposals — 策略改動提案

> **版本**:v3.0 ｜ **建立日期**:2026-04-26
> **權威來源**:[`docs/workflow-cheatsheet.md`](../docs/workflow-cheatsheet.md) §16
> **相關章節**:[`docs/post-trade-review-rubric.md`](../docs/post-trade-review-rubric.md) §5 / [`docs/design-zh-TW.md`](../docs/design-zh-TW.md) §4.3.3 / §4.10.5

---

## 1. 此資料夾用途

存放**待 review / 待合併的策略改動提案**。每份提案是一個 Markdown 檔,描述對 [`docs/workflow-cheatsheet.md`](../docs/workflow-cheatsheet.md) 或 `src/ohmystock/strategies/` 的具體改動。

提案來源:
1. **LLM 復盤自動產出**(主要):由 `post_trade_review_team` swarm 的 proposer 節點寫入
2. **人工發現**(次要):任何時候可手動建立提案
3. **外部研究**:從論文 / 報告整理而來

---

## 2. 工作流(對應 cheatsheet §16)

```
proposal 建立(status=pending)
    │
    ▼
自動驗證閘 trigger via /api/proposals/{id}/validate
    │ (status=validating)
    ▼ WFA + Robust + 黃金樣本
    │
    ├── 通過 → status=approved → PENDING_REVIEW/
    │        │
    │        ▼ 人工 review(GitHub PR 或本機檢視)
    │        │
    │        ├── 同意 → /api/proposals/{id}/merge → status=merged
    │        │   合併 cheatsheet & strategy code,bump 版本
    │        │
    │        └── 拒絕 → status=rejected,寫拒絕原因
    │
    └── 失敗 → status=rejected → 寫驗證失敗原因
```

> ⚠️ **安全約束**:`merge` 動作必須由 `/api/proposals/{id}/merge` 端點注入 `confirm_token`(來自人工 ConfirmDialog)。LLM 直接呼叫 `proposal_tool.merge_proposal` 會被拒絕。

### 2.1 v0 狀態轉換層 — 已完成 / 仍 deferred

`proposal-state-machine` change（archive 後 spec：`openspec/specs/proposal-state-machine/spec.md`）落地的範圍：

| 元件 | 狀態 |
|---|---|
| `transition_proposal()` Python API（5 條合法 edge、原子寫、自動搬檔、frontmatter 變更紀錄追加）| ✅ 完成（`src/ohmystock/proposal/state.py`）|
| WFA / Robust / 黃金樣本 驗證引擎 | ⏳ deferred |
| `/api/proposals/{id}/validate`、`/merge`、`/reject` endpoint | ⏳ deferred |
| web-admin `/proposals` 頁面 | ⏳ deferred |
| git commit / PR 自動化、cheatsheet diff 套用、版本 bump | ⏳ deferred |
| `scripts/update_proposal_stats.py`（README §10 表）| ⏳ deferred |
| 回滾流程（`reverted_at` / `reverted_reason`）| ⏳ deferred |

意思是：**狀態機本身可用**（人工或下一輪復盤節點可呼叫 `transition_proposal` 推進狀態 + 搬檔），但驅動它的「自動驗證閘」與「合併流程」仍是手動操作，需後續 change 補齊。

---

## 3. 檔案命名規則

```
proposals/
├── README.md                                       # 本檔
├── 2026-04-30-vcp-volume-threshold.md             # status=pending(剛由 LLM 產出)
├── 2026-04-30-time-stop-extend-vcp.md             # status=validating
├── PENDING_REVIEW/                                 # status=approved 等待人工
│   └── 2026-03-15-confidence-calibration.md
├── merged/                                         # status=merged 歸檔
│   ├── 2026-02-28-vcp-criteria-tightening.md
│   └── 2026-01-31-time-stop-asymmetric.md
└── rejected/                                       # status=rejected 歸檔
    ├── 2026-02-15-llm-confidence-floor-raise.md   # WFA 失敗
    └── 2026-03-05-experimental-mt5-integration.md  # 人工拒絕
```

**檔名格式**:`<YYYY-MM-DD>-<topic>.md`
- `<YYYY-MM-DD>`:建立日期(ISO 格式)
- `<topic>`:小寫 kebab-case,描述改動主題,長度 < 40 字元

---

## 4. 提案模板

複製此模板開新提案:

```markdown
---
proposal_id: 2026-04-30-vcp-volume-threshold
target_section: cheatsheet §6.4 加分項 + §9 K 線型態庫
status: pending
created_by: post_trade_review_team        # 或 <github_username>
created_at: 2026-04-30T19:30:00+08:00
review_id: 2026-04                          # 對應的 review,人工提案則填 null
priority: high | medium | low
---

## 1. 改動描述
(targeting cheatsheet 的具體章節 + 改動內容,1-2 段)

## 2. 動機與佐證
(為何要改?引用 reviews/<period>/metrics.json 的具體指標)

- reviews/2026-04/metrics.json `by_pattern.VCP`:n=8, win_rate=0.375, expectancy=-0.4%
- reviews/2026-04/attribution.json:6 筆 VCP 失敗中 5 筆量能勉強達 1.5×
- 對比 2026-Q1 同條件 win_rate=0.62

## 3. 改動 diff 草稿

\`\`\`diff
--- workflow-cheatsheet.md §6.4 加分項
+++ workflow-cheatsheet.md §6.4 加分項
- 看漲 K 線型態(吞噬 / 晨星 / 紅 K 站上 20MA / VCP / 杯柄突破)
+ 看漲 K 線型態(吞噬 / 晨星 / 紅 K 站上 20MA / VCP【收盤站穩 EMA10 + 量能 ≥ 1.3×】 / 杯柄突破)
\`\`\`

\`\`\`diff
--- src/ohmystock/strategies/_kpattern/vcp.py
+++ src/ohmystock/strategies/_kpattern/vcp.py
- VCP_VOLUME_THRESHOLD = 1.5
+ VCP_VOLUME_THRESHOLD = 1.3
+ VCP_REQUIRES_EMA10_HOLD = True
\`\`\`

## 4. 預期影響範圍
- `src/ohmystock/strategies/_kpattern/vcp.py`(detector)
- `src/ohmystock/strategies/tw_momentum_swing/scoring.py`(加分計算)
- `skills/technical/breakout.md`(描述)
- 預估每月命中候選變化:+12 檔

## 5. 風險評估
- 過於嚴格可能漏掉真正的 VCP 突破 → 歷史 2 檔通過案例都符合新條件,風險可控
- 若 EMA10 過於敏感,可能在震盪市產生雜訊 → 需 WFA 在 2022 熊市段驗證

## 6. 驗證計畫
- WFA 5 年訓練 + 1 年測試,滾動 1 年
- 樣本內外 Sharpe 落差 < 30%
- ±10% 鄰域 Robust 衰減 < 50%
- 黃金樣本 0050 / 2330 / 0056 不退化

## 7. 預期改善幅度
- 整體 win_rate:56.5% → 60% 預估
- 整體 PF:1.84 → 2.0 預估
- 月度交易筆數:23 → 18 (篩選更嚴)

## 8. 變更紀錄
<!-- 自動填入,不要手動編輯 -->
- 2026-04-30T19:30:00+08:00 created by post_trade_review_team
- 2026-05-01T08:15:00+08:00 status: pending → validating
- 2026-05-01T08:42:00+08:00 status: validating → approved (WFA pass)
```

---

## 5. 必填欄位 / 可選欄位

| 欄位 | 必填 | 說明 |
|---|---|---|
| `proposal_id` | ✓ | 對應檔名(不含 `.md`) |
| `target_section` | ✓ | 影響的 cheatsheet 章節 / 程式碼路徑 |
| `status` | ✓ | `pending / validating / approved / rejected / merged` |
| `created_by` | ✓ | `post_trade_review_team` 或 GitHub 帳號 |
| `created_at` | ✓ | ISO-8601 含時區 |
| `review_id` | 條件 | 由復盤產出時必填,人工提案可為 `null` |
| `priority` | 建議 | `high / medium / low`(影響 review 順序) |
| `merged_at` | 自動 | 合併時自動填入 |
| `merged_to_version` | 自動 | 合併後 cheatsheet 版本(例 `v3.1`) |
| `validation_report_path` | 自動 | WFA 驗證報告路徑 |

---

## 6. 驗證閘細節(對應 cheatsheet §16.3)

| 驗證項 | 通過條件 | 失敗時動作 |
|---|---|---|
| **WFA 樣本內外 Sharpe 落差** | < 30% | 標記 `overfitting`,status=rejected |
| **Robust 測試** | ±10% 鄰域 Sharpe 衰減 < 50% | 標記 `unstable`,status=rejected |
| **黃金樣本回歸** | 0050 / 2330 / 0056 不退化 | 標記 `regression`,status=rejected |
| **MDD 變化** | 不能比原版差 > +20% 相對值 | 標記 `risk_increase`,status=rejected |
| **Sample size** | 影響的歷史交易 ≥ 10 筆 | 標記 `insufficient_data`,status=rejected |

驗證報告寫入 `proposals/<id>.validation.json`(自動產生),供人工審視。

---

## 7. 合併流程

### 自動模式(future)
僅當以下全部成立時可考慮:
- 提案優先 `low`
- 影響範圍僅單一參數調整(非邏輯變動)
- 通過所有驗證閘
- 提案 sample size ≥ 30 筆

> 目前(v3.0)**不啟用自動合併**,保留全人工 review。

### 人工模式(預設)
1. 提案進入 `PENDING_REVIEW/`
2. 開發者(或主管)checkout 並檢視:
   - 改動 diff
   - 驗證報告(`*.validation.json`)
   - 對應的 review 報告
3. 同意 → 透過 UI 點 `/api/proposals/{id}/merge` 注入 confirm_token
4. 系統自動:
   - 套用 cheatsheet diff
   - 套用 strategy code diff(若有)
   - bump cheatsheet 版本(例 `v3.0` → `v3.1`)
   - 更新 cheatsheet Changelog
   - 移檔到 `merged/`
   - 寫 git commit + tag
5. 拒絕 → 移檔到 `rejected/`,寫拒絕原因到 frontmatter

---

## 8. 版本管理

- 每次 merge 對應一個 git tag(例 `cheatsheet-v3.1`)
- 提案合併寫入 cheatsheet 開頭 Changelog 表格(見 cheatsheet `v2 → v3 Changelog` 格式)
- 對應 strategy code 檔案頂端必須更新 `# implements cheatsheet §X (v3.1)`

---

## 9. 回滾

若合併後出現問題:
1. `git revert <merge-commit>` 回到上一版
2. 將提案從 `merged/` 移回 `rejected/`,frontmatter 加上 `reverted_at` + `reverted_reason`
3. 重新評估或拋棄

---

## 10. 提案統計(由腳本自動更新)

<!-- 由 scripts/update_proposal_stats.py 維護,不要手動編輯 -->

| 期間 | pending | approved | merged | rejected |
|---|---|---|---|---|
| (尚無資料) | 0 | 0 | 0 | 0 |

---

## 11. FAQ

**Q: LLM 可以直接修改本資料夾嗎?**
A: 可以(透過 `proposal_tool.create_proposal`),但**只能寫 `pending` 狀態**。狀態轉換到 `approved`/`merged` 必經人工 ConfirmDialog 注入 token。

**Q: 提案被 reject 後可以重提嗎?**
A: 可以,但建議先檢視 `rejected/` 中相似提案的失敗原因,避免重蹈覆轍。

**Q: `priority` 怎麼定?**
A: `high` = 進場條件 / 風控規則層級;`medium` = K 線型態 / 加分項;`low` = 排序 / 顯示 / 文案層級。

**Q: LLM prompt 的改動為何不走 proposals/?**
A: v3 決策 #14：Decider 與復盤 swarm 的 system prompt 走獨立通路。
- `prompts/decider.md` 改動 → 回測歷史訊號比 PnL/Sharpe → 通過則 merge prompt（不寫 proposal）
- `prompts/review.md` 改動 → 跑 `reviews/_golden/` 黃金集比對 reference answer → 通過則 merge prompt
- proposals/ 仍管 strategy code / cheatsheet 文字 / 硬規則改動（cheatsheet §16.0 邊界說明）
- 兩通路分工的動機：避免「改判斷層 prompt 也要寫 markdown 提案」的儀式感負擔；prompt diff 本身就是版本紀錄
