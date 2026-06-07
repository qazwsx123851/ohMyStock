## ADDED Requirements

### Requirement: Provider 連線測試 UI

Settings 頁 SHALL 為 Shioaji / FinMind 各提供連線測試按鈕，點擊後呼叫 test-connection endpoint 並即時呈現成功（含延遲）或失敗（含錯誤訊息，不顯示金鑰明文）。

#### Scenario: 測試成功

- **WHEN** 點擊某 provider 的連線測試且回 `ok:true`
- **THEN** 顯示成功狀態與 latency

#### Scenario: 測試失敗

- **WHEN** 回 `ok:false`
- **THEN** 顯示失敗狀態與 error 訊息，不洩漏金鑰

### Requirement: 額度與模型分布顯示

Settings 頁 SHALL 唯讀顯示 `budget` 區塊（已用 / 預算 / 剩餘）與 `model_mix` 各模型佔比。

#### Scenario: 顯示預算與模型分布

- **WHEN** settings payload 含 `budget`
- **THEN** 頁面顯示已用/預算/剩餘額度與各模型佔比
