## MODIFIED Requirements

### Requirement: 全部端點維持無認證（v0 no Bearer）

本 capability 涵蓋的所有端點 SHALL 通過 `web-admin-bearer-auth` capability 的 `require_admin` dependency；不帶 token 的 request SHALL 回 HTTP 401，body 為統一 envelope `{"ok": false, "error": {"code": "auth_missing", "message": <human-readable>}}`。token 不符的 request SHALL 回 HTTP 401，`error.code == "auth_invalid"`。本 capability 自身**不**重複實作 token 比對邏輯，僅在 router 註冊時引用 `Depends(require_admin)`，由 `web-admin-bearer-auth` 的 dependency 與 envelope handler 完成 401 映射。

#### Scenario: screener endpoint 不帶 Authorization 回 401
- **WHEN** 對 `POST /api/admin/screener/run` 發 valid body 但**不**帶 `Authorization` header
- **THEN** HTTP status 為 401；body `["ok"] is False`、`["error"]["code"] == "auth_missing"`

#### Scenario: confirm endpoint 不帶 Authorization 回 401
- **WHEN** 對 `POST /api/admin/confirm-gate/confirm` 發 valid body 但**不**帶 `Authorization` header
- **THEN** HTTP status 為 401；`["error"]["code"] == "auth_missing"`

#### Scenario: 帶合法 token 端點正常運作
- **GIVEN** `Settings.ohmystock_admin_token` 設為合法 token、`Authorization: Bearer <valid>` header 帶上
- **WHEN** 對 `POST /api/admin/screener/run` 發 valid body
- **THEN** HTTP 200；走 success path；envelope shape 與本 capability 其他 success scenario 一致
