## ADDED Requirements

### Requirement: `ohmystock decide` 子命令

系統 SHALL 在 `ohmystock` CLI 註冊 `decide` 子命令，串接 live providers 組裝的 `EntryInput` 與 `entry-decider` capability 的 `decide_entry(...)`，並把系統覆寫後的決策印至 stdout。

子命令 SHALL 接受以下旗標：

- `--symbol <s>`（必填）— 候選個股代號（4 位數字 TWSE / OTC）。
- `--asof <YYYY-MM-DD>`（必填）— 對齊 Phase 2B input assembler 的 `asof_date` 參數。
- `--json / --no-json`（選填，預設 `--no-json`）— `--json` 時 stdout 為 `OrchestrationResult` 對應 dict 的 JSON dump；`--no-json` 時 stdout 為人類可讀 summary（含 decision / force_reject_reason / cost_usd / decision_id 四行）。

行為：

1. 從 `Settings()` 讀 `decider_model`（env `OHMYSTOCK_DECIDER_MODEL`，預設 `claude-opus-4-7`）。若 `decider_model` 以 `fake://` 開頭且 env `OHMYSTOCK_ALLOW_FAKE_DECIDER` 不為 `true` → exit code 4，stderr 印 `"refused to use fake decider in non-test env"`。
2. 用既有 live providers 組 `EntryInput`（candidate / market_context / rules_digest / available_tools / available_skills）。組裝失敗 → exit code 2，stderr 印 `"entry_input_assembly_failed: <reason>"`。
3. 開或建 `OHMYSTOCK_DB_PATH` 指定的 SQLite，呼叫 `init_schema(conn)`（idempotent），呼叫 `decide_entry(...)`。
4. **enter** → exit code 0，依 `--json` 印 stdout。
5. **reject**（含 LLM 自願 reject 與系統 force_reject）→ exit code 1，依 `--json` 印 stdout。
6. **DeciderOutputParseError 或其他 internal exception** → exit code 3，stderr 印 traceback 摘要（前 5 行）。

CLI help 中 SHALL 含字面警告：`"This command writes pending_confirm entries; broker submission is not yet wired."` （提醒目前不會真的下單）。

#### Scenario: `ohmystock decide --help` 列旗標與警告
- **WHEN** 執行 `uv run ohmystock decide --help`
- **THEN** 命令以 exit code 0 結束，stdout 同時包含 `--symbol`、`--asof`、`--json` 三個旗標名稱，且含字面 `pending_confirm`

#### Scenario: enter 路徑印 summary 並 exit 0
- **GIVEN** monkeypatch `decide_entry` 回 `OrchestrationResult(decision_id="dec_2026-04-30T14-30-00_2330", final=DeciderOutput(decision="enter", ...), written_kind="entry", llm_cost=LLMCost(0.37), force_reject_reason=None)`，且 input assembler 順利
- **WHEN** 執行 `uv run ohmystock decide --symbol 2330 --asof 2026-04-30`
- **THEN** 命令以 exit code 0 結束，stdout 含字串 `decision: enter`、`decision_id: dec_2026-04-30T14-30-00_2330`、`cost_usd: 0.37`

#### Scenario: --json 印合法 JSON
- **GIVEN** 同前 GIVEN
- **WHEN** 執行 `uv run ohmystock decide --symbol 2330 --asof 2026-04-30 --json`
- **THEN** 命令以 exit code 0 結束，`json.loads(stdout)` 是 dict 且包含 `decision_id` / `decision` / `force_reject_reason` / `cost_usd` 四個 key

#### Scenario: reject 路徑 exit 1
- **GIVEN** monkeypatch `decide_entry` 回 `written_kind="reject", force_reject_reason="stage_4_excluded"`
- **WHEN** 執行 `uv run ohmystock decide --symbol 2330 --asof 2026-04-30`
- **THEN** 命令以 exit code 1 結束，stdout 含 `decision: reject`、`force_reject_reason: stage_4_excluded`

#### Scenario: input assembler 失敗 exit 2
- **GIVEN** monkeypatch `assemble_entry_input` raise `ValueError("symbol not in universe: 9999")`
- **WHEN** 執行 `uv run ohmystock decide --symbol 9999 --asof 2026-04-30`
- **THEN** 命令以 exit code 2 結束，stderr 含 `entry_input_assembly_failed:` 與 `symbol not in universe`

#### Scenario: parse error exit 3
- **GIVEN** monkeypatch `decide_entry` raise `DeciderOutputParseError(raw_text="...", cause=json.JSONDecodeError(...))`
- **WHEN** 執行 `uv run ohmystock decide --symbol 2330 --asof 2026-04-30`
- **THEN** 命令以 exit code 3 結束，stderr 含 `DeciderOutputParseError`

#### Scenario: 拒絕在非測試環境用 fake decider
- **GIVEN** env `OHMYSTOCK_DECIDER_MODEL=fake://always-enter`、env `OHMYSTOCK_ALLOW_FAKE_DECIDER` 未設或為空
- **WHEN** 執行 `uv run ohmystock decide --symbol 2330 --asof 2026-04-30`
- **THEN** 命令以 exit code 4 結束，stderr 含 `refused to use fake decider`

---

### Requirement: `OHMYSTOCK_DECIDER_MODEL` 與 `OHMYSTOCK_ALLOW_FAKE_DECIDER` 環境變數

`Settings` 類別 SHALL 新增兩個欄位：

- `decider_model: str`（env `OHMYSTOCK_DECIDER_MODEL`），預設 `"claude-opus-4-7"`。
- `ohmystock_allow_fake_decider: bool`（env `OHMYSTOCK_ALLOW_FAKE_DECIDER`），預設 `False`。

`.env.example` SHALL 同時新增這兩個 key（值為 `claude-opus-4-7` 與 `false`）。

#### Scenario: Settings 預設值
- **WHEN** test 透過 `monkeypatch.delenv` 清掉這兩個 env var key（`raising=False`），執行 `Settings(_env_file=None)`
- **THEN** `s.decider_model == "claude-opus-4-7"` 且 `s.ohmystock_allow_fake_decider is False`

#### Scenario: env 覆寫 decider_model
- **GIVEN** env `OHMYSTOCK_DECIDER_MODEL=claude-sonnet-4-6`
- **WHEN** `Settings()`
- **THEN** `s.decider_model == "claude-sonnet-4-6"`

#### Scenario: `.env.example` 新增兩個 key
- **WHEN** 讀取 `.env.example`
- **THEN** 檔案 SHALL 含 `OHMYSTOCK_DECIDER_MODEL` 與 `OHMYSTOCK_ALLOW_FAKE_DECIDER` 兩個 key
