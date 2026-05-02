## ADDED Requirements

### Requirement: `ohmystock confirm` 子命令

系統 SHALL 在 `ohmystock` CLI 註冊 `confirm` 子命令，包裝 `confirm-gate` capability 的四個函式（`list_pending` / `confirm` / `reject` / `sweep_expired`），讓 solo dev 可由命令列驅動 pending entry 的人工生命週期。

子命令 SHALL 支援以下旗標組合（互斥群組）：

| 旗標組合 | 行為 | Exit code |
|---|---|---|
| `--list` | 印出目前所有 pending entry（decision_id、symbol、age、TTL）；表格形式至 stdout | `0`（含空 list） |
| `<decision_id>` | 對該 decision_id 呼叫 `confirm(...)`；成功印 fill 摘要至 stdout | `0` 成功 / `2` not_found / `2` not_pending / `2` already expired / `3` broker_failed |
| `<decision_id> --reject [--reason "..."]` | 對該 decision_id 呼叫 `reject(...)`；`--reason` 為空時用預設 `"human rejected via confirm gate"` | `1` 成功（人工 reject 為「semantic non-zero」）/ `2` not_found / `2` not_pending |
| `--sweep-expired` | 呼叫 `sweep_expired(...)`；印被 sweep 的 decision_id 數量與清單至 stdout | `0`（含 sweep 0 筆） |
| 同時給 `--list` 與 `--reject` / `--sweep-expired` | Typer mutually-exclusive options 拒絕 | `2`（Typer usage error） |

子命令 SHALL 共用以下旗標：
- `--user TEXT`（預設 `os.getenv("USER", "unknown")`）— 寫入 `human_confirmed_by` / `rejected_by`。
- `--db PATH`（預設來自 `Settings().ohmystock_db_path`）— SQLite 路徑。
- `--timeout-minutes INT`（預設來自 `Settings().ohmystock_confirm_timeout_minutes`）— sweep / list 用的 TTL。
- `--default-capital-twd INT`（預設來自 `Settings().ohmystock_default_capital_twd`）— confirm 計算 qty 用。
- `--json` — 將結構化結果以 JSON 印至 stdout（含 `action`、`decision_id`、`fill` / `reject` / `expire` / `pending` 細節）。

子命令 SHALL 在執行任何寫入前呼叫 `init_schema(conn)` 確保表存在（idempotent）。子命令 SHALL 在 `OHMYSTOCK_AUTO_EXECUTE=true` 時於 stderr 印一行警告 `"warning: auto mode requires the Phase 3.5 breaker, falling back to human confirm"`，然後正常執行人工流程（v0 不支援 auto）。

子命令 root help SHALL 含字面 `pending_confirm` 與 `expire` 字串，以提示用戶其影響的 lifecycle 狀態。

#### Scenario: `ohmystock confirm --help` 列旗標與警告
- **WHEN** 執行 `uv run ohmystock confirm --help`
- **THEN** stdout 含 `--list`、`--reject`、`--sweep-expired`、`--user`、`--reason`、`--timeout-minutes`、`--default-capital-twd`、`--json` 字串；含字面 `pending_confirm` 與 `expire`

#### Scenario: `--list` 印 pending entry 並 exit 0
- **GIVEN** monkeypatch `list_pending` 回 `[PendingEntry(decision_id="dec_X", symbol="2330", created_at="2026-05-02T10:00:00+08:00", age_seconds=900, ttl_seconds=900, current_price=832.0, final_sizing_pct=16.5)]`
- **WHEN** 執行 `uv run ohmystock confirm --list`
- **THEN** 命令以 exit code 0 結束，stdout 含 `dec_X`、`2330`、`832`、`16.5`、`900`

#### Scenario: `<decision_id>` 成功 confirm 並 exit 0
- **GIVEN** monkeypatch `confirm` 回 `ConfirmResult(decision_id="dec_X", fill=Fill(symbol="2330", filled_qty=1000, fill_price=832.0, fill_ts="2026-05-02T10:15:00+08:00", side="buy", requested_qty=1000), qty=1000)`
- **WHEN** 執行 `uv run ohmystock confirm dec_X`
- **THEN** 命令以 exit code 0 結束，stdout 含 `dec_X`、`2330`、`1000`、`832.0`、`confirmed`

#### Scenario: `<decision_id> --reject --reason "..."` 成功 reject 並 exit 1
- **GIVEN** monkeypatch `reject` 回 `RejectResult(decision_id="dec_X", reject_row_id=42)`
- **WHEN** 執行 `uv run ohmystock confirm dec_X --reject --reason "盤勢不對"`
- **THEN** 命令以 exit code 1 結束（semantic non-zero），stdout 含 `dec_X`、`rejected`、`盤勢不對`

#### Scenario: `<decision_id>` 對不存在的 decision exit 2
- **GIVEN** monkeypatch `confirm` raise `ConfirmGateError(code="not_found", ...)`
- **WHEN** 執行 `uv run ohmystock confirm dec_does_not_exist`
- **THEN** 命令以 exit code 2 結束，stderr 含 `not_found`

