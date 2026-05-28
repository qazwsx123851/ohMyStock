# .claude/rules/ — 專案規則索引

LLM 新對話啟動時的補充規則庫。`CLAUDE.md` 只放跨專案通用行為（Karpathy 4 條 + Response Guidelines）+ 專案一行概要 + 技術堆疊；其餘專案專屬規則拆在此目錄。

## 何時讀哪份

| 檔案 | 何時讀 |
|---|---|
| `workflow.md` | 任何要動 git / OpenSpec / 提交建議的時刻 |
| `ssot-pointers.md` | **改公式、schema、事件、I/O 規格之前**。最重要。 |
| `capability-map.md` | 想知道「某功能怎麼做的」、要找 spec / impl 對應路徑時 |

## 不在此目錄的東西

- **docs 導覽**：讀 `docs/README.md`
- **目前 phase 進度 / 路線圖**：跑 `ls openspec/changes/archive/ | sort` 或 `git log --oneline -20`
- **業務邏輯細節**：依 `ssot-pointers.md` 導向對應 `docs/*.md`
