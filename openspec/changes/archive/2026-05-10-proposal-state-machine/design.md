## Context

`proposal-writer` v0（archive `phase5-review-mvp`）已落地：`ProposalDraft` frozen pydantic + `write_proposal` 寫 `<YYYY-MM-DD>-<topic>.md` + 強制 `status=pending` + `-2`..`-99` collision suffix + `parse_proposal` round-trip。寫出的檔 frontmatter 含 `proposal_id` / `target_section` / `status` / `created_by` / `created_at` / `review_id` / `priority`，內文有 8 個 `## N.` 段落，「## 8. 變更紀錄」初始為 `- <ts> created by <actor>` 一行。

`proposals/README.md` §2 / cheatsheet §16 規定 5 狀態工作流：

```
pending → validating → approved → merged
              │            │
              └── rejected ┘
```

`approved` 提案 SHALL 移到 `proposals/PENDING_REVIEW/`、`merged` 到 `proposals/merged/`、`rejected` 到 `proposals/rejected/`。

目前無 caller 驅動轉換 — Phase 5 的 `post_trade_review_team` proposer 節點只呼叫 `write_proposal`。下一輪 LLM 復盤要把 WFA 通過的提案標 `approved` 時將立刻撞到此缺口。

**Constraints**
- Solo dev 個人專案，避免 admin endpoint / web UI / 定時任務（皆 deferred）
- writer v0 的「永不覆寫已存在檔」契約只約束 *create*；state machine 是 *update*，可以也必須改檔內容（含 frontmatter）— 但仍保留「新檔 → `os.replace` → 刪舊檔」的原子性
- frontmatter 之外的內文 8 段落 SHALL byte-identical（除「## 8. 變更紀錄」追加新行之外）

## Goals / Non-Goals

**Goals:**
- 純 Python API：`transition_proposal(path, new_status, *, actor, reason=None, validation_report_path=None, merged_to_version=None) -> Path`，可在 CLI / future endpoint / 測試中直接呼叫
- 強制合法邊：5 條合法轉換之外（含同狀態、回退、跳躍、未知狀態字串）一律拋 `ProposalStateError`
- 子資料夾自動搬檔：`approved` / `merged` / `rejected` 各自的 sink 目錄；`pending` / `validating` 留在 `proposals/` 根
- frontmatter mutation：寫新 `status` 與 transition 相關 metadata（`merged_at` / `merged_to_version` / `validation_report_path` / `rejected_reason`），其他鍵保留原值與順序
- 「## 8. 變更紀錄」append-only：每次 transition 加一行 `- <iso-ts> status: <old> → <new> by <actor>[ (<reason>)]`
- 原子性：用 `tempfile.NamedTemporaryFile(dir=target_parent, delete=False)` 寫新檔 → `os.replace(tmp, new_path)` → 刪舊路徑；exception 時清理 tmp
- 與 `parse_proposal` round-trip：transition 後再 `parse_proposal` 仍能還原 `ProposalDraft`（除新增 metadata 鍵）

**Non-Goals:**
- WFA 驗證引擎本體（`scripts/validate_proposal.py` 等）
- `/api/admin/proposals/*` REST endpoint
- web-admin `/proposals` 頁面
- git commit / PR 自動化、cheatsheet diff 套用、版本 bump
- `scripts/update_proposal_stats.py` 與 README §10 表格自動更新
- 回滾流程（`reverted_at` / `reverted_reason` frontmatter）
- 多檔批次轉換、查詢 API（`list_proposals_by_status` 等）— 留給呼叫端用 `glob` 解決
- 鎖 / concurrency — solo dev 本機跑，無多 writer 競爭

## Decisions

### 純函式 API、非 class
**選**：`transition_proposal(path, new_status, *, actor, reason=None, ...)` 一個函式
**捨**：`ProposalStateMachine(proposals_dir)` class、`Proposal.transition_to(status)` method

理由：v0 `write_proposal` / `parse_proposal` 已是純函式風格；class 對 solo dev 個人專案是負擔（建構 / 注入 / mock 全多餘）。Path-based 也讓呼叫端不用先 `parse_proposal` 再 transition。

### 合法邊用 frozenset 表
**選**：`_LEGAL_TRANSITIONS: frozenset[tuple[ProposalStatus, ProposalStatus]]` 5 條 edge
**捨**：`Enum` + 每個 status 自帶 `next_states` method、`networkx.DiGraph`

理由：5 條邊不需要 graph lib；frozenset 讀寫一目了然，import-time 構建零成本。

### `ProposalStatus = Literal["pending", "validating", "approved", "merged", "rejected"]`
**選**：`Literal` type alias
**捨**：`StrEnum`（Python 3.11+）

理由：與 v0 `priority: Literal[...]` 一致；不需要 `.value` / iteration；pydantic 對 `Literal` 原生支援。

### 子資料夾配對寫死
**選**：`_SINK_DIR: dict[ProposalStatus, str | None] = {"approved": "PENDING_REVIEW", "merged": "merged", "rejected": "rejected", "pending": None, "validating": None}`
**捨**：可設定的 mapping、env var、call-time override

理由：`proposals/README.md` §3 是唯一 source of truth — 改 sink dir 名稱意味著 README 也要改；不需要可設定性。`None` = 留在 root。

