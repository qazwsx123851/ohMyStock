## ADDED Requirements

### Requirement: Provider 連線測試 endpoint

系統 SHALL 提供 `POST /api/admin/settings/test-connection`，body `{ provider }`（`shioaji` 或 `finmind`），對該 provider 做輕量呼叫並回 `{ ok, latency_ms?, error? }`。測試 MUST NOT 下單、MUST NOT 消耗顯著額度（Shioaji 僅查 login 狀態、FinMind 僅做最小查詢）。

#### Scenario: 連線成功

- **WHEN** 對已正確設定的 provider 發 test-connection
- **THEN** 回 200 `{ ok: true, latency_ms }`

#### Scenario: 連線失敗

- **WHEN** provider 未設定或無法連線
- **THEN** 回應 `{ ok: false, error }`，error 不洩漏金鑰明文

#### Scenario: 不支援的 provider

- **WHEN** body 帶非 `shioaji`/`finmind` 的 provider
- **THEN** 回 400 `error.code=invalid_input`

### Requirement: 預算與模型分布欄位

settings payload SHALL 新增 `budget` 區塊 `{ used_usd, budget_usd, remaining_usd, model_mix }`，其中 `model_mix` 含各模型（opus/sonnet/haiku）使用佔比，資料源為 cost-tracking。此區塊為唯讀。

#### Scenario: 回傳預算與模型分布

- **WHEN** 前端查詢 settings
- **THEN** 回應 `budget` 區塊含 used/budget/remaining 與 `model_mix` 各模型佔比
