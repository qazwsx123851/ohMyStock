# ohMyStock 文件導覽

> 本檔為 docs/ 入口索引；任何 LLM Agent 開新對話應先讀本檔。
> 最後更新：2026-04-26（同 docs reorg）

---

## 1. 文件清單與職責

| 檔案 | 職責 | 大小級別 |
|---|---|---|
| `design-zh-TW.md` | 架構、模組、Tools/Skills/Memory/Backend、目錄結構、路線圖、風險登記 | 大（核心） |
| `workflow-cheatsheet.md` | **交易邏輯權威**：Phase 0–5 + §16 提案閘 + §17 文件關係表 | 大（業務） |
| `safety-and-simulation.md` | Live/Sim 防線 9 層 + verify_simulation + Shioaji SDK 限制 + 對賬機制（從 design §4.5 拆出） | 中 |
| `frontend.md` | React 19 UI 全部設計：路由、Zustand、API client、Tailwind/shadcn、design tokens、a11y、18 頁 wireframes（從 design §4.9 拆出） | 大（前端） |
| `llm-decision-schema.md` | LLM Decider I/O JSON 規格 + Trade Journal schema（FTS5）+ derived 欄位 + schema 演進規範 | 中 |
| `post-trade-review-rubric.md` | Phase 5 五節點 DAG 評分準則（data_loader → attributor → aggregator → critic → proposer） | 中 |
| `tools-contracts.md` | **21 個 `@register_tool` 工具的 I/O schema 唯一權威**（input / output / errors） | 中 |
| `v3-decisions.md` | v3 已拍板決策（12 項）+ 預算追蹤 + 個人 milestone（取代舊 v3-review-summary.md「給主管」框架） | 小 |

---

## 2. 公式 / Schema 唯一權威表

**避免 solo dev 改一處忘另一處的核心約定。** 改公式或 schema 時，**只改下表「唯一權威」一欄**；其他位置都應該是 reference。

| 主題 | 唯一權威 | 不要在這裡改 |
|---|---|---|
| Volatility Targeting sizing 公式 | `workflow-cheatsheet.md` §6.6 | `design-zh-TW.md` §4.6、`safety-and-simulation.md` |
| ATR 停損公式 | `workflow-cheatsheet.md` §6.6 | `design-zh-TW.md` §4.6、§4.5 |
| Trade Journal schema（含 entry/exit/reject/expire） | `llm-decision-schema.md` §4 | `design-zh-TW.md` §4.6.1 |
| Trade Journal 衍生 / join 欄位（derived） | `llm-decision-schema.md` §4.5 | `post-trade-review-rubric.md` §1 不複製欄位定義 |
| LLM Decider 輸出嚴格約束 | `llm-decision-schema.md` §2.1 | `workflow-cheatsheet.md` §6.5（只放 yaml 摘要 + reference） |
| Phase 5 五節點 DAG 評分準則 | `post-trade-review-rubric.md` §0–§5 | `design-zh-TW.md` §4.7.2（只放 YAML preset）、`workflow-cheatsheet.md` §15.2（只放整合說明） |
| Risk-Off 觸發條件清單 | `workflow-cheatsheet.md` §0 | `design-zh-TW.md` §3 架構圖（只能說「有 Risk Gate」） |
| K 線型態庫 | `workflow-cheatsheet.md` §9 | 程式碼註解只能 reference |
| 21 個 Tool 的 I/O schema | `tools-contracts.md` | `design-zh-TW.md` §4.3 只放總表，3 個已詳列的 tool（trade_journal / post_trade_review / proposal）保留在 §4.3.1-§4.3.3 |
| Auto-execute breaker 閾值（confidence 0.7、單日 5 筆、25%、30% deviation 等） | `safety-and-simulation.md` §2.9 | `workflow-cheatsheet.md` §6.7 mode B（只能 reference） |
| Phase 2B → Swarm Input Assembler 規格 | `design-zh-TW.md` §4.7.0 | 任何 swarm preset YAML 不得自行重定義輸入欄位 |

---

## 3. 修文件流程（個人版）

| 改動類型 | 流程 |
|---|---|
| 業務邏輯 / 交易規則 | 走 `workflow-cheatsheet.md` §16 提案流程（即使是自己改也走，保留 audit trail） |
| 架構 / 目錄 / API | 直接編輯 `design-zh-TW.md`，無需提案 |
| Schema 演進 | 編輯 `llm-decision-schema.md`，依 §6 schema 演進規範（v3.0 → v3.1 只加欄位不刪）|
| 前端 design tokens / wireframe | 直接編輯 `frontend.md` |
| Safety 防線新增 / 修改 | 編輯 `safety-and-simulation.md`，並同步 `verify_simulation.py` 的 check |

---

## 4. 給未來 LLM Agent 的快速指引

**任務 → 該讀哪個檔：**

- 「為什麼這樣設計？」/ 看整體架構 → `design-zh-TW.md` §1–§3
- 「該怎麼選股 / 進場 / 出場？」→ `workflow-cheatsheet.md`（**business logic SSOT**）
- 「LLM 該輸出什麼 JSON？」→ `llm-decision-schema.md` §1–§3
- 「Phase 5 復盤節點怎麼評分？」→ `post-trade-review-rubric.md`
- 「live trading 安全防線是什麼？」→ `safety-and-simulation.md`
- 「前端怎麼寫 / 用什麼元件 / 顏色配置？」→ `frontend.md`
- 「Trade Journal SQLite 欄位？」→ `llm-decision-schema.md` §4
- 「Trade Journal 衍生欄位 / 復盤怎麼 join entry-exit？」→ `llm-decision-schema.md` §4.5
- 「`market_data_tool` 怎麼呼叫 / 哪些參數？」→ `tools-contracts.md`
- 「Phase 2B 怎麼組 LLM 輸入？」→ `design-zh-TW.md` §4.7.0
- 「v3 已拍板的決策 / 預算 / milestone？」→ `v3-decisions.md`
- 「台股市場細節（T+2、漲跌停、當沖稅率）」→ `design-zh-TW.md` §4.4.1

**禁止：** 不要在多個檔複製貼上同一份公式 / schema；引用上面 §2 表格的「唯一權威」。

---

## 5. 版本

策略版本（v1 → v2 → v3）保留在 `workflow-cheatsheet.md` preamble 的 changelog 區塊。
本 README 跟著 reorg 一起 bump：v1.0 = 2026-04-26 docs 重整初稿。
