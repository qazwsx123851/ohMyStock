## ADDED Requirements

### Requirement: Settings 欄位與 live-mode 衝突 validator

系統 SHALL 在 `ohmystock.config.settings.Settings` 增加以下欄位（皆為 env-overridable，預設值即為 cheatsheet §6.7 / safety §2.9 規定值）：

| 欄位 | 型別 | 預設 | 用途 |
|---|---|---|---|
| `OHMYSTOCK_AUTO_EXECUTE` | `bool` | `False` | 主開關；`True` 時 `try_auto_execute` 才會嘗試自動執行 |
| `OHMYSTOCK_AUTO_EXECUTE_DAILY_LIMIT` | `int` | `5` | 單日 LLM-decided 自動下單筆數上限 |
| `OHMYSTOCK_AUTO_EXECUTE_MIN_CONFIDENCE` | `float` | `0.7` | LLM `confidence` 最低門檻 |
| `OHMYSTOCK_AUTO_EXECUTE_MAX_NOTIONAL_PCT` | `float` | `0.25` | 單筆金額上限 = `account_equity_twd * pct` |
| `OHMYSTOCK_AUTO_EXECUTE_MAX_SIZING_DEVIATION` | `float` | `0.30` | `final_sizing_pct` 對 `system_sizing_pct` 的相對偏離上限；超過 → 自動 clamp |
| `OHMYSTOCK_AUTO_EXECUTE_LOSS_LOCKOUT_HOURS` | `int` | `24` | 連續 3 筆虧損超門檻後鎖定多少小時 |
| `OHMYSTOCK_AUTO_EXECUTE_LOSS_PCT_THRESHOLD` | `float` | `-0.05` | 連續虧損認定門檻（單筆 `realized_pnl_pct < threshold` 計入） |
| `OHMYSTOCK_AUTO_EXECUTE_ACCOUNT_EQUITY_TWD` | `int` | `1_000_000` | 用於 notional cap 的帳戶 equity（v0 stub；未來由 broker.account_balance 替代） |

系統 SHALL 在 `Settings` 增加 `model_validator(mode="after")` 名稱 `forbid_auto_execute_in_live`：若 `OHMYSTOCK_AUTO_EXECUTE` 為 `True` 且 `OHMYSTOCK_BROKER == "shioaji-live"` → raise `RuntimeError`，message 含 `"shioaji-live"` 與 `"OHMYSTOCK_AUTO_EXECUTE"` 字串。

#### Scenario: 預設值正確
- **WHEN** 以無相關 env 變數的環境建構 `Settings()`
- **THEN** `settings.OHMYSTOCK_AUTO_EXECUTE is False`、`settings.OHMYSTOCK_AUTO_EXECUTE_DAILY_LIMIT == 5`、`settings.OHMYSTOCK_AUTO_EXECUTE_MIN_CONFIDENCE == 0.7`、`settings.OHMYSTOCK_AUTO_EXECUTE_MAX_NOTIONAL_PCT == 0.25`、`settings.OHMYSTOCK_AUTO_EXECUTE_MAX_SIZING_DEVIATION == 0.30`

#### Scenario: live + auto_execute=true raise RuntimeError
- **GIVEN** env `OHMYSTOCK_BROKER=shioaji-live`、`OHMYSTOCK_AUTO_EXECUTE=true`、其他必要 live 變數齊備
- **WHEN** 建構 `Settings()`
- **THEN** raise `RuntimeError`，message 同時含 `"shioaji-live"` 與 `"OHMYSTOCK_AUTO_EXECUTE"` 字串

#### Scenario: sim + auto_execute=true 正常通過
- **GIVEN** env `OHMYSTOCK_BROKER=shioaji-sim`、`OHMYSTOCK_AUTO_EXECUTE=true`
- **WHEN** 建構 `Settings()`
- **THEN** 不 raise；`settings.OHMYSTOCK_AUTO_EXECUTE is True`

---

### Requirement: try_auto_execute 函式：對 pending_confirm entry 跑五道 breaker

系統 SHALL 在 `ohmystock.safety.auto_execute` 模組對外公開：

- `try_auto_execute(conn, *, decision_id, broker, settings, clock=system_clock) -> AutoExecuteResult`
- `AutoExecuteResult`：frozen dataclass `(decision_id: str, outcome: AutoExecuteOutcome, confirm_result: ConfirmResult | None, evidence: dict[str, Any])`
- `AutoExecuteOutcome`：`Literal["pass", "sizing_clamped_then_pass", "flag_off", "low_confidence", "daily_limit", "notional_limit", "loss_lockout", "live_broker"]`
- `AutoExecuteError`：例外，attribute `code: Literal["not_found","not_pending","payload_invalid","broker_failed","confirm_failed"]`、可選 `cause: Exception | None`

