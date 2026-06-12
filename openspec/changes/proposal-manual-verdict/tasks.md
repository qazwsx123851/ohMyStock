# tasks — proposal-manual-verdict

## 1. 後端 wfa.py

- [x] 1.1 `run_validation` 加 `auto_transition: bool = True` keyword；False 且非 dry-run 時寫報告後直接 return（不呼叫 `_transition_after_verdict`）
- [x] 1.2 `tests/validation/test_wfa.py` 新增案例：`auto_transition=False` → 報告寫出於 root、markdown 未搬移、frontmatter status 仍 `validating`、事件照發

## 2. 後端 validate endpoint

- [x] 2.1 `validate_proposal_endpoint` 以 `auto_transition=False` 呼叫 `run_validation`；`_post_run_state_paths` 改為人工模式語意（new_path 恆 None；report_path 非 dry-run 時為 `<slug>.validation.json`）
- [x] 2.2 非 dry-run 回應 `new_status` 恆為 `"validating"`
- [x] 2.3 更新 `tests/api/test_admin_proposals_validate_endpoint.py`：pass/fail 兩案例斷言檔案留原位 + status 仍 validating + 報告存在

## 3. 前端 web-admin

- [x] 3.1 `validation-dialog.tsx`：DialogDescription 與 `toastMessage` 改為人工模式文案（pass/fail 都提示「請審閱後 Approve/Reject」）
- [x] 3.2 `transition-dialog.tsx`：target=approved 開啟時預填 `validation_report_path = <slug>.validation.json`
- [x] 3.3 更新對應 Vitest 斷言

## 4. 文件同步

- [x] 4.1 `docs/web-admin-user-testing-spec.md` 落差總表 D7 改為已解決
- [ ] 4.2 spec delta 同步至 `openspec/specs/`（留待 `/opsx:archive` 流程處理）

## 5. 驗收

- [x] 5.1 後端 pytest 全綠（1535 passed）
- [x] 5.2 web-admin Vitest 全綠（248 passed；e2e/smoke.spec.ts 被 Vitest 誤抓為既有問題，與本 change 無關）
