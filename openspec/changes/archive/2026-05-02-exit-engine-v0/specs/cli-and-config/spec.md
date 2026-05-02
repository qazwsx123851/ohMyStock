## ADDED Requirements

### Requirement: `ohmystock evaluate-exits` 子命令

系統 SHALL 在 `ohmystock` CLI 註冊 `evaluate-exits` 子命令，包裝 `exit-engine` capability 的 `evaluate_open_positions(...)`，讓 solo dev 可在每日盤後 close 一輪：對所有 confirmed entry 評估三條 v0 出場條件，將觸發者寫成 `kind=exit` row 並翻 entry status 為 `closed`。

子命令 SHALL 支援以下旗標：

| 旗標 | 必填 | 行為 |
|---|---|---|
| `--asof YYYY-MM-DD` | 必填 | 評估的交易日（用於 lookup close price 與計算 hold_days） |
| `--symbol XXXX` | 選填 | 限定評估單一 symbol（用於人工 spot-check） |
| `--price FLOAT` | 選填 | 覆寫 market_data lookup 的 close 價（**只能與 `--symbol` 一起用**） |
| `--db PATH` | 選填 | SQLite 路徑；預設讀 `OHMYSTOCK_DB_PATH` |
| `--json` | 選填 | 將結構化結果以 JSON 印至 stdout |

子命令 SHALL 在執行任何寫入前呼叫 `init_schema(conn)` 確保表存在（idempotent）。

子命令 SHALL 用 `ohmystock.swarm._live_market` 模組的 close-price lookup 作為預設 `MarketDataLookup` 實作（同 `ohmystock decide` 的 live provider chain），除非 `--price` 旗標 override。

子命令 root help SHALL 含字面 `kind=exit`、`closed`、`hit_stop_loss`、`hit_t1`、`time_stop` 字串，以提示用戶其影響的 lifecycle 狀態與 v0 三標籤。

**Exit codes：**
- `0` — 評估完成（不論 close 多少筆，含 0 筆）
- `2` — usage error（缺 `--asof`、`--asof` 非合法日期、`--price` 未配 `--symbol`）
- `3` — `ExitEngineError(code="market_data_unavailable")` 或其他 engine 層錯誤；stderr 列失敗 symbol

#### Scenario: `ohmystock evaluate-exits --help` 列旗標與 lifecycle 字串
- **WHEN** 執行 `uv run ohmystock evaluate-exits --help`
- **THEN** stdout 含 `--asof`、`--symbol`、`--price`、`--db`、`--json` 字串；含字面 `kind=exit`、`closed`、`hit_stop_loss`、`hit_t1`、`time_stop`

#### Scenario: 缺 --asof exit 2
- **WHEN** 執行 `uv run ohmystock evaluate-exits`
- **THEN** 命令以 exit code 2 結束（Typer usage error）

#### Scenario: --asof 非合法日期 exit 2
- **WHEN** 執行 `uv run ohmystock evaluate-exits --asof "not-a-date"`
- **THEN** 命令以 exit code 2 結束，stderr 含 `asof` 或 `date` 字串

#### Scenario: --price 未配 --symbol exit 2
- **WHEN** 執行 `uv run ohmystock evaluate-exits --asof 2026-05-07 --price 900.0`
- **THEN** 命令以 exit code 2 結束，stderr 含 `--price` 與 `--symbol` 字串（要求兩者同時提供）

#### Scenario: --symbol 與 --price 一起 — close 觸 T1 exit 0
- **GIVEN** in-memory test DB 有一筆 confirmed entry `symbol="2330"`、`actual_entry_price=832.0`、`stop_loss_price=784.58`，monkeypatch `evaluate_open_positions` 回 `[ExitResult(decision_id="dec_X", action="closed", decision=ExitDecision(exit_tag="hit_t1", actual_exit_price=900.0, pnl_pct=8.17, hold_days=5, exit_reason="..."))]`
- **WHEN** 執行 `uv run ohmystock evaluate-exits --asof 2026-05-07 --symbol 2330 --price 900.0`
- **THEN** 命令以 exit code 0 結束，stdout 含 `dec_X`、`hit_t1`、`closed`、`8.17`

#### Scenario: 評估完成但 0 筆 close exit 0
- **GIVEN** monkeypatch `evaluate_open_positions` 回 `[]`
- **WHEN** 執行 `uv run ohmystock evaluate-exits --asof 2026-05-07`
- **THEN** 命令以 exit code 0 結束，stdout 含 `0 closed` 或等價字串

#### Scenario: 多筆 entry，一筆 close、一筆 held
- **GIVEN** monkeypatch `evaluate_open_positions` 回 兩筆 ExitResult（一筆 closed、一筆 held）
- **WHEN** 執行 `uv run ohmystock evaluate-exits --asof 2026-05-07`
- **THEN** 命令以 exit code 0 結束，stdout 兩行（含 closed 與 held 各一）

#### Scenario: market_data lookup 失敗 exit 3
- **GIVEN** monkeypatch `evaluate_open_positions` raise `ExitEngineError(code="market_data_unavailable", failed_symbols=["2317"])`
- **WHEN** 執行 `uv run ohmystock evaluate-exits --asof 2026-05-07`
- **THEN** 命令以 exit code 3 結束，stderr 含 `market_data_unavailable` 與 `2317`

#### Scenario: `--json` 路徑回合法 JSON list
- **GIVEN** 同 hit_t1 GIVEN
- **WHEN** 執行 `uv run ohmystock evaluate-exits --asof 2026-05-07 --symbol 2330 --price 900.0 --json`
- **THEN** stdout 為合法 JSON，`json.loads` 後為 dict 含 keys：`asof`、`evaluated`（list[dict]）、`exit_code`；list 元素含 `decision_id`、`action`、`exit_tag`、`actual_exit_price`、`pnl_pct`、`hold_days`
