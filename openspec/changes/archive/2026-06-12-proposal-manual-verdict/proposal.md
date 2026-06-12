# proposal-manual-verdict — WFA 驗證後保留人工確認

## Why

`docs/web-admin-user-testing-spec.md` 落差總表 D7：`user-scenarios.md` §6 寫的是「Mark 看完 WFA 報告才點 merge/reject」，但現行 `run_validation` 非 dry-run 一律自動轉狀態（pass → `approved` 搬 `PENDING_REVIEW/`、fail → `rejected` 搬 `rejected/`）。fail 的提案 Mark 完全沒機會看報告後做最終裁決（例如門檻差一點點但有其他理由想保留）。Boss 已拍板：保留「人工看完報告才決定」的控制權。

## What Changes

- **`run_validation` 加 `auto_transition: bool = True` 參數**：False 且非 dry-run 時，報告照寫（sibling `<slug>.validation.json`）、WFA_PASSED/WFA_FAILED 事件照發，但不呼叫狀態轉移 — 提案停在 `validating`。預設 True，CLI `ohmystock validate-proposal` 行為不變。
- **`POST /api/admin/proposals/{slug}/validate` 改為固定人工模式**：endpoint 一律以 `auto_transition=False` 呼叫；非 dry-run 回應 `new_status: "validating"`、`new_path: null`、`report_path: "<slug>.validation.json"`。人工裁決走既有 transition endpoint（`validating → approved/rejected` 本來就是合法邊）。
- **web-admin 前端**：`<ValidationDialog>` 文案與 toast 改為「報告已產出，狀態維持 validating，請審閱後 Approve/Reject」；`<TransitionDialog>` target=approved 時預填 `validation_report_path = <slug>.validation.json`。

## Capabilities

### New Capabilities
（無）

### Modified Capabilities
- `wfa-validation-engine`：`run_validation` 新增 `auto_transition` 參數
- `admin-proposals-endpoints`：validate endpoint 不再自動轉狀態
- `web-admin-proposals-pages`：ValidationDialog 文案 / TransitionDialog 預填

## Impact

**後端**
- `src/ohmystock/validation/wfa.py`：`run_validation` 簽名 + 末段流程
- `src/ohmystock/api/routes/proposals.py`：`validate_proposal_endpoint` 回應組裝（`_post_run_state_paths` 邏輯）

**前端**
- `web-admin/src/components/validation-dialog.tsx`：DialogDescription + toastMessage
- `web-admin/src/components/transition-dialog.tsx`：approved 預填 report path

**測試**
- `tests/validation/test_wfa.py`：新增 `auto_transition=False` 案例（報告寫出、檔案不動、狀態仍 validating）
- `tests/api/test_admin_proposals_validate_endpoint.py`：非 dry-run 回應斷言改為 `new_status=validating`、檔案留在原位
- `web-admin` Vitest：dialog 文案 / 預填斷言更新

**文件**
- `docs/web-admin-user-testing-spec.md` 落差總表 D7 標記已解決
- `docs/user-scenarios.md` §6 不需改（本來就寫人工確認 — 實作向文件對齊）

**非目標（避免過度工程）**
- 不加前端「auto/manual」toggle — admin 一律人工，CLI 維持自動，無人要求可配置。
- transition 時不自動搬移 `<slug>.validation.json`（frontmatter 路徑僅顯示用，無程式解析）。
- 不改 `rejected` 後不可重驗的既有限制。
