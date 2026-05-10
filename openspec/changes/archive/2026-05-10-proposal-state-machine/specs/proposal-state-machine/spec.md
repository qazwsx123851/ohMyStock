## ADDED Requirements

### Requirement: 提供 ProposalStatus 與 ProposalStateError

系統 SHALL 在 `ohmystock.proposal.state` 提供 `ProposalStatus = Literal["pending", "validating", "approved", "merged", "rejected"]` type alias，以及 `ProposalStateError(RuntimeError)` 例外類別。所有合法狀態 SHALL 列舉於此 5 值集合中；任何其他字串（含大小寫變體、空字串、`None`）作為 `new_status` 傳入 `transition_proposal` 時 SHALL 拋 `ProposalStateError` 並以 `"unknown_status"` 作為 first-line message 子字串。

#### Scenario: ProposalStatus 含 5 值
- **WHEN** import `from ohmystock.proposal.state import ProposalStatus` 並透過 `typing.get_args(ProposalStatus)` 取得 tuple
- **THEN** SHALL 等於 `("pending", "validating", "approved", "merged", "rejected")`，順序與內容皆相符

#### Scenario: 未知 status 拋 ProposalStateError
- **WHEN** 呼叫 `transition_proposal(path=valid_pending_md, new_status="approve", actor="mark")`（拼錯 — 缺 `d`）
- **THEN** SHALL 拋 `ProposalStateError`，其 message SHALL 包含 `"unknown_status"`

#### Scenario: 大小寫變體拒絕
- **WHEN** 呼叫 `transition_proposal(path=valid_pending_md, new_status="Pending", actor="mark")`
- **THEN** SHALL 拋 `ProposalStateError`，其 message SHALL 包含 `"unknown_status"`

---

### Requirement: 強制 5 條合法 transition edge

系統 SHALL 僅允許以下 5 條 status transition：`pending → validating`、`validating → approved`、`validating → rejected`、`approved → merged`、`approved → rejected`。任何其他 (current, new) 組合（包含同狀態、回退、跳躍、merged/rejected 為起點的轉換）SHALL 拋 `ProposalStateError` 並以 `"illegal_transition"` 作為 message 子字串。`current_status` SHALL 由目標檔的 frontmatter `status` 鍵讀取，**不**依賴檔案所在目錄推斷。

#### Scenario: pending → validating 通過
- **WHEN** 呼叫 `transition_proposal(path=pending_md, new_status="validating", actor="mark")`
- **THEN** SHALL 成功回傳新檔路徑；不拋任何 exception

#### Scenario: pending → approved 拒絕（跳躍）
- **WHEN** 呼叫 `transition_proposal(path=pending_md, new_status="approved", actor="mark", validation_report_path=Path("v.json"))`
- **THEN** SHALL 拋 `ProposalStateError`，message 含 `"illegal_transition"`

#### Scenario: 同狀態拒絕
- **WHEN** 呼叫 `transition_proposal(path=validating_md, new_status="validating", actor="mark")`
- **THEN** SHALL 拋 `ProposalStateError`，message 含 `"illegal_transition"`

#### Scenario: merged 為起點拒絕（terminal）
- **WHEN** 對 frontmatter `status=merged` 的檔呼叫 `transition_proposal(path=merged_md, new_status="rejected", actor="mark", reason="found bug")`
- **THEN** SHALL 拋 `ProposalStateError`，message 含 `"illegal_transition"`

#### Scenario: rejected 為起點拒絕（terminal）
- **WHEN** 對 frontmatter `status=rejected` 的檔呼叫 `transition_proposal(path=rejected_md, new_status="validating", actor="mark")`
- **THEN** SHALL 拋 `ProposalStateError`，message 含 `"illegal_transition"`

#### Scenario: validating → rejected 通過
- **WHEN** 呼叫 `transition_proposal(path=validating_md, new_status="rejected", actor="mark", reason="WFA fail")`
- **THEN** SHALL 成功回傳新檔路徑

#### Scenario: approved → merged 通過
- **WHEN** 呼叫 `transition_proposal(path=approved_md, new_status="merged", actor="mark", merged_to_version="v3.1")`
- **THEN** SHALL 成功回傳新檔路徑