### 原子性：tmpfile + `os.replace` + delete old
**選**：
1. 計算 `new_path`（含 sink dir + 檔名 + collision check）
2. `tempfile.NamedTemporaryFile(dir=new_path.parent, delete=False, suffix=".md.tmp")` 寫新內容
3. `os.replace(tmp_path, new_path)`（POSIX/Windows 皆原子）
4. 若 `old_path != new_path`：`old_path.unlink()`
5. 若任何步驟拋 exception：`tmp_path` 若存在則 unlink

**捨**：先 copy 後 delete、`shutil.move`、SQLite 持久化

理由：`os.replace` 在 Windows / POSIX 都是 atomic rename（同 filesystem）。step 4 的 unlink 不在原子窗口內，但只會留下「兩份相同內容的檔」而非「資料遺失或半成品」— 接受這個瑕疵；solo dev 撞到時手動清理。

### 檔名衝突處理：直接拒絕（不 auto-suffix）
**選**：transition 時若 `new_path` 已存在 → 拋 `ProposalStateError("destination_exists")`
**捨**：套用 v0 writer 的 `-2`..`-99` collision suffix

理由：v0 collision 是因為「同日同 topic 的不同 draft」自然會撞；transition 不會 — 同一 `proposal_id` 不可能在兩個 sink dir 都有檔。若真的撞，多半是手工錯誤或上次 transition 留下殘骸，要立刻 fail-loud 而非靜默改名。

### frontmatter 寫回：保留鍵順序
**選**：讀進 dict（`yaml.safe_load`）、改值、`yaml.safe_dump(sort_keys=False, allow_unicode=True)` 寫回
**捨**：完全重寫 frontmatter、引入 `python-frontmatter` 新依賴

理由：保 byte-stable diff（除 status / 新加的 metadata 鍵）讓人工 review 容易。新加的 metadata 鍵 SHALL append 到 frontmatter 結尾。`pyyaml` 已在依賴內。

### 「## 8. 變更紀錄」append：用簡單文字搜尋
**選**：找 `## 8. 變更紀錄` 那行，把新 line 插到該段落末尾（檔尾，因為是末段）
**捨**：完整 markdown AST parse

理由：v0 writer 寫的格式固定，簡單 line search 足夠；若找不到 `## 8. 變更紀錄` heading → 拋 `ProposalStateError("malformed_changelog")`。

### Reason 欄位用法
**選**：`reason: str | None`
- 寫入 changelog: `- <ts> status: pending → validating by <actor> (kicked off WFA)`
- 寫入 frontmatter `rejected_reason`（僅當 `new_status == "rejected"` 且 `reason` 非空）
- 不寫入 `merged_to_version`（那是另一參數）

**捨**：每種 transition 一個專屬 reason 欄位

理由：reason 是給人看的 free text；機器讀的（`merged_to_version` / `validation_report_path`）是 typed 參數。

### Validator: required-args-by-target-status
**選**：在 `transition_proposal` 內顯式 check
- `new_status == "merged"` → 必須傳 `merged_to_version`，否則拋 `ProposalStateError("missing_merged_to_version")`
- `new_status == "approved"` → 必須傳 `validation_report_path`，否則拋 `ProposalStateError("missing_validation_report")`
- `new_status == "rejected"` → 必須傳 `reason`，否則拋 `ProposalStateError("missing_rejection_reason")`
- 其他 transition → reason / 兩個 path 皆 optional

**捨**：所有欄位皆 optional、靠 caller 自律

理由：這三個 metadata 是 audit trail 的關鍵，缺了等於丟資訊。fail-loud。

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| `os.replace` + 後續 `unlink` 之間 process crash → 兩份相同內容檔遺留 | 接受；solo dev 撞到手動 `rm`。Test: simulate crash 驗證 `os.replace` 已成功（資料無遺失） |
| frontmatter 鍵順序漂移（不同 yaml lib 版本） | 凍結 `pyyaml` minor 版本（已在 `pyproject.toml`）；test 寫死 expected key 順序 |
| Markdown 內文末尾無 trailing newline 導致 changelog 追加格式怪 | writer v0 確保 trailing newline；state machine 在追加前再 normalize 一次（`text.rstrip("\n") + "\n- <line>\n"`） |
| `proposals/<sink>/` 不存在時 `os.replace` 失敗 | 在計算 `new_path` 後立即 `new_path.parent.mkdir(parents=True, exist_ok=True)` |
| Caller 手工把 `pending` 提案塞進 `merged/` 子資料夾 → state machine 讀 path 推不出 sink dir | 不依賴目錄推 status — status 一律由 frontmatter 讀；目錄只是 *寫入* 規則 |
| 同步並發兩個 caller 同時 transition 同一檔 → race | solo dev 不會發生；不加 lock |

## Migration Plan

無需 migration — 現有 `proposals/` 內 0 個檔（pre-implementation）。第一次跑時 sink dir 由 `mkdir(parents=True, exist_ok=True)` 建立。

`proposal-writer` v0 寫出的檔 frontmatter 已含本 change 需要的所有鍵（`status` / `created_at` / `proposal_id` 等），不需 backfill。

## Open Questions

無 — 所有設計決策已在 §Decisions 列定。實作時若撞到未列情境（如「`approved` 之後想退回 `validating`」），fail-loud 拋 `ProposalStateError("illegal_transition")`，由 caller 自行決定加新邊或手動修正。
