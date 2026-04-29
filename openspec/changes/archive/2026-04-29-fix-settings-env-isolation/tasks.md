## 1. 修復 test isolation

- [x] 1.1 在 `tests/test_cli.py::test_settings_constructible_without_env` 加入 `monkeypatch: pytest.MonkeyPatch` 參數，function body 開頭用 list comprehension 對 11 個 env var key（`ANTHROPIC_API_KEY`、`SHIOAJI_API_KEY`、`SHIOAJI_SECRET_KEY`、`SHIOAJI_CA_PATH`、`SHIOAJI_CA_PASSWD`、`SHIOAJI_PERSON_ID`、`FINMIND_TOKEN`、`OHMYSTOCK_AUTO_EXECUTE`、`OHMYSTOCK_LLM_DEGRADE`、`OHMYSTOCK_DB_PATH`、`OHMYSTOCK_LOG_LEVEL`）逐一呼叫 `monkeypatch.delenv(key, raising=False)`
- [x] 1.2 把 `Settings()` 改成 `Settings(_env_file=None)`，其餘三條 assertion 不動

## 2. 驗證

- [x] 2.1 跑 `uv run pytest tests/test_cli.py -v` 確認 `test_settings_constructible_without_env` 轉綠（且其他 6 個 test_cli 測試保持綠）
- [x] 2.2 跑 `uv run pytest -q` 確認 35 個 test 全綠
- [x] 2.3 跑 `uv run ohmystock smoke-test`（本機已有真實 `.env`），確認 3 項 PASS、exit 0（驗證 production `Settings` 行為未動）

## 3. 收尾

- [x] 3.1 跑 `openspec validate fix-settings-env-isolation --strict` 通過
- [x] 3.2 commit（commit message 引用 change name + 簡述「test isolation, no production change」）
