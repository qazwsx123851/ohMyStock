# design — proposal-manual-verdict

## D1. `auto_transition` 放在 library 層，endpoint 寫死 False

三個候選位置比較：

| 方案 | 說明 | 取捨 |
|---|---|---|
| A. 只改 endpoint（不碰 wfa.py，endpoint 自己不呼叫 transition） | 不可行 — transition 在 `run_validation` 內部，endpoint 攔不到 | — |
| B. `run_validation` 加 `auto_transition` 參數，endpoint 寫死 False（採用） | CLI 預設不變；admin 一律人工；無新請求欄位 | 最小 diff |
| C. ValidateRequest 加 `auto_transition` body 欄位 | 提供前端 toggle 彈性 | 無人要求的可配置性，違反 simplicity-first |

採 **B**。`ValidateRequest` 不加欄位（`extra="forbid"` 維持原樣）。

## D2. 報告落點與人工 approve 的銜接

`auto_transition=False` 時報告寫在 proposals root（與停在 `validating` 的 markdown 同層）：`<root>/<slug>.validation.json`。

人工 approve 走既有 `POST .../transition`，`validation_report_path` 由 Mark 填（前端預填 `<slug>.validation.json`）。markdown 搬進 `PENDING_REVIEW/` 後報告留在 root — 該 frontmatter 路徑目前僅顯示用（`extra_frontmatter`），無程式解析，不做搬移（見 proposal 非目標）。

## D3. 回應欄位語意（非 dry-run + 人工模式）

```json
{
  "verdict": "pass | fail",
  "new_status": "validating",
  "new_path": null,
  "report_path": "<slug>.validation.json",
  "deltas": {...},
  "failures": [...]
}
```

`_post_run_state_paths` 改寫：dry-run → `(None, None)` 不變；人工模式 → `(None, "<slug>.validation.json")`。原本依 verdict 推 sink 目錄的分支整段移除（endpoint 已無自動轉路徑）。

## D4. 既有測試的破壞面

- `tests/api/test_admin_proposals_validate_endpoint.py` 中斷言「pass 後檔案在 PENDING_REVIEW/」「fail 後在 rejected/」的案例改為斷言「檔案留在原位、status 仍 validating、報告存在於 root」。
- `tests/validation/test_wfa.py` 既有案例不動（預設 True 行為不變），新增 False 案例。
- web-admin Vitest：`validation-dialog` toast 文案斷言、`transition-dialog` approved 預填斷言。