---

### Requirement: required-args 由 new_status 決定

系統 SHALL 依 `new_status` 對 keyword args 套用以下檢查：
- `new_status == "approved"` → 必須傳非 `None` 的 `validation_report_path: Path`，否則拋 `ProposalStateError("missing_validation_report")`
- `new_status == "merged"` → 必須傳非 `None` 的 `merged_to_version: str`，否則拋 `ProposalStateError("missing_merged_to_version")`
- `new_status == "rejected"` → 必須傳非空字串 `reason: str`，否則拋 `ProposalStateError("missing_rejection_reason")`
- `new_status` 為其他合法值（`validating`）→ 三個欄位皆 optional

`actor` 參數 SHALL 為非空字串；空字串或 `None` SHALL 拋 `ProposalStateError("missing_actor")`。required-args 檢查 SHALL **晚於** illegal_transition 檢查 — 即先確認 transition 合法，再檢查 args。

#### Scenario: approved 缺 validation_report_path
- **WHEN** 呼叫 `transition_proposal(path=validating_md, new_status="approved", actor="mark")`（無 validation_report_path）
- **THEN** SHALL 拋 `ProposalStateError`，message 含 `"missing_validation_report"`

#### Scenario: merged 缺 merged_to_version
- **WHEN** 呼叫 `transition_proposal(path=approved_md, new_status="merged", actor="mark")`
- **THEN** SHALL 拋 `ProposalStateError`，message 含 `"missing_merged_to_version"`

#### Scenario: rejected 缺 reason
- **WHEN** 呼叫 `transition_proposal(path=validating_md, new_status="rejected", actor="mark")`
- **THEN** SHALL 拋 `ProposalStateError`，message 含 `"missing_rejection_reason"`

#### Scenario: rejected reason 為空字串拒絕
- **WHEN** 呼叫 `transition_proposal(path=validating_md, new_status="rejected", actor="mark", reason="")`
- **THEN** SHALL 拋 `ProposalStateError`，message 含 `"missing_rejection_reason"`

#### Scenario: actor 為空字串拒絕
- **WHEN** 呼叫 `transition_proposal(path=pending_md, new_status="validating", actor="")`
- **THEN** SHALL 拋 `ProposalStateError`，message 含 `"missing_actor"`

#### Scenario: validating 不需 path/version/reason
- **WHEN** 呼叫 `transition_proposal(path=pending_md, new_status="validating", actor="mark")`
- **THEN** SHALL 成功回傳新檔路徑；不拋任何 exception

---

### Requirement: 自動搬到 status 對應的子資料夾

系統 SHALL 依 `new_status` 把檔搬到 `proposals_root` 下對應子資料夾：`approved` → `PENDING_REVIEW/`、`merged` → `merged/`、`rejected` → `rejected/`、`pending` / `validating` → `proposals_root` 根目錄（若已在根則不動）。`proposals_root` SHALL 由輸入 `path` 的 parent 反推（若 parent 名稱為 `PENDING_REVIEW` / `merged` / `rejected` 之一則 `proposals_root = path.parent.parent`，否則 `proposals_root = path.parent`）。子資料夾不存在時 SHALL `mkdir(parents=True, exist_ok=True)`。

回傳 `Path` SHALL 為搬移後的最終路徑（含子資料夾），而非原 path。

#### Scenario: validating → approved 搬到 PENDING_REVIEW
- **WHEN** 呼叫 `transition_proposal(path=proposals_dir/"2026-04-30-x.md", new_status="approved", actor="mark", validation_report_path=Path("v.json"))`
- **THEN** SHALL 回傳 `proposals_dir/"PENDING_REVIEW"/"2026-04-30-x.md"`；原 `proposals_dir/"2026-04-30-x.md"` SHALL 不再存在；新路徑 SHALL 存在

#### Scenario: approved → merged 搬到 merged/
- **WHEN** 對 `proposals_dir/"PENDING_REVIEW"/"2026-04-30-x.md"`（status=approved）呼叫 `transition_proposal(..., new_status="merged", actor="mark", merged_to_version="v3.1")`
- **THEN** SHALL 回傳 `proposals_dir/"merged"/"2026-04-30-x.md"`；原 `PENDING_REVIEW/2026-04-30-x.md` SHALL 不再存在

