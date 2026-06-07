## ADDED Requirements

### Requirement: reject 自訂原因輸入

Confirm Gate reject 動作 SHALL 開啟輸入框收集使用者自訂 `reason`，並以該文字送出（移除寫死的 `user_reject`）。空白 reason MUST 於前端擋下、不送出。

#### Scenario: 輸入原因並拒絕

- **WHEN** 使用者點拒絕、輸入非空原因、送出
- **THEN** reject 請求 `reason` 帶該文字，成功後卡片消失

#### Scenario: 空白原因

- **WHEN** 使用者未輸入原因即送出
- **THEN** 前端擋下、不發送請求

### Requirement: confirm 二次輸入張數

Confirm Gate confirm 動作 SHALL 開啟 ConfirmDialog 顯示後端建議張數並允許手動覆寫，送出時帶 `qty`。實際成交張數以伺服器套 sizing clamp 後為準（見 confirm-gate delta）。

#### Scenario: 覆寫張數確認

- **WHEN** 使用者於 ConfirmDialog 修改張數並確認
- **THEN** confirm 請求帶該 `qty`，成功後依伺服器回應更新持倉

#### Scenario: 沿用建議張數

- **WHEN** 使用者不修改、直接確認
- **THEN** confirm 以建議張數送出