`try_auto_execute` 行為（依固定順序執行；前面任何 breaker 觸發 → 立即寫一筆 `kind=auto_execute_audit` 並 `return`，不呼叫 `confirm()`）：

1. **解析 entry**：`SELECT symbol, payload_json FROM journal_entries WHERE decision_id=? AND kind='entry' ORDER BY id DESC LIMIT 1`。若無 row → raise `AutoExecuteError(code="not_found")`。若 `payload.decision_status != "pending_confirm"` → raise `AutoExecuteError(code="not_pending")`。若 payload JSON 無法解析或缺 `llm_confidence`/`current_price`/`final_sizing_pct`/`stage` → raise `AutoExecuteError(code="payload_invalid")`。
2. **flag_off breaker**：若 `settings.OHMYSTOCK_AUTO_EXECUTE is False` → 寫 audit `outcome="flag_off"`，return `AutoExecuteResult(outcome="flag_off", confirm_result=None, evidence={"flag": False})`。
3. **live_broker breaker**：若 `settings.OHMYSTOCK_BROKER == "shioaji-live"` → 寫 audit `outcome="live_broker"`，return `AutoExecuteResult(outcome="live_broker", confirm_result=None, evidence={"broker_mode": "shioaji-live"})`。（即使 step 2 通過，這道仍是冗餘防線 — settings validator 已擋 `live + auto_execute=true` 組合，但 sim 模式被人為 mutate `OHMYSTOCK_BROKER` 也防得住）
4. **low_confidence breaker**：若 `payload.llm_confidence < settings.OHMYSTOCK_AUTO_EXECUTE_MIN_CONFIDENCE` → 寫 audit `outcome="low_confidence"`，evidence 含 `{"llm_confidence": <v>, "min_confidence": <threshold>}`，return。
5. **notional_limit breaker**：以 `_compute_qty(equity=settings.OHMYSTOCK_AUTO_EXECUTE_ACCOUNT_EQUITY_TWD, sizing_pct=payload.final_sizing_pct, current_price=payload.current_price)` 計算 `qty`（重用 confirm-gate `_compute_qty`），`notional_twd = qty * payload.current_price`；若 `notional_twd > settings.OHMYSTOCK_AUTO_EXECUTE_ACCOUNT_EQUITY_TWD * settings.OHMYSTOCK_AUTO_EXECUTE_MAX_NOTIONAL_PCT` → 寫 audit `outcome="notional_limit"`，evidence 含 `{"notional_twd": <v>, "max_notional_twd": <cap>}`，return。
6. **daily_limit breaker**：`SELECT count(*) FROM journal_entries WHERE kind='entry' AND json_extract(payload_json, '$.auto_executed')=1 AND json_extract(payload_json, '$.human_confirmed_at') >= ? AND json_extract(payload_json, '$.human_confirmed_at') < ?`，其中時間範圍為「今日 TPE 00:00:00+08:00」到 `clock.now_iso()`；若 count >= `settings.OHMYSTOCK_AUTO_EXECUTE_DAILY_LIMIT` → 寫 audit `outcome="daily_limit"`，evidence 含 `{"auto_today_count": <c>, "daily_limit": <l>}`，return。
7. **loss_lockout breaker**：`SELECT json_extract(payload_json, '$.realized_pnl_pct') AS pnl, json_extract(payload_json, '$.closed_at') AS closed FROM journal_entries WHERE kind='exit' AND json_extract(payload_json, '$.source')='auto' ORDER BY id DESC LIMIT 3`。若回傳少於 3 row → 不 trigger（pass through）。若三筆 `pnl < settings.OHMYSTOCK_AUTO_EXECUTE_LOSS_PCT_THRESHOLD`（皆是嚴重虧損），且最新一筆的 `closed_at + LOSS_LOCKOUT_HOURS > clock.now()` → 寫 audit `outcome="loss_lockout"`，evidence 含 `{"loss_streak_count": 3, "lockout_until": "<iso>"}`，return。
8. **sizing clamp**（**非** breaker）：`system_sizing_pct(stage)` = `10.0 if stage == 3 else 25.0`；`deviation = abs(payload.final_sizing_pct - system_sizing_pct) / system_sizing_pct`；若 `deviation > settings.OHMYSTOCK_AUTO_EXECUTE_MAX_SIZING_DEVIATION` → `clamped = min(payload.final_sizing_pct, system_sizing_pct)`，UPDATE 該 entry payload `final_sizing_pct = clamped`（在同一 SQLite 連線、無新 transaction），記下 `(raw_sizing_pct, clamped_sizing_pct, system_sizing_pct)`；標記 `outcome_label = "sizing_clamped_then_pass"`。否則 `outcome_label = "pass"`，無 mutation。
9. **執行 confirm**：呼叫 `confirm(conn, decision_id=decision_id, broker=broker, default_capital_twd=settings.OHMYSTOCK_AUTO_EXECUTE_ACCOUNT_EQUITY_TWD, user="auto", auto_executed=True, clock=clock)`。若 raise `ConfirmGateError` → raise `AutoExecuteError(code="confirm_failed", cause=e)`，**不**寫 audit row（confirm 自己已 rollback；audit 缺一筆優於 audit 不一致）。
10. **寫 audit row**（成功路徑）：`outcome=outcome_label`，evidence 含 `{"llm_confidence": <v>, "auto_today_count": <c+1>, "notional_twd": <v>, "system_sizing_pct": <v>, "raw_sizing_pct": <v>, "clamped_sizing_pct": <v if clamped else None>, "broker_mode": "<broker_mode>"}`。回 `AutoExecuteResult(outcome=outcome_label, confirm_result=<from step 9>, evidence=<same>)`。

