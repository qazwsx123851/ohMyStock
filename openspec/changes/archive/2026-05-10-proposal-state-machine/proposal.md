## Why

`proposal-writer` v0 只能寫入 `status=pending` 的提案，無法推進到 `validating / approved / merged / rejected`，也不會把檔案搬到 `PENDING_REVIEW/` / `merged/` / `rejected/` 子資料夾。`proposals/README.md` §2 / cheatsheet §16 規定的 5 狀態工作流目前**全靠人工改 frontmatter + mv 檔**，下一輪 LLM 復盤產出提案時將立刻撞到這個缺口（無法把 WFA 通過的提案標 approved、無法把人工拒絕的歸檔）。

本 change 補齊**狀態轉換 API 本身** — 一個純 Python 函式 + 檔案搬移 + 變更紀錄追加。**不**做 WFA 驗證引擎、admin endpoint、PR 自動化（皆延後）。

## What Changes

- 新增 `ohmystock.proposal.state` 模組提供 `transition_proposal(path, new_status, *, actor, reason=None, validation_report_path=None, merged_to_version=None) -> Path`
- 強制狀態轉換圖（5 狀態 + 5 條合法邊）：`pending → validating`、`validating → approved`、`validating → rejected`、`approved → merged`、`approved → rejected`；其他轉換（含同狀態、回退、跳躍）一律拋 `ProposalStateError`
- 自動搬檔規則：`approved` → 移到 `PENDING_REVIEW/`；`merged` → 移到 `merged/`；`rejected` → 移到 `rejected/`；`pending` / `validating` 留在 `proposals/` 根目錄
- frontmatter 變更：寫入新 `status`、必要時新增 `merged_at` / `merged_to_version` / `validation_report_path` / `rejected_reason`；其他既有欄位 SHALL 保持 byte-identical
- 「## 8. 變更紀錄」區段每次轉換 SHALL 追加一行 `- <iso-ts> status: <old> → <new> by <actor>[ (<reason>)]`
- 原子性：搬檔 + 改檔內容必須 all-or-nothing — 用 `tempfile` 寫新檔 → `os.replace` → 刪舊檔；中途失敗不可留半成品
- **NOT in scope（明文延後）**：WFA 驗證引擎、`/api/admin/proposals/*` endpoint、web-admin /proposals 頁、git commit/PR 自動化、cheatsheet diff 自動套用、bump 版本、`scripts/update_proposal_stats.py`、回滾 (`reverted_at`) 流程

## Capabilities

### New Capabilities
- `proposal-state-machine`: 提案狀態轉換的 Python API — 5 狀態圖、合法邊驗證、frontmatter 變更紀錄追加、子資料夾搬檔、原子性寫入

### Modified Capabilities
（無；`proposal-writer` v0 行為與檔案格式保持不變 — 新 capability 只讀 writer 寫出的檔再轉換它，不改 writer API）

## Impact

- 新檔：`src/ohmystock/proposal/state.py`、`tests/proposal/test_state.py`
- 新增 export：`src/ohmystock/proposal/__init__.py` 加 `transition_proposal` / `ProposalStateError` / `ProposalStatus`
- 新目錄結構：`proposals/PENDING_REVIEW/`、`proposals/merged/`、`proposals/rejected/`（首次轉換時 lazy `mkdir(parents=True, exist_ok=True)`）
- 不影響 runtime：暫無 caller — Phase 5 的 `post_trade_review_team` proposer 節點目前只 `write_proposal`；本 change 只提供能力，下一輪人工或 admin endpoint 才會真正驅動
- 文件：CLAUDE.md §5 SSOT 表加 `proposal-state-machine` 一列；`proposals/README.md` §2 流程圖中「自動驗證閘」「合併流程」仍標 *deferred*（本 change 只填狀態轉換層）
