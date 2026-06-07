## ADDED Requirements

### Requirement: 使用者覆寫進場張數

confirm endpoint SHALL 接受可選的 `override_qty`。提供時，伺服器 MUST 套用兩層 sizing 防線（`docs/safety-and-simulation.md` §2.9）；伺服器為唯一裁決點，前端 dialog 不得繞過。未提供時，沿用既有 sizing 行為（向後相容）。

#### Scenario: 提供範圍內的 qty

- **WHEN** confirm 帶 `override_qty` 且未觸發任一防線
- **THEN** 以該 qty 送出下單，回應 `qty` 等於使用者輸入值

#### Scenario: 超過名目上限（硬界）

- **WHEN** `override_qty` 使名目曝險超過帳戶權益 25% 上限
- **THEN** 回 409 `error.code=qty_exceeds_notional_limit`，含允許上限，不下單

#### Scenario: 偏離系統公式（軟界）

- **WHEN** `override_qty` 在名目上限內、但偏離系統 sizing 公式 >30%
- **THEN** 伺服器 clamp 到較保守值下單，回 200 標記 `clamped:true` 與實際 `qty`

#### Scenario: 未提供 override_qty（向後相容）

- **WHEN** confirm 未帶 `override_qty`
- **THEN** 沿用既有後端 sizing 計算決定張數，行為與現況一致
