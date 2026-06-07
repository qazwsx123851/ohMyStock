## ADDED Requirements

### Requirement: Dashboard 風控、月度熔斷與成本呈現

Dashboard SHALL 呈現 risk gate 三色燈、月度熔斷 banner 與本月成本進度條，資料源為 dashboard summary（見 admin-read-endpoints delta）。視覺沿用既有 design tokens（紅漲綠跌語意）。

#### Scenario: risk gate 三色燈

- **WHEN** dashboard summary `risk_gate.status` 為 green / yellow / red
- **THEN** Dashboard 顯示對應綠 / 黃 / 紅燈，並列出 `triggers`（red 時可見觸發條件）

#### Scenario: 月度熔斷 banner

- **WHEN** `monthly_breaker.tripped = true`
- **THEN** Dashboard 顯示紅色 banner、提示禁止新進場與須跑月度復盤

#### Scenario: 成本進度條變色

- **WHEN** `cost.pct` ≥ 80%
- **THEN** 成本進度條轉橘色
- **WHEN** `cost.pct` < 80%
- **THEN** 進度條為正常色
