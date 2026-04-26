# ohMyStock v3.0 — 已拍板決策與預算追蹤

> **個人專案決策紀錄**（取代原 `v3-review-summary.md`「給主管 review 摘要」）。
> 用途：保留 v3 設計演進過程的關鍵決策與依據，避免日後忘了「為什麼選 X 不選 Y」。
> 建立日期：2026-04-26

---

## 1. v3 一頁摘要

### 1.1 為什麼從 v2 升 v3

v2 流程是「自動掃描 → 自動評分 → 人工 Phase 3 進場 → 出場後寫 trade journal」，**沒有閉環**。v3 改成：

```
訊號偵測 → LLM 進場決策 + 倉位計算 → 結構化記錄
       → LLM 復盤 → LLM 出策略改動提案 → 人工 review + WFA 驗證
       → 合併回 cheatsheet → 下一輪
```

讓系統能**自我改進**，不必人工每月手動研究新規則。

### 1.2 v3 做了什麼

| 變更 | 對應章節 |
|---|---|
| Phase 3 由人工拍板升級為 **LLM Decider 自動分析 + Confirm Gate**（可切自動執行） | cheatsheet §6 / design §4.7.1 |
| Trade Journal 由純數值欄位升級為 **LLM 結構化思考鏈 + FTS5 索引** | cheatsheet §6.8 / llm-decision-schema §4 |
| 月底「統計報告」升級為 **LLM 復盤五節點 swarm** + 策略改動提案產出 | cheatsheet §15 / post-trade-review-rubric |
| **新增** 提案 → WFA 驗證 → 人工 PR review → 合併工作流 | cheatsheet §16 / design §4.10 |
| **新增** safety §2.9 防線 9「LLM 自動下單熔斷」（`OHMYSTOCK_AUTO_EXECUTE=true` 時生效） | safety-and-simulation §2.9 |

### 1.3 v2 → v3 影響

| 項目 | v2 | v3 |
|---|---|---|
| 開發週期 | 13 週 | **16 週**（+ Phase 3.5 = 3 週） |
| LLM API 月成本 | 不適用 | **USD ~$31-36 / NT$ ~960-1,120**（預期） |
| 文件數量 | 2 份 | **8 份**（design / cheatsheet / llm-decision-schema / rubric / safety / frontend / tools-contracts / README） |
| 安全防線 | 8 條 | **9 條**（+LLM 自動下單熔斷） |

### 1.4 主要風險與緩解

| 風險 | 緩解 |
|---|---|
| LLM 幻覺造成下單失誤 | Confirm Gate 預設人工；自動模式經 5 項熔斷；Live 模式強制 disabled |
| LLM 自動寫 cheatsheet 漂移 | 改 cheatsheet 一律走 proposal → WFA → 人工 PR；LLM 不可直接 commit |
| 復盤 LLM 過擬合歷史交易 | 提案必經 WFA 樣本外驗證；Robust 衰減 > 50% 拒絕；黃金樣本回歸 |
| Claude API 成本爆量 | Opus 僅用最關鍵節點；啟用 prompt cache + batch API；月度復盤頻率 |

---

## 2. v1 即需的基礎決策（已拍板）

| # | 議題 | 決策 | 依據 |
|---|---|---|---|
| 1 | FinMind 贊助會員預算 NT$ 2,000/年 | ✅ **核可** | 籌碼面 skill 必需；台股無替代 |
| 2 | Shioaji 模擬倉帳號 | ✅ **個人帳號** | 個人專案，無代理開戶問題 |
| 3 | Web UI 對外 / 對內 | ✅ **對內 localhost** | 避開 SITC 投顧執照風險；個人使用無 PDPA 顧慮 |
| 4 | Live trading 時程 | 🔵 **延後評估** | MVP 後若試模擬倉穩定 6+ 個月再考慮 |
| 5 | Audit log 儲存 | ✅ **本地 90 天 hot + 自行歸檔** | 個人無金管會稽核需求 |
| 6 | 多人使用 | ✅ **單一使用者** | 個人專案 |

## 3. v3 新增決策（已內部拍板，2026-04-26）

| # | 議題 | 決策 | 預期影響 |
|---|---|---|---|
| 7 | **Anthropic Claude API 月預算** | **USD $50/月 上限**（NT$ 1,500），預期實支 NT$ 960-1,120 | 啟用 prompt cache + batch API 可降至 NT$ 620-775 |
| 8 | **LLM 模型配置** | Opus 4.7（關鍵決策）+ Sonnet 4.6（分析）+ Haiku 4.5（規則檢查） | 混合分層，品質與成本平衡 |
| 9 | **`OHMYSTOCK_AUTO_EXECUTE` v1 範圍** | v1 同時做 true/false 兩模式 | Phase 3.5 工期 2→3 週 |
| 10 | **`proposals/` 與 `reviews/` 進 git** | 進 git | 預估 +3MB/年，跨機 sync 必要 |
| 11 | **Confirm Gate timeout** | 30 分鐘 expire | 配合盤中 11:00/13:00 訊號節奏 |
| 12 | **復盤頻率** | 月度自動 + 任意手動 | 不採週度（代價過高） |

