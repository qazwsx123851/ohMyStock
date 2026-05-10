## 1. 模組骨架

- [x] 1.1 在 `src/ohmystock/proposal/state.py` 建立模組，定義 `ProposalStatus = Literal["pending", "validating", "approved", "merged", "rejected"]`、`ProposalStateError(RuntimeError)`、`_LEGAL_TRANSITIONS: frozenset[tuple[ProposalStatus, ProposalStatus]]`（5 條 edge）、`_SINK_DIR: dict[ProposalStatus, str | None]`
- [x] 1.2 把 `ProposalStatus` / `ProposalStateError` / `transition_proposal` 加到 `src/ohmystock/proposal/__init__.py` 的 `__all__`

## 2. 驗證邏輯

- [x] 2.1 實作 `_validate_new_status(new_status)` — 不在 `get_args(ProposalStatus)` 中拋 `ProposalStateError("unknown_status: <value>")`
- [x] 2.2 實作 `_validate_transition(current, new)` — 不在 `_LEGAL_TRANSITIONS` 拋 `ProposalStateError("illegal_transition: <current> -> <new>")`
- [x] 2.3 實作 `_validate_required_args(new_status, *, actor, reason, validation_report_path, merged_to_version)` — 依 status 檢查 `missing_actor` / `missing_validation_report` / `missing_merged_to_version` / `missing_rejection_reason`
- [x] 2.4 確保檢查順序為：`unknown_status` → `illegal_transition` → required-args（spec 規定 args 檢查 *晚於* transition 檢查）

## 3. 檔案讀寫

- [x] 3.1 實作 `_read_proposal(path) -> tuple[dict, str]` — 用 `yaml.safe_load` 解 frontmatter dict，回傳 `(frontmatter, body_str)`；缺 `---` delimiter 拋 `ProposalStateError("malformed_frontmatter")`
- [x] 3.2 實作 `_resolve_proposals_root(path) -> Path` — 若 parent 名為 `PENDING_REVIEW`/`merged`/`rejected` 則 `path.parent.parent`，否則 `path.parent`
- [x] 3.3 實作 `_resolve_new_path(root, filename, new_status) -> Path` — 依 `_SINK_DIR[new_status]` 拼路徑（`None` → root 根目錄）

## 4. frontmatter & changelog mutation

- [x] 4.1 實作 `_mutate_frontmatter(fm: dict, new_status, *, reason, validation_report_path, merged_to_version, now_iso) -> dict` — 更新 `status`、依 status append `validation_report_path` / `merged_to_version` / `merged_at` / `rejected_reason`；既有 key 順序保留（用 dict 插入順序）
- [x] 4.2 實作 `_append_changelog(body: str, *, old_status, new_status, actor, reason, now_iso) -> str` — 找「## 8. 變更紀錄」heading；找不到拋 `ProposalStateError("malformed_changelog")`；用 `body.rstrip("\n") + "\n- <line>\n"` normalize
- [x] 4.3 實作 `_serialize(fm: dict, body: str) -> str` — `yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)` + `---\n` 包夾 + body

## 5. 原子寫入 + 搬檔

- [x] 5.1 實作 `_atomic_write(content: str, new_path: Path) -> None` — `new_path.parent.mkdir(parents=True, exist_ok=True)`、`tempfile.NamedTemporaryFile(dir=new_path.parent, delete=False, suffix=".md.tmp")` 寫 + `flush` + `os.fsync`、close 後 `os.replace(tmp, new_path)`；exception 時清理 tmp 並 re-raise
- [x] 5.2 在 `transition_proposal` 主函式內整合：`old_path != new_path` 時於 `_atomic_write` 後 `old_path.unlink()`；新路徑已存在拋 `ProposalStateError("destination_exists")` — 必須在 `_atomic_write` *之前* 檢查

## 6. 主函式組裝

- [x] 6.1 在 `transition_proposal(path, new_status, *, actor, reason=None, validation_report_path=None, merged_to_version=None) -> Path` 串起：validate args → read file → validate transition (current_status from frontmatter) → validate required args → resolve paths → check destination_exists → mutate frontmatter → append changelog → serialize → atomic write → unlink old → return new_path
- [x] 6.2 確保 `current_status` 一律由 frontmatter 讀，**不**從 path 推（spec 明文要求）
- [x] 6.3 加 docstring 列出 5 條合法 edge 與每個 status 對應的 required args

## 7. 單元測試（`tests/proposal/test_state.py`）

- [x] 7.1 fixture：用既有 `write_proposal` 寫 `pending` 檔當起點；helper `_make_md(status, *, body=None)` 產生不同狀態的測試檔
- [x] 7.2 測 `ProposalStatus` 5 值（`get_args` tuple equality）
- [x] 7.3 測 5 條合法 transition 全通（pending→validating、validating→approved、validating→rejected、approved→merged、approved→rejected）
- [x] 7.4 測 illegal transitions 全拋 `ProposalStateError`：同狀態、pending→approved、merged→任何、rejected→任何、unknown_status、case-mismatch
- [x] 7.5 測 required-args：approved 缺 validation_report_path / merged 缺 merged_to_version / rejected 缺 reason / rejected reason="" / actor=""
- [x] 7.6 測搬檔：validating→approved 進 PENDING_REVIEW、approved→merged 進 merged、validating→rejected 進 rejected、pending→validating 留根
- [x] 7.7 測 `destination_exists`：手動 touch 殘骸後 transition 拋錯，原檔不變
- [x] 7.8 測 frontmatter mutation：approved 寫 validation_report_path、merged 寫 merged_to_version + merged_at（regex `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$`）、rejected 寫 rejected_reason
- [x] 7.9 測既有 7 鍵順序保留（`list(yaml.safe_load(written_fm).keys())[:7] == [...]`）
- [x] 7.10 測內文 7 段（## 1.~## 7.）byte-identical
- [x] 7.11 測 changelog 追加：regex match `^- \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2} status: pending → validating by mark$`，含 reason 變體
- [x] 7.12 測 malformed_changelog：刪 `## 8. 變更紀錄` heading 後 transition 拋錯，原檔 *未*變動
- [x] 7.13 測原子性：成功後 `parent.glob("*.md.tmp")` 為空；用 monkeypatch 對 `os.replace` 注入 `OSError` 後檢查 tmp 已清掉、原檔內容不變
- [x] 7.14 測 `parse_proposal` round-trip：transition 後對新路徑呼叫 `parse_proposal` 不拋；含新加的 `merged_at` / `merged_to_version` 等鍵也不拋

## 8. 文件

- [x] 8.1 在 `CLAUDE.md` §5 SSOT 表追加一列：`Proposal state machine v0 — transition_proposal API + 5 條合法 edge + sink dir 搬檔 + frontmatter metadata + changelog append + atomic write` → `openspec/specs/proposal-state-machine/spec.md`（archive 後）+ `src/ohmystock/proposal/state.py`
- [x] 8.2 在 `proposals/README.md` §2 流程圖下方新增一段「v0 已完成 / 仍 deferred」對照表（state machine API 完成、validation engine / endpoint / PR 自動化 deferred）

## 9. 驗證

- [x] 9.1 跑 `uv run pytest tests/proposal/test_state.py -v`，全綠
- [x] 9.2 跑 `uv run pytest tests/proposal/ -v`（含既有 schema/writer/round-trip），確認本 change 沒打壞 `proposal-writer` v0
- [x] 9.3 跑 `openspec validate proposal-state-machine --strict`，無 error
