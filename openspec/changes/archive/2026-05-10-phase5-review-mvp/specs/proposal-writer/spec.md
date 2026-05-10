## ADDED Requirements

### Requirement: 提供 ProposalDraft frozen pydantic model

系統 SHALL 提供 `ohmystock.proposal.schema.ProposalDraft` pydantic model，採 `frozen=True` 與 `extra="forbid"`，欄位至少包含：`topic: str`（kebab-case，1-40 字元）、`target_section: str`（cheatsheet 章節 / 程式碼路徑說明）、`created_by: str`、`created_at: datetime`（含時區）、`review_id: str | None`、`priority: Literal["high","medium","low"]`、`description: str`（§1 改動描述內文）、`motivation: str`（§2 動機與佐證內文，需含至少一個 `metrics.json#` JSON pointer 字串）、`diff_draft: str`（§3 改動 diff 草稿內文）、`expected_impact: str`（§4 預期影響範圍內文）、`risk_assessment: str`（§5 風險評估內文）、`validation_plan: str`（§6 驗證計畫內文）、`expected_improvement: str`（§7 預期改善幅度內文）。任何 model 之外的欄位 SHALL 在驗證時拋 `pydantic.ValidationError`。

#### Scenario: 缺欄位拋 ValidationError
- **WHEN** 建構 `ProposalDraft(topic="vcp-x")` 而省略其他必填欄位
- **THEN** SHALL 拋 `pydantic.ValidationError`，error 含至少 `target_section` 欄位的 missing 訊息

#### Scenario: 多餘欄位拋 ValidationError
- **WHEN** 建構 `ProposalDraft(..., status="approved")` 額外傳 `status` 欄位
- **THEN** SHALL 拋 `pydantic.ValidationError`，error 訊息含 `extra fields not permitted` 或同義訊息

#### Scenario: topic 非 kebab-case 拒絕
- **WHEN** 建構 `ProposalDraft(topic="VCP_volume_threshold", ...)`（含底線、大寫）
- **THEN** SHALL 拋 `pydantic.ValidationError`，error 訊息指明 topic 必須符合 `^[a-z0-9]+(-[a-z0-9]+)*$`

#### Scenario: topic 超過 40 字元拒絕
- **WHEN** 建構 `ProposalDraft(topic="x" * 41, ...)`
- **THEN** SHALL 拋 `pydantic.ValidationError`，error 訊息指明長度上限 40

#### Scenario: motivation 缺 JSON pointer 拒絕
- **WHEN** 建構 `ProposalDraft(motivation="VCP 命中率太低，建議放寬", ...)` 而 motivation 不含 `metrics.json#` 子字串
- **THEN** SHALL 拋 `pydantic.ValidationError`，error 訊息指明 motivation 必須引用至少一個 `metrics.json#` JSON pointer

---

### Requirement: write_proposal 寫出 markdown 並強制 status=pending

系統 SHALL 提供 `ohmystock.proposal.writer.write_proposal(draft: ProposalDraft, proposals_dir: Path) -> Path` 函式，把 `ProposalDraft` 轉成 markdown 寫到 `<proposals_dir>/<YYYY-MM-DD>-<topic>.md`（`<YYYY-MM-DD>` 取自 `draft.created_at.date()`）。輸出 markdown SHALL 含 YAML frontmatter（`proposal_id` / `target_section` / `status` / `created_by` / `created_at` / `review_id` / `priority`）以及 8 個 `## ` 內文段落（`改動描述` / `動機與佐證` / `改動 diff 草稿` / `預期影響範圍` / `風險評估` / `驗證計畫` / `預期改善幅度` / `變更紀錄`）。frontmatter 中 `status` SHALL **強制**為 `"pending"`，**忽略**任何其他傳入值。回傳值 SHALL 為實際寫入的檔案路徑（含 collision suffix）。

#### Scenario: status 強制 pending
- **WHEN** 呼叫 `write_proposal(draft, dir)`，draft 不含 status 欄位
- **THEN** 寫出檔的 frontmatter SHALL 含 `status: pending`；無其他 status 值

