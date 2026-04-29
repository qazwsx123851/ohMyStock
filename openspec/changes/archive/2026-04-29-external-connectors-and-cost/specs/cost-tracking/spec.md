## ADDED Requirements

### Requirement: 提供 @track_llm_cost async decorator

系統 SHALL 提供 `ohmystock.observability.cost_tracker.track_llm_cost` async decorator，其簽章為 `track_llm_cost(decision_id: str | None = None)`。被包住的 async function SHALL 回傳 Anthropic `Message` object（`anthropic.types.Message`）。decorator 在被包住 function 成功 return 後 SHALL 從回傳值的 `usage.input_tokens` 與 `usage.output_tokens` 計算成本，並寫入 `llm_costs` SQLite 表。被包住 function 拋例外時 decorator SHALL **不**寫入成本（避免估算成本造成假帳），但例外 SHALL 原樣 propagate。

#### Scenario: 成功呼叫寫入 cost
- **WHEN** 包住的 async function mock 為回傳 `Message(model="claude-haiku-4-5-20251001", usage=Usage(input_tokens=100, output_tokens=50))`，執行 `await wrapped()`
- **THEN** `llm_costs` 表新增一筆紀錄，`model = "claude-haiku-4-5-20251001"`、`input_tokens = 100`、`output_tokens = 50`、`cost_usd > 0`、`created_at` 為 ISO-8601 含 `+08:00` 時區字串

#### Scenario: 例外不寫 cost 且原樣 propagate
- **WHEN** 包住的 async function 拋出 `RuntimeError("api error")`
- **THEN** `await wrapped()` 拋出同一個 `RuntimeError`；`llm_costs` 表筆數不變

#### Scenario: decision_id 帶入 cost row
- **WHEN** 以 `@track_llm_cost(decision_id="dec_2026-04-30T14-30-00_2330")` 包住 function 並成功執行
- **THEN** `llm_costs` 新增的 row `decision_id = "dec_2026-04-30T14-30-00_2330"`

---

### Requirement: 計費表 hardcode 為常數 dict

系統 SHALL 在 `cost_tracker.py` 模組頂層宣告常數 `MODEL_PRICING_USD_PER_MTOK: dict[str, dict[str, float]]`，至少包含 `claude-opus-4-7`、`claude-sonnet-4-6`、`claude-haiku-4-5-20251001` 三個 key。每個 value 為含 `input` 與 `output` 兩個 float 欄位的 dict（單位 USD per million tokens）。計費表 SHALL **不**從 env var / yaml / 外部資源載入。模型不在表中時 SHALL raise `ValueError`，避免靜默計算為 0。

#### Scenario: 三個模型計費表存在
- **WHEN** 執行 `from ohmystock.observability.cost_tracker import MODEL_PRICING_USD_PER_MTOK`
- **THEN** dict 至少包含 `claude-opus-4-7`、`claude-sonnet-4-6`、`claude-haiku-4-5-20251001` 三個 key；每個 value 含 `input` 與 `output` 兩個 float 欄位

#### Scenario: 未知模型 raise ValueError
- **WHEN** 包住的 function 回傳 `Message(model="claude-future-99", usage=...)`，執行 decorator
- **THEN** decorator 拋出 `ValueError`，message 包含 `"claude-future-99"` 與「未在計費表」相關文字（如 `"unknown model"` 或 `"未知模型"`）

---

### Requirement: 月度成本聚合 query helper

系統 SHALL 提供 `ohmystock.observability.cost_tracker.get_monthly_cost_usd(year_month: str) -> float` 函式。`year_month` 格式為 `YYYY-MM`（e.g. `"2026-04"`）。函式 SHALL 回傳該月（依 `created_at` 字串 prefix 比對）所有 `llm_costs` row 的 `cost_usd` 加總；無資料時回傳 `0.0`。

#### Scenario: 聚合該月所有 cost
- **WHEN** `llm_costs` 表內有三筆 `created_at` 開頭為 `2026-04`、`cost_usd` 分別 `0.01 / 0.02 / 0.03`，與一筆 `2026-05` 的 `0.10`，執行 `get_monthly_cost_usd("2026-04")`
- **THEN** 回傳 `0.06`（誤差容忍 `< 1e-9`）

#### Scenario: 無資料回傳 0.0
- **WHEN** `llm_costs` 表為空，執行 `get_monthly_cost_usd("2026-04")`
- **THEN** 回傳 `0.0`
