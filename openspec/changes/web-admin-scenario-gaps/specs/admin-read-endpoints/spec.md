## ADDED Requirements

### Requirement: Dashboard summary 風控、熔斷與成本欄位

Dashboard summary 回應 SHALL 提供 risk gate 狀態、月度熔斷旗標、本月 LLM 成本與預算。後端僅組裝既有來源的狀態，**不得重抄或重算**交易公式（觸發條件 SSOT：`docs/workflow-cheatsheet.md` §0；月度熔斷門檻同 §0）。

#### Scenario: 回傳 risk gate 狀態

- **WHEN** 前端查詢 dashboard summary
- **THEN** 回應含 `risk_gate.status` ∈ `{green, yellow, red}` 與 `risk_gate.triggers`（觸發的條件名稱字串陣列，未觸發為空陣列）

#### Scenario: 月度熔斷已觸發

- **WHEN** 當月 PnL 達月度熔斷門檻
- **THEN** 回應 `monthly_breaker.tripped = true`，並含 `monthly_breaker.month_pnl_pct`

#### Scenario: 月度熔斷未觸發

- **WHEN** 當月 PnL 未達門檻
- **THEN** 回應 `monthly_breaker.tripped = false`

#### Scenario: 回傳本月成本與預算

- **WHEN** 前端查詢 dashboard summary
- **THEN** 回應含 `cost.used_usd`、`cost.budget_usd`、`cost.pct`（used / budget）
