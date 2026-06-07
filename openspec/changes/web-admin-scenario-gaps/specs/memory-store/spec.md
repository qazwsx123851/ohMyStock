## ADDED Requirements

### Requirement: Memory 寫入（insert）

MemoryStore SHALL 提供 insert 路徑，寫入一筆 memory（kind/content/tags/source），並透過既有 FTS5 INSERT 觸發器同步索引。schema 不變。

#### Scenario: insert 後可檢索

- **WHEN** 透過 store insert 一筆 memory
- **THEN** 該筆可由 list 取得，且其 content 可由 FTS5 search 命中

#### Scenario: insert 寫入 created_at

- **WHEN** insert 一筆 memory
- **THEN** 該筆帶有 created_at（ISO 8601，含時區）
