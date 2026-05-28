# ssot-pointers — 唯一權威表

改公式或 schema 之前，**先在這張表找到唯一權威檔**，只改那一處。多處出現的會在原檔以 `[[duplicated]]` 標註。

## 業務邏輯 / Schema SSOT

| 主題 | 唯一權威 |
|---|---|
| Volatility Targeting sizing 公式 | `docs/workflow-cheatsheet.md` §6.6 |
| ATR 停損公式 | `docs/workflow-cheatsheet.md` §6.6 |
| Risk-Off 觸發條件 | `docs/workflow-cheatsheet.md` §0 |
| K 線型態庫 | `docs/workflow-cheatsheet.md` §9 |
| Phase 2B Swarm Input Assembler | `docs/design-zh-TW.md` §4.7.0 |
| Trade Journal schema | `docs/llm-decision-schema.md` §4 |
| Trade Journal 衍生欄位 | `docs/llm-decision-schema.md` §4.5 |
| LLM Decider 輸出約束 | `docs/llm-decision-schema.md` §2.1 |
| Phase 5 五節點 DAG 評分 | `docs/post-trade-review-rubric.md` §0–§5 |
| 21 個 Tool 的 I/O schema | `docs/tools-contracts.md` |
| Auto-execute breaker 閾值 | `docs/safety-and-simulation.md` §2.9 |
| Live provider error codes / freshness policy | `openspec/specs/live-providers/spec.md` |
| web-admin 23 頁面視覺契約 | `docs/web-admin-page-designs.md` |

## 規則

1. **不要在程式碼或其他 doc 重抄公式**。需要 reference 時用 `見 docs/workflow-cheatsheet.md §6.6`。
2. 改任何一條前，先 grep 整個 repo 確認沒有複製版本（若有，列出來給 user，討論是否要清理）。
3. 改完要同步任何明確依賴此 schema 的程式（例如 Trade Journal schema 改了，要看 `src/ohmystock/journal/` 是否需動）。
