## MODIFIED Requirements

### Requirement: decide_entry 編排函式

系統 SHALL 提供 `ohmystock.decider.orchestrator.decide_entry(entry_input, *, conn, decider, clock=system_clock, decision_id_factory=default_decision_id) -> OrchestrationResult`，串接「LLM 呼叫 → 驗證 → journal write → llm_costs write」一次完成。

`OrchestrationResult`：dataclass `(decision_id: str, final: DeciderOutput, written_kind: Literal["entry","reject"], llm_cost: LLMCost, force_reject_reason: str | None)`。

`default_decision_id(entry_input)` SHALL 回 `f"dec_{entry_input.trigger_at.replace(':','-').replace('+08:00','')}_{entry_input.candidate.symbol}"`（與 `docs/llm-decision-schema.md` §1 範例對齊）。

行為：

1. 呼叫 `decider.decide(entry_input)` 取 `(raw, usage)`。若 raise `DeciderOutputParseError` → 寫一筆 `kind=reject`（reject_layer=llm，reject_reason `"json_parse_error: <exc.raw_text 截 500 字>"`），仍寫 `llm_costs`（若 `usage` 可取得；否則 `input_tokens=output_tokens=0, cost_usd=0.0`），並 re-raise。
2. 跑 `validate_decider_output(raw, entry_input.candidate)` 取 `vr`。
3. `vr.final_decision.decision == "enter"` → 寫 `kind=entry` payload 含 §4.1 全部欄位（`decision_status="pending_confirm"` / `auto_executed=false` / `human_confirmed_by=null` / `human_confirmed_at=null` / `final_sizing_pct=raw.proposed_sizing_pct`（暫等於 proposed，下一個 change 才會被 Sizing Service 改寫） / **`system_sizing_pct=10.0 if raw.stage == 3 else 25.0`**（新增；v0 stub 對應 §2.1 stage cap，未來改為 Volatility Targeting 公式輸出） / `stop_loss_price=null`（待 ATR Service 計算） / `atr_at_entry=null`（同前） / `risk_regime_at_entry=null`（待 Risk Gate 計算） / SEPA 五欄從 raw 拷貝），`written_kind="entry"`。
4. `vr.final_decision.decision == "reject"` → 寫 `kind=reject` payload 含 §4.3 欄位（`reject_layer="llm"` / `reject_reason=vr.force_reject_reason` / `decision_status="rejected"`），`written_kind="reject"`。
5. 寫一筆 `llm_costs`（`decision_id` / `model=usage.model` / `input_tokens=usage.input_tokens` / `output_tokens=usage.output_tokens` / `cost_usd=usage.cost_usd` / `created_at=clock.now_iso()`）。
6. 回 `OrchestrationResult(decision_id, vr.final_decision, written_kind, LLMCost(usage), vr.force_reject_reason)`。

整段 SHALL 在同一個 `conn.commit()` 之後 atomic 落盤（用 BEGIN/COMMIT 包起來）。若步驟 3/4/5 任一 raise → rollback 並 re-raise，`OrchestrationResult` 不回。

`system_sizing_pct` 為 entry payload 的新增欄位，型別 `float`，**僅** 在 `kind=entry` row 寫入；`kind=reject` row 的 payload 不含此欄位。寫入規則：`stage == 3` → `10.0`；其餘 stage（1, 2，stage 4 已被 `validate_decider_output` 強制 reject 不會走到此分支）→ `25.0`。此欄位由 `auto-execute` capability 的 sizing-deviation breaker 讀取使用；未來引入 Volatility Targeting 計算後，本欄位將改為該計算結果，本 spec 的數值規則自動失效（屆時 `decide_entry` 與 `validate_decider_output` 將共同更新）。

#### Scenario: enter 路徑寫一筆 journal_entries (kind=entry) + 一筆 llm_costs
- **GIVEN** 一個 in-memory SQLite conn 已跑過 `init_schema(conn)`、一個 fake decider 回合法 enter raw、`entry_input.candidate.symbol="2330"`
- **WHEN** 呼叫 `decide_entry(entry_input, conn=conn, decider=fake_decider, ...)`
- **THEN** `result.written_kind == "entry"` ；`SELECT count(*) FROM journal_entries WHERE kind='entry'` 為 1 ；`SELECT json_extract(payload_json, '$.decision_status') FROM journal_entries` 為 `'pending_confirm'` ；`SELECT count(*) FROM llm_costs` 為 1 且該 row 的 `decision_id` 等於 `result.decision_id`