#### Scenario: pending → validating 留在根目錄
- **WHEN** 對 `proposals_dir/"2026-04-30-x.md"` 呼叫 `transition_proposal(..., new_status="validating", actor="mark")`
- **THEN** SHALL 回傳 `proposals_dir/"2026-04-30-x.md"`（同 path），原檔被覆寫過但檔名不變

#### Scenario: 子資料夾首次使用自動建立
- **WHEN** `proposals_dir/"merged"` 不存在，呼叫 `transition_proposal(approved_md, new_status="merged", actor="mark", merged_to_version="v3.1")`
- **THEN** SHALL 自動建立 `proposals_dir/"merged"` 目錄並把檔搬過去

#### Scenario: 目的檔已存在拒絕
- **WHEN** `proposals_dir/"PENDING_REVIEW"/"2026-04-30-x.md"` 已存在（殘骸），對 `proposals_dir/"2026-04-30-x.md"` 呼叫 `transition_proposal(..., new_status="approved", ..., validation_report_path=Path("v.json"))`
- **THEN** SHALL 拋 `ProposalStateError`，message 含 `"destination_exists"`；兩個檔皆 SHALL 保持原狀

---

### Requirement: frontmatter status 與 metadata 寫入

寫出檔的 frontmatter SHALL：
1. `status` 鍵值更新為 `new_status`
2. `new_status == "approved"` 時 SHALL 寫入 `validation_report_path: <字串路徑>`（用 `str(Path)`）
3. `new_status == "merged"` 時 SHALL 寫入 `merged_to_version: <傳入字串>` 與 `merged_at: <ISO-8601 含時區的當下時間>`
4. `new_status == "rejected"` 且 `reason` 非空 時 SHALL 寫入 `rejected_reason: <reason 字串>`
5. 既有所有其他鍵 SHALL 保持原值與順序；新加的鍵 SHALL append 到 frontmatter 末尾

frontmatter 之外的內文 8 個 `## N.` 段落 SHALL 保持 byte-identical（除「## 8. 變更紀錄」依下一條 requirement 追加）。

#### Scenario: approved 寫 validation_report_path
- **WHEN** `transition_proposal(validating_md, new_status="approved", actor="mark", validation_report_path=Path("proposals/2026-04-30-x.validation.json"))` 完成
- **THEN** 寫出檔 frontmatter SHALL 含 `status: approved` 與 `validation_report_path: proposals/2026-04-30-x.validation.json`

#### Scenario: merged 寫 merged_to_version + merged_at
- **WHEN** `transition_proposal(approved_md, new_status="merged", actor="mark", merged_to_version="v3.1")` 完成
- **THEN** 寫出檔 frontmatter SHALL 含 `status: merged`、`merged_to_version: v3.1`，以及 `merged_at` 鍵值為 ISO-8601 含時區字串（例 `2026-05-10T15:30:00+08:00`）

#### Scenario: rejected 寫 rejected_reason
- **WHEN** `transition_proposal(validating_md, new_status="rejected", actor="mark", reason="WFA Sharpe drop > 30%")` 完成
- **THEN** 寫出檔 frontmatter SHALL 含 `status: rejected` 與 `rejected_reason: "WFA Sharpe drop > 30%"`

#### Scenario: 既有鍵順序保留
- **WHEN** 原檔 frontmatter 鍵順序為 `proposal_id / target_section / status / created_by / created_at / review_id / priority`，呼叫 `transition_proposal(..., new_status="validating", actor="mark")`
- **THEN** 寫出檔 frontmatter 前 7 鍵 SHALL 與原順序相同（僅 `status` 值改變）

#### Scenario: 內文 8 段落 byte-identical（除變更紀錄）
- **WHEN** 對 valid `pending` 檔呼叫 `transition_proposal(..., new_status="validating", actor="mark")`
- **THEN** 寫出檔的「## 1. 改動描述」到「## 7. 預期改善幅度」共 7 段內文 SHALL 與原檔對應段落 byte-identical

---

### Requirement: 變更紀錄追加格式

