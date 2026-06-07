## ADDED Requirements

### Requirement: Memory 寫入 endpoint

系統 SHALL 提供 `POST /api/admin/memory/rows`，body `{ kind, content, tags?, source? }`，新增一筆 memory 並回傳建立的 row。`kind` MUST 限既有有效值（note/lesson/proposal/review_summary）；`content` MUST 非空。寫入後該筆 MUST 可被既有 list / FTS5 search 檢索。

#### Scenario: 成功寫入

- **WHEN** 以合法 `kind` + 非空 `content` POST memory row
- **THEN** 回 200 含新建 row（id/kind/content/tags/source/created_at）
- **AND** 後續 list / search 可查到該筆

#### Scenario: 無效 kind

- **WHEN** `kind` 不在有效集合
- **THEN** 回 400 `error.code=invalid_input`

#### Scenario: 空 content

- **WHEN** `content` 為空或全空白
- **THEN** 回 400 `error.code=invalid_input`