#### Scenario: `<decision_id>` broker 失敗 exit 3
- **GIVEN** monkeypatch `confirm` raise `ConfirmGateError(code="broker_failed", cause=BrokerError("forced"))`
- **WHEN** 執行 `uv run ohmystock confirm dec_X`
- **THEN** 命令以 exit code 3 結束，stderr 含 `broker_failed`

#### Scenario: `--sweep-expired` 印 sweep 結果並 exit 0
- **GIVEN** monkeypatch `sweep_expired` 回 `["dec_A", "dec_B"]`
- **WHEN** 執行 `uv run ohmystock confirm --sweep-expired`
- **THEN** 命令以 exit code 0 結束，stdout 含 `2 expired`、`dec_A`、`dec_B`

#### Scenario: `--sweep-expired` 0 筆過期 exit 0
- **GIVEN** monkeypatch `sweep_expired` 回 `[]`
- **WHEN** 執行 `uv run ohmystock confirm --sweep-expired`
- **THEN** 命令以 exit code 0 結束，stdout 含 `0 expired`

#### Scenario: 同時給 --list 與 --reject 拒絕
- **WHEN** 執行 `uv run ohmystock confirm dec_X --list --reject`
- **THEN** 命令以 exit code 2 結束（Typer usage error），stderr 含 `mutually exclusive` 或等價字串

#### Scenario: OHMYSTOCK_AUTO_EXECUTE=true 印 warning 但仍跑人工流程
- **GIVEN** env `OHMYSTOCK_AUTO_EXECUTE=true`，monkeypatch `confirm` 回 `ConfirmResult(...)`
- **WHEN** 執行 `uv run ohmystock confirm dec_X`
- **THEN** 命令以 exit code 0 結束；stderr 含字面 `auto mode requires the Phase 3.5 breaker`；stdout 含 `confirmed`（仍跑人工流程）

#### Scenario: `--json` 路徑回合法 JSON dict
- **WHEN** 執行 `uv run ohmystock confirm dec_X --json`（對成功 confirm 路徑）
- **THEN** stdout 為合法 JSON，`json.loads` 後為 dict，含 keys：`action`（值 `"confirm"`）、`decision_id`、`fill`（dict 含 `fill_price`、`filled_qty`、`fill_ts`）、`exit_code`

---

### Requirement: 新增 Settings 欄位 `ohmystock_confirm_timeout_minutes` / `ohmystock_default_capital_twd`

系統 SHALL 在 `ohmystock.config.Settings` 新增以下兩個欄位：

- `ohmystock_confirm_timeout_minutes: int = 30`（env `OHMYSTOCK_CONFIRM_TIMEOUT_MINUTES`，case-insensitive）
- `ohmystock_default_capital_twd: int = 1_000_000`（env `OHMYSTOCK_DEFAULT_CAPITAL_TWD`，case-insensitive）

兩欄位 SHALL 為正 int；當 env 解析得到的值 ≤ 0 時，pydantic SHALL raise `ValidationError`（pydantic 的 `int` 型別不會主動拒絕 0 或負值，故本 requirement SHALL 在 `Settings` model 上加 `field_validator` 強制 `> 0`）。

`.env.example` SHALL 在 `# --- ohMyStock runtime toggles ---` 區塊或新區塊 `# --- Confirm Gate v0 ---` 中新增兩行：
```
OHMYSTOCK_CONFIRM_TIMEOUT_MINUTES=30
OHMYSTOCK_DEFAULT_CAPITAL_TWD=1000000
```

#### Scenario: 預設值 — 不設 env 時等於文件預設
- **WHEN** 在無相關 env 的環境執行 `Settings()`
- **THEN** `s.ohmystock_confirm_timeout_minutes == 30` 且 `s.ohmystock_default_capital_twd == 1_000_000`

#### Scenario: env 覆寫 timeout
- **GIVEN** monkeypatch env `OHMYSTOCK_CONFIRM_TIMEOUT_MINUTES=60`
- **WHEN** 執行 `Settings()`
- **THEN** `s.ohmystock_confirm_timeout_minutes == 60`

#### Scenario: env 覆寫 default capital
- **GIVEN** monkeypatch env `OHMYSTOCK_DEFAULT_CAPITAL_TWD=2500000`
- **WHEN** 執行 `Settings()`
- **THEN** `s.ohmystock_default_capital_twd == 2_500_000`

#### Scenario: timeout ≤ 0 raise ValidationError
- **GIVEN** monkeypatch env `OHMYSTOCK_CONFIRM_TIMEOUT_MINUTES=0`
- **WHEN** 執行 `Settings()`
- **THEN** raise `pydantic.ValidationError`，message 含 `ohmystock_confirm_timeout_minutes`

#### Scenario: default_capital ≤ 0 raise ValidationError
- **GIVEN** monkeypatch env `OHMYSTOCK_DEFAULT_CAPITAL_TWD=-1`
- **WHEN** 執行 `Settings()`
- **THEN** raise `pydantic.ValidationError`，message 含 `ohmystock_default_capital_twd`

#### Scenario: `.env.example` 含兩個新 key
- **WHEN** 讀取 repo root 的 `.env.example`
- **THEN** 檔案內容含 `OHMYSTOCK_CONFIRM_TIMEOUT_MINUTES=30` 與 `OHMYSTOCK_DEFAULT_CAPITAL_TWD=1000000` 兩行（值為文件預設）