---

## 4. 預算與成本追蹤

> 詳細估算原稿 `composed-wobbling-torvalds.md`「LLM API 成本預估」章節。

### 4.1 月度 LLM 成本拆解

| 項目 | 月成本 (USD) | 月成本 (NT$) |
|---|---|---|
| Phase 3 LLM Decider（中等情境 65 次/月） | $22 | NT$ 695 |
| Phase 5 復盤（月度 + 季度均攤） | $4 | NT$ 125 |
| 偶發 swarm（投資委員會等 ad-hoc） | $5-10 | NT$ 155-310 |
| **合計** | **$31-36** | **NT$ 960-1,120** |
| **年化** | **$372-432** | **NT$ 11,500-13,400** |

### 4.2 替代配置參考

| 配置 | 月成本 | 評估 |
|---|---|---|
| 全 Sonnet 簡化 | NT$ 310 | 省 70%，但決策深度下降 |
| **混合分層（採用）** | **NT$ 960-1,120** | Opus 僅用最關鍵節點 |
| 全 Opus 高階 | NT$ 3,720-4,650 | 4× 成本，品質提升邊際遞減 |

### 4.3 成本爆量警示

- 強多頭市場候選爆量（150+/月）→ 飆至 NT$ 1,800+
- 改週度復盤 → 飆至 NT$ 2,000+（**不採用**）
- **軟性熔斷**：月成本超 USD $50 自動降階為全 Sonnet（待實作）

---

## 5. 個人 Milestone（取代 Roadmap）

> v3 由 13 週擴充至 **16 週**；若 2026-04-28 開工，預計 **2026-08 中** 完成 MVP

| 階段 | 週數 | 累積週 | 預計完成 | 自我驗收 |
|---|---|---|---|---|
| Phase 0: Scaffold | 1 | 1 | 2026-05-05 | `ohmystock --help` 可執行；FastAPI 啟動 |
| Phase 1: 核心 Agent + 基礎 skills | 2 | 3 | 2026-05-19 | 跑得通 1 個 swarm preset（投資委員會） |
| Phase 2: 回測引擎 + 模擬下單 | 3 | 6 | 2026-06-09 | 跑通歷史回測 + Shioaji simulation 下 1 張 |
| Phase 3: 完整 skill 庫 + Swarm | 3 | 9 | 2026-06-30 | 21 個 tool 全部實作；12 個 swarm preset 至少 4 個可跑 |
| **Phase 3.5: 閉環 LLM 決策 + 復盤（v3）** | **3** | **12** | **2026-07-21** | **完整跑通閉環迴圈一輪**（含 LLM 成本實際 vs 預估） |
| Phase 4: Web UI + 記憶 | 2 | 14 | 2026-08-04 | 18 個 wireframe 全部實作 |
| Phase 5: 強化 / 文件 / 部署 | 2 | 16 | **2026-08-18** | Docker compose up 一鍵啟動；自我跑 1 週模擬 |

### 5.1 月底自我檢視

- Anthropic API 帳單實際 vs 預估對照
- 是否還在 NT$ 1,500/月預算內
- 模擬倉 PnL（雖不重要，但驗證系統有跑）

---

## 6. 已知尚未完全解決的議題（個人 backlog）

| 項目 | 狀態 | 備註 |
|---|---|---|
| Live trading 流程上線 | 🔵 延後 | safety §1-§5 已寫完，v1 不啟用 |
| **MOPS 反爬風險** | 🟡 監控 | 若反爬則改人工檔案匯入 |
| **FinMind 服務中斷** | ✅ 已準備 fallback | 鏈：FinMind → TWSE OpenAPI → twstock → Parquet 快取 |
| **個人 API 帳號歸屬** | ✅ 已確認 | Anthropic API 用個人帳號 + 個人信用卡 |
| **跨機 sync** | 🟡 待選擇 | git + 手動加密 `.env.live` 或 syncthing |
| **資料備份** | 🟡 待設計 | `~/.ohmystock/` 整個目錄定期備份到外接 SSD？ |

---

## 7. 變更紀錄

| 日期 | 異動 |
|---|---|
| 2026-04-26 | v3 初版內部拍板；本檔建立（取代 v3-review-summary.md「給主管」框架） |