#### Scenario: LLM 自願 reject 寫 kind=reject reject_layer=llm
- **GIVEN** fake decider 回合法但 `decision="reject" / confidence=0.4`
- **WHEN** `decide_entry(...)`
- **THEN** `result.written_kind == "reject"`、`result.force_reject_reason == "confidence_below_0_6"`；`SELECT json_extract(payload_json, '$.reject_layer') FROM journal_entries WHERE kind='reject'` 為 `'llm'`

#### Scenario: 系統覆寫導致 reject 也寫 kind=reject reject_layer=llm
- **GIVEN** fake decider 回 `decision="enter" / stage=4`，candidate `stage=4`
- **WHEN** `decide_entry(...)`
- **THEN** `result.written_kind == "reject"`、`result.force_reject_reason == "stage_4_excluded"`；journal 中該筆 `reject_reason` 為 `"stage_4_excluded"`

#### Scenario: DeciderOutputParseError 寫 reject 並 re-raise
- **GIVEN** fake decider 在被呼叫時 raise `DeciderOutputParseError(raw_text="i think...", cause=json.JSONDecodeError(...))`
- **WHEN** `decide_entry(...)`
- **THEN** raise `DeciderOutputParseError` ；DB 已寫一筆 `kind=reject` reject_reason 字串開頭為 `"json_parse_error:"` ；`llm_costs` 寫一筆 `input_tokens=0 / output_tokens=0 / cost_usd=0.0`

#### Scenario: 寫入失敗 rollback
- **GIVEN** monkeypatch `journal_writer` 在第 3 步寫 `kind=entry` 時 raise `sqlite3.IntegrityError`
- **WHEN** `decide_entry(...)`
- **THEN** raise `sqlite3.IntegrityError` ；`SELECT count(*) FROM journal_entries`、`SELECT count(*) FROM llm_costs` 均為 0（rollback 生效）

#### Scenario: stage=2 entry payload 寫 system_sizing_pct=25.0
- **GIVEN** fake decider 回合法 enter raw `stage=2 / proposed_sizing_pct=20.0`，candidate `stage=2`
- **WHEN** `decide_entry(...)`
- **THEN** `SELECT json_extract(payload_json, '$.system_sizing_pct') FROM journal_entries WHERE kind='entry'` 為 `25.0`

#### Scenario: stage=3 entry payload 寫 system_sizing_pct=10.0
- **GIVEN** fake decider 回合法 enter raw `stage=3 / proposed_sizing_pct=8.0`（≤ 10 不觸發 §2.1 cap），candidate `stage=3`
- **WHEN** `decide_entry(...)`
- **THEN** `SELECT json_extract(payload_json, '$.system_sizing_pct') FROM journal_entries WHERE kind='entry'` 為 `10.0`；`SELECT json_extract(payload_json, '$.final_sizing_pct') FROM journal_entries WHERE kind='entry'` 為 `8.0`（無 stage-3 cap 觸發）

#### Scenario: stage=3 sizing capped 後 system_sizing_pct 仍為 10.0
- **GIVEN** fake decider 回 `stage=3 / proposed_sizing_pct=18.0`（觸發 §2.1 stage-3 cap），candidate `stage=3`
- **WHEN** `decide_entry(...)`
- **THEN** `final_sizing_pct=10.0`（被 §2.1 cap）；`system_sizing_pct=10.0`；兩者相等代表此 entry 不會被 auto-execute sizing-clamp 觸發

#### Scenario: reject row 不含 system_sizing_pct 欄位
- **GIVEN** fake decider 回 `decision="reject"`
- **WHEN** `decide_entry(...)`
- **THEN** `written_kind="reject"`；`SELECT json_extract(payload_json, '$.system_sizing_pct') FROM journal_entries WHERE kind='reject'` 為 `NULL`（欄位不存在）