每筆 audit row 的 `kind = "auto_execute_audit"`、`symbol = <entry symbol>`、`created_at = clock.now_iso()`、`payload_json` 為以下結構：

```json
{
  "decision_status": "auto_execute_audit",
  "outcome": "<one of 8 outcomes>",
  "decision_id_ref": "<decision_id>",
  "audit_at": "<clock.now_iso()>",
  "evidence": { ... outcome-specific keys ... }
}
```

`AutoExecuteError(code="not_found"|"not_pending"|"payload_invalid")` SHALL **不**寫 audit row（這些是呼叫者契約違反，不是業務 outcome）。

#### Scenario: flag_off → 寫 audit + 不呼叫 confirm
- **GIVEN** in-memory SQLite + `init_schema(conn)` + 一筆 pending_confirm entry `decision_id="dec_X"`，`settings.OHMYSTOCK_AUTO_EXECUTE = False`
- **WHEN** 呼叫 `try_auto_execute(conn, decision_id="dec_X", broker=FakePaperBroker(...), settings=settings, clock=...)`
- **THEN** 回 `AutoExecuteResult(outcome="flag_off", confirm_result=None, ...)`；DB 中 `SELECT count(*) FROM journal_entries WHERE kind='auto_execute_audit' AND decision_id=?` 為 1；該 row payload `outcome` 為 `"flag_off"`；entry row `decision_status` 仍為 `"pending_confirm"`

#### Scenario: live_broker → 寫 audit + 不呼叫 confirm
- **GIVEN** `settings.OHMYSTOCK_AUTO_EXECUTE = True`、`settings.OHMYSTOCK_BROKER = "shioaji-live"`（測試用 monkeypatch 跳過 settings validator）、pending entry 存在
- **WHEN** `try_auto_execute(...)`
- **THEN** 回 outcome `"live_broker"`；audit row 存在；entry 仍 pending

#### Scenario: low_confidence → 寫 audit + 不呼叫 confirm
- **GIVEN** `settings.OHMYSTOCK_AUTO_EXECUTE = True`、`settings.OHMYSTOCK_BROKER = "shioaji-sim"`、pending entry payload `llm_confidence=0.62`
- **WHEN** `try_auto_execute(...)`
- **THEN** 回 outcome `"low_confidence"`；audit row evidence 為 `{"llm_confidence": 0.62, "min_confidence": 0.7}`；entry 仍 pending

#### Scenario: notional_limit → 寫 audit + 不呼叫 confirm
- **GIVEN** pending entry payload `final_sizing_pct=25.0`、`current_price=832.0`，settings `account_equity_twd=1_000_000`、`max_notional_pct=0.20`（人為調低使 25% 觸發）
- **WHEN** `try_auto_execute(...)`
- **THEN** 回 outcome `"notional_limit"`；audit evidence 含 `notional_twd=250_000`、`max_notional_twd=200_000`；entry 仍 pending

#### Scenario: daily_limit → 寫 audit + 不呼叫 confirm
- **GIVEN** 今日 TPE 已有 5 筆 entry payload `auto_executed=true / human_confirmed_at` 落在 `[今日00:00, now]`，新一筆 pending entry `dec_Y` 進來；settings `daily_limit=5`
- **WHEN** `try_auto_execute(conn, decision_id="dec_Y", ...)`
- **THEN** 回 outcome `"daily_limit"`；audit evidence 含 `auto_today_count=5, daily_limit=5`；`dec_Y` entry 仍 pending