系統 SHALL 在「## 8. 變更紀錄」段落末尾追加一行，格式為 `- <iso-ts> status: <old_status> → <new_status> by <actor>`，其中 `<iso-ts>` 為 transition 當下的 ISO-8601 時間字串（含時區，使用本機時區或 UTC 任一，但同一函式內 SHALL 一致）。若 `reason` 非 `None` 且非空，SHALL 在行尾加 ` (<reason>)`。原有的「變更紀錄」內容（如 `created by ...` 行）SHALL 保留。若檔案缺少 `## 8. 變更紀錄` heading，SHALL 拋 `ProposalStateError`，message 含 `"malformed_changelog"`。

#### Scenario: 追加格式正確
- **WHEN** 對 frontmatter status=pending 的檔（變更紀錄段含 `- 2026-04-30T19:30:00+08:00 created by post_trade_review_team`）呼叫 `transition_proposal(..., new_status="validating", actor="mark")`
- **THEN** 寫出檔 SHALL 含原 created 行，並在其後新增一行符合 regex `^- \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2} status: pending → validating by mark$`

#### Scenario: 含 reason 的追加行
- **WHEN** 呼叫 `transition_proposal(validating_md, new_status="rejected", actor="mark", reason="WFA fail")`
- **THEN** 寫出檔 SHALL 在變更紀錄段尾新增一行 `- <iso-ts> status: validating → rejected by mark (WFA fail)`

#### Scenario: 缺變更紀錄段拋錯
- **WHEN** 對「無 ## 8. 變更紀錄 heading」的 markdown 檔呼叫 `transition_proposal(..., new_status="validating", actor="mark")`
- **THEN** SHALL 拋 `ProposalStateError`，message 含 `"malformed_changelog"`；目標檔 SHALL **不**被修改

---

### Requirement: 寫入原子性

寫入 SHALL 原子：先以 `tempfile.NamedTemporaryFile(dir=new_path.parent, delete=False, suffix=".md.tmp")` 寫新內容、`flush` + `os.fsync`、close，再 `os.replace(tmp_path, new_path)`。若 `old_path != new_path`，再 `old_path.unlink()`。任何步驟拋 exception 時，若 `tmp_path` 存在 SHALL `unlink` 並 re-raise，**不**靜默吞錯。`os.replace` 失敗（含 cross-device、permission）SHALL re-raise 原 OSError，不包成 `ProposalStateError`。

#### Scenario: 成功 transition 不留 .tmp 檔
- **WHEN** 呼叫 `transition_proposal(...)` 成功完成
- **THEN** `new_path.parent` 中 SHALL 不存在 `.md.tmp` 結尾的殘檔

#### Scenario: 寫入過程模擬失敗清理 tmp
- **WHEN** 在 `os.replace` 之前 monkeypatch 強制 `tempfile` 寫入後拋 `IOError`
- **THEN** SHALL re-raise 原 `IOError`；`new_path.parent` 中 SHALL 不存在 `.md.tmp` 殘檔；原檔內容 SHALL 不被修改

---

### Requirement: parse_proposal round-trip 相容

`transition_proposal` 寫出的檔 SHALL 仍可被既有 `ohmystock.proposal.writer.parse_proposal` 成功解析回 `ProposalDraft`（不拋 `ProposalParseError`）。`ProposalDraft` 不含的新增 frontmatter 鍵（`merged_at` / `merged_to_version` / `validation_report_path` / `rejected_reason`）SHALL 被 `parse_proposal` 忽略而非拋錯。

#### Scenario: pending → validating 後 parse_proposal 成功
- **WHEN** `transition_proposal(pending_md, new_status="validating", actor="mark")` 完成後對新路徑呼叫 `parse_proposal(new_path)`
- **THEN** SHALL 回傳 `ProposalDraft` 實例，不拋任何 exception

#### Scenario: merged 後 parse_proposal 忽略 merged_at 等新鍵
- **WHEN** `transition_proposal(approved_md, new_status="merged", actor="mark", merged_to_version="v3.1")` 完成後對新路徑呼叫 `parse_proposal(new_path)`
- **THEN** SHALL 回傳 `ProposalDraft`，不因 `merged_at` / `merged_to_version` 鍵存在而拋 `ProposalParseError`
