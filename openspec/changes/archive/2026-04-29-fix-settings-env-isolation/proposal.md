## Why

Phase 0d 任務 8.2 要求在 repo root 放真實 `.env` 跑 smoke-test，於是 `.env` 現在含真 API key。`tests/test_cli.py::test_settings_constructible_without_env` 依賴「repo root 沒有 `.env`」這個隱性前提來驗證 `Settings()` 在 zero-env 情境可建構，於是現在紅燈：

```
AssertionError: assert 'sk-ant-api03-...' is None
```

這是一個 latent test bug，不是 production bug——`Settings` 行為符合 spec（`.env` 存在時就讀）。但 unit test 沒有實際 isolate env，只是仰賴「跑 CI 時 repo 沒 .env」的脆弱假設。Phase 1 開工前必須轉綠，避免後續 change 在紅燈基線上開發。

## What Changes

- 修改 `tests/test_cli.py::test_settings_constructible_without_env`，使測試本身明確 isolate env（用 `Settings(_env_file=None)` 跳過 dotenv，並用 `monkeypatch.delenv` 清掉 11 個 env var key），不再依賴 repo 工作目錄狀態
- 更新 `cli-and-config` capability spec 的「`Settings()` 在無 `.env` 與無 env var 時可建構」scenario 文字，明示 test SHALL 透過 fixture 構造 isolated env，不假設 repo 工作目錄

## Capabilities

### New Capabilities
（無）

### Modified Capabilities
- `cli-and-config`: 「設定檔載入器」requirement 下的 zero-env scenario 改為 SHALL 由 test fixture 主動構造 isolated env（明確 disable `.env` 載入 + 清掉 env var），而非仰賴執行環境本身為空

## Impact

- 影響檔案：`tests/test_cli.py`（1 個測試）、`openspec/specs/cli-and-config/spec.md`（1 個 scenario 措辭）
- 不影響 production 程式碼（`src/ohmystock/config.py` 不動）
- 不影響其他 capability、不新增依賴
- 全部測試應從 1 failed / 34 passed 變回 35 passed