#### Scenario: loss_lockout → 寫 audit + 不呼叫 confirm
- **GIVEN** journal 中已有 3 筆 `kind=exit` row payload `source="auto"`、`realized_pnl_pct ∈ {-0.06, -0.07, -0.08}`，最新一筆 `closed_at="2026-05-02T09:00:00+08:00"`；`clock.now()="2026-05-02T15:00:00+08:00"`、settings `loss_lockout_hours=24`、pending entry 存在
- **WHEN** `try_auto_execute(...)`
- **THEN** 回 outcome `"loss_lockout"`；audit evidence 含 `loss_streak_count=3, lockout_until="2026-05-03T09:00:00+08:00"`；entry 仍 pending

#### Scenario: loss_lockout 不 trigger 當 exit 數量 < 3
- **GIVEN** journal 中只有 2 筆 `kind=exit source=auto` row（皆虧損 > 5%）；pending entry 存在；其他 breaker 通過；FakePaperBroker
- **WHEN** `try_auto_execute(...)`
- **THEN** 回 outcome `"pass"`（loss_lockout 沒 trigger，因為 streak 需要剛好 3 筆才算）；entry 變 confirmed

#### Scenario: pass → 呼叫 confirm 並寫 audit
- **GIVEN** 所有 breaker 通過（`auto_execute=True / sim / confidence=0.85 / notional 在限度 / daily count=0 / no losses`）、pending entry payload `final_sizing_pct=20.0 stage=2 current_price=832.0 atr_14_pct=2.85`、FakePaperBroker
- **WHEN** `try_auto_execute(...)`
- **THEN** 回 `AutoExecuteResult(outcome="pass", confirm_result=ConfirmResult(...), ...)`；entry row payload `decision_status="confirmed"` / `auto_executed=True` / `human_confirmed_by="auto"` / `actual_entry_price=832.0`；audit row 存在 outcome `"pass"`

#### Scenario: sizing_clamped_then_pass → clamp + 呼叫 confirm + 寫 audit
- **GIVEN** pending entry payload `final_sizing_pct=20.0 stage=3`（system_sizing_pct=10.0；deviation=(20-10)/10=1.0 > 0.30），其他 breaker 通過
- **WHEN** `try_auto_execute(...)`
- **THEN** entry payload `final_sizing_pct` 被 UPDATE 為 `10.0`（取 min）；confirm 用 clamped 值算 qty；回 outcome `"sizing_clamped_then_pass"`；audit evidence 含 `raw_sizing_pct=20.0 / clamped_sizing_pct=10.0 / system_sizing_pct=10.0`

#### Scenario: not_pending entry raise AutoExecuteError + 不寫 audit
- **GIVEN** entry 已被 confirmed
- **WHEN** 呼叫 `try_auto_execute(conn, decision_id=..., ...)`
- **THEN** raise `AutoExecuteError(code="not_pending")`；DB 中 `SELECT count(*) FROM journal_entries WHERE kind='auto_execute_audit' AND decision_id=?` 為 0

#### Scenario: not_found raise AutoExecuteError + 不寫 audit
- **WHEN** 呼叫 `try_auto_execute(conn, decision_id="dec_does_not_exist", ...)`
- **THEN** raise `AutoExecuteError(code="not_found")`；DB 無新 row

#### Scenario: payload 缺 stage raise payload_invalid + 不寫 audit
- **GIVEN** pending entry payload 缺 `stage` 欄位
- **WHEN** `try_auto_execute(...)`
- **THEN** raise `AutoExecuteError(code="payload_invalid")`，message 含 `"stage"`

#### Scenario: confirm raise BrokerError → AutoExecuteError(confirm_failed) + 不寫 audit
- **GIVEN** 所有 breaker 通過、broker = `FakePaperBroker(raise_on_submit=True)`
- **WHEN** `try_auto_execute(...)`
- **THEN** raise `AutoExecuteError(code="confirm_failed")`，`exc.cause` 為 `ConfirmGateError`；entry 仍 pending（confirm 內已 rollback）；audit row count 為 0

---

### Requirement: 模組對外 API 透過 `__init__.py` re-export

系統 SHALL 在 `src/ohmystock/safety/__init__.py` 額外 re-export `try_auto_execute`、`AutoExecuteResult`、`AutoExecuteOutcome`、`AutoExecuteError`，並保留先前 `confirm-gate-v0` 既有的 export 不變。

#### Scenario: 公開符號可從 ohmystock.safety import
- **WHEN** 執行 `from ohmystock.safety import try_auto_execute, AutoExecuteResult, AutoExecuteOutcome, AutoExecuteError`
- **THEN** import 成功；`AutoExecuteOutcome` 為 typing.Literal 而非 class；`try_auto_execute` 是 callable