#### Scenario: 8 個段落都出現
- **WHEN** 呼叫 `write_proposal(draft, dir)` 完成
- **THEN** 寫出檔內容 SHALL 依序含 `## 1. 改動描述` / `## 2. 動機與佐證` / `## 3. 改動 diff 草稿` / `## 4. 預期影響範圍` / `## 5. 風險評估` / `## 6. 驗證計畫` / `## 7. 預期改善幅度` / `## 8. 變更紀錄` 八個 markdown heading

#### Scenario: 變更紀錄段含 created 標記
- **WHEN** 呼叫 `write_proposal(draft, dir)` 完成，draft.created_at 為 `2026-04-30T19:30:00+08:00`、created_by 為 `post_trade_review_team`
- **THEN** 寫出檔的「變更紀錄」段 SHALL 至少含一行 `- 2026-04-30T19:30:00+08:00 created by post_trade_review_team`

#### Scenario: proposal_id 對齊檔名
- **WHEN** 呼叫 `write_proposal(draft, dir)` 寫出 `2026-04-30-vcp-volume-threshold.md`
- **THEN** 寫出檔的 frontmatter `proposal_id` SHALL 等於 `"2026-04-30-vcp-volume-threshold"`（不含 `.md` 後綴）

---

### Requirement: 檔名衝突 auto-suffix 至 -99

當目標檔名已存在於 `proposals_dir` 時，`write_proposal` SHALL 嘗試 `<YYYY-MM-DD>-<topic>-2.md`、`-3.md`、… 直到找到不存在的檔名（最多 `-99`）。所有 collision 路徑（`-2.md` 到 `-99.md`）皆已存在 SHALL 拋 `RuntimeError`，message 含字串 `"too many proposals"`。**`write_proposal` SHALL 永不覆寫已存在的檔案**，無 force flag、無 overwrite option。

#### Scenario: 同 topic 第二次寫入加 -2 後綴
- **WHEN** `proposals_dir/2026-04-30-vcp-volume-threshold.md` 已存在，呼叫 `write_proposal(draft_same_topic, dir)`
- **THEN** SHALL 寫出 `proposals_dir/2026-04-30-vcp-volume-threshold-2.md`；既有檔內容 SHALL **不**變動

#### Scenario: -2 也存在則加 -3
- **WHEN** `proposals_dir/2026-04-30-vcp-volume-threshold.md` 與 `proposals_dir/2026-04-30-vcp-volume-threshold-2.md` 都已存在
- **THEN** SHALL 寫出 `proposals_dir/2026-04-30-vcp-volume-threshold-3.md`

#### Scenario: 99 全用完拋 RuntimeError
- **WHEN** `proposals_dir/2026-04-30-vcp-volume-threshold.md` 與 `-2.md` 至 `-99.md` 全部已存在
- **THEN** SHALL 拋 `RuntimeError`，message SHALL 包含字串 `"too many proposals"`

---

### Requirement: validate_template 對既有檔案 round-trip 解析

系統 SHALL 提供 `ohmystock.proposal.writer.parse_proposal(path: Path) -> ProposalDraft` 函式，從既有 markdown 檔反向解析回 `ProposalDraft`（不含 status 欄位，因 status 由 writer 強制）。`write_proposal(draft, dir)` 寫出後再用 `parse_proposal` 讀回 SHALL 取得 byte-identical（除 status 欄位外）的 `ProposalDraft`。**Round-trip 失敗** SHALL 拋 `ProposalParseError` 含具體缺漏欄位名。

#### Scenario: write 後 parse 取回原 draft
- **WHEN** `write_proposal(draft_original, dir)` 寫出後立即 `parse_proposal(written_path)` 讀回 `draft_parsed`
- **THEN** `draft_parsed.topic` / `target_section` / `created_by` / `created_at` / `review_id` / `priority` / `description` / `motivation` / `diff_draft` / `expected_impact` / `risk_assessment` / `validation_plan` / `expected_improvement` SHALL 全部與 `draft_original` 對應欄位相等

#### Scenario: parse 缺段落拋 ProposalParseError
- **WHEN** 對一份缺少「## 5. 風險評估」段落的 markdown 呼叫 `parse_proposal(path)`
- **THEN** SHALL 拋 `ProposalParseError`，message 含字串 `"風險評估"` 或欄位名 `"risk_assessment"`
