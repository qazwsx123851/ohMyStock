## Context

Phase 0d 完成後，`tests/test_cli.py::test_settings_constructible_without_env` 紅燈。原因：該 test 直接呼叫 `Settings()` 且斷言 `anthropic_api_key is None`，但 `Settings` 的 `model_config` 寫死 `env_file=".env"`，pydantic-settings 會自動讀 repo root `.env`。Phase 0d 任務 8.2 要求放真實 `.env` 跑 smoke-test，於是 test 在 archive 後第一次跑就紅。

這是個 latent test bug：原本綠是因為當時 repo 沒 `.env`（test 隱性依賴執行環境）。現在 `.env` 是 Phase 0d 的功能性前提，不能砍。修法只能改 test，不能改 production code。

## Goals / Non-Goals

**Goals:**
- `uv run pytest -v` 全綠（35/35）
- Test 不再依賴 repo 工作目錄是否存在 `.env`
- 保留 `Settings` 預設行為（自動讀 `.env`）— production code 不動

**Non-Goals:**
- 不改 `Settings` 類別 API
- 不引入 `tests/conftest.py` 全域 env isolation fixture（only one test 需要 isolation；過早抽象）
- 不改其他 33 個現綠的 test
- 不處理 Phase 1 範圍

## Decisions

### Decision 1: 用 `Settings(_env_file=None)` 跳過 dotenv，不改 production code

pydantic-settings 的 `BaseSettings.__init__` 接受 `_env_file` 關鍵字參數，傳 `None` 會 override `model_config` 裡的 `env_file=".env"`，本次呼叫不讀 dotenv。這是 pydantic-settings 文件化 API（不是 private hack）。

**Alternatives considered:**
- (A) 在 `conftest.py` 寫 autouse fixture 把 `.env` 暫時搬走 → 會影響全部 test、有檔案 IO 風險、過度設計。
- (B) `monkeypatch.chdir(tmp_path)` 切到沒 `.env` 的暫存目錄 → 可行但脆，pydantic-settings 解析 `.env` 路徑相對 cwd，未來行為若改就會壞；也會影響其他依賴 cwd 的程式碼。
- (C) 改 `Settings` 預設 `env_file=None`，靠 caller 顯式傳 → 改 production API、影響 smoke-test、違反 pydantic-settings 慣例。

**選 `_env_file=None`** 因為：作用域最小（只一個 test）、用文件化 API、不動 production code。

### Decision 2: 同步用 `monkeypatch.delenv` 清 11 個 env var

`_env_file=None` 只跳過 dotenv 檔案；若 shell 已 export `ANTHROPIC_API_KEY`，pydantic-settings 仍會吃 process env。本機開發環境很可能已 export 這些 key（user 跑 smoke-test 時設過）。

用 pytest `monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)` 對 11 個 key 各清一次（list comprehension），保證 test isolation 與執行 shell 解耦。`raising=False` 確保 key 不存在也不報錯。

**Alternatives considered:**
- 用 `monkeypatch.setenv` 設成空字串 → `pydantic-settings` 對「key 存在但值為空」的處理依 type annotation 而異，`str | None` 欄位空字串會被解成 `""` 不是 `None`，反而誤判。
- 不清 env，只靠 `_env_file=None` → 在已 export key 的 dev 機器上仍會紅。

### Decision 3: spec scenario 改寫，明示 test isolation 是 contract 一部分

原 scenario「在乾淨環境（無 `.env`、無相關 env var）執行 `Settings()`」的「乾淨環境」措辭隱含了「執行環境本身為空」這個前提，導致 test 怠惰沒去主動 isolate。改寫後 scenario WHEN 句明示「test 透過 `monkeypatch.delenv` 清掉 11 個 key，然後 `Settings(_env_file=None)`」，把 isolation 責任固化進 spec，避免未來再犯。

## Risks / Trade-offs

- **Risk**: `_env_file=None` 是 pydantic-settings 行為，未來大版號 bump 可能改 → **Mitigation**: 跟 `pydantic-settings` lockfile pinning 走；spec 寫的是「test SHALL isolate env」不是「SHALL 用 `_env_file=None`」，未來可換 API。
- **Trade-off**: spec scenario 把實作細節（`monkeypatch.delenv` / `_env_file=None`）寫進 WHEN，違反「spec 應只描述 behavior 不描述實作」的潔癖。但這個 scenario 本來就是「驗證 zero-env 行為的 test」，把 isolation 機制寫清楚比留模糊有用 — solo dev 專案優先防自己再踩坑，不為團隊風格純度設計。
