## ADDED Requirements

### Requirement: PMConclusionNode 介面與 Anthropic 預設實作

系統 SHALL 在 `ohmystock.decider` 模組對外公開以下符號：

- `PMConclusionNode`：Protocol，唯一方法 `decide(entry_input: EntryInput) -> tuple[DeciderOutput, LLMUsage]`。
- `AnthropicPMConclusionNode`：預設實作，`__init__(client, model: str, max_tokens: int = 4096)`，使用 `anthropic` SDK 的 `messages.create()` 呼叫設定的 model 並解析 JSON 回應。
- `LLMUsage`：dataclass `(input_tokens: int, output_tokens: int, cost_usd: float, model: str)`。
- `DeciderOutputParseError`：例外，當 LLM 回的文字無法 `json.loads` 或 `DeciderOutput.model_validate` 時 raise，attribute 含 `raw_text: str`（截斷至 500 字元）與 `cause: Exception`。

`AnthropicPMConclusionNode.decide(...)` 流程 SHALL 為：構建 `system` 與 `user` message → 呼叫 `client.messages.create(model=self.model, system=SYSTEM_PROMPT, max_tokens=self.max_tokens, messages=[...])` → 取 `response.content[0].text` → `json.loads` → `DeciderOutput.model_validate` → 計算 `cost_usd` → 回 `(output, LLMUsage)`。

#### Scenario: AnthropicPMConclusionNode 正常路徑回 (DeciderOutput, LLMUsage)
- **GIVEN** 一個 mock anthropic client，`messages.create(...)` 回 `MagicMock(content=[MagicMock(text=valid_json_str)], usage=MagicMock(input_tokens=18420, output_tokens=1240))`，其中 `valid_json_str` 是符合 v3.1 schema 的 enter 決策 JSON
- **WHEN** 呼叫 `AnthropicPMConclusionNode(client, "claude-opus-4-7").decide(entry_input)`
- **THEN** 回傳的 tuple 第一個元素是 `DeciderOutput` 實例，`decision == "enter"`；第二個元素是 `LLMUsage(input_tokens=18420, output_tokens=1240, cost_usd=≈0.3693, model="claude-opus-4-7")`（cost = 18420/1e6 × $15 + 1240/1e6 × $75）

#### Scenario: 非 JSON 文字 raise DeciderOutputParseError
- **GIVEN** mock client 回 `text="I think we should enter, the chart looks good"`（非 JSON）
- **WHEN** 呼叫 `AnthropicPMConclusionNode.decide(entry_input)`
- **THEN** raise `DeciderOutputParseError`，`exc.raw_text` 為該字串，`isinstance(exc.cause, json.JSONDecodeError)` 為 True

#### Scenario: JSON 但欄位缺少 raise DeciderOutputParseError
- **GIVEN** mock client 回 `text='{"decision":"enter","confidence":0.8}'`（缺 must_have_check 等欄位）
- **WHEN** 呼叫 `AnthropicPMConclusionNode.decide(entry_input)`
- **THEN** raise `DeciderOutputParseError`，`isinstance(exc.cause, ValidationError)` 為 True

#### Scenario: 未知 model 計算成本 raise KeyError
- **WHEN** 呼叫 `AnthropicPMConclusionNode(client, "claude-fake-99").decide(entry_input)` 且 mock 回合法 JSON
- **THEN** raise `KeyError`，message 含 `"claude-fake-99"`

---

### Requirement: DeciderOutput Pydantic 模型對齊 v3.1 schema

系統 SHALL 提供 `ohmystock.decider.models.DeciderOutput` Pydantic 模型，欄位與型別 SHALL 完全對應 `docs/llm-decision-schema.md` §2 v3.1 範例：

| 欄位 | 型別 | 約束（pydantic 層） |
|---|---|---|
| `output_schema_version` | `Literal["v3.1"]` | 嚴格 |
| `decision_id` | `str` | 非空 |
| `decided_at` | `str` | ISO-8601 with `+08:00` |
| `model` | `str` | 非空 |
| `decision` | `Literal["enter","reject","reduce_size"]` | 嚴格 |
| `confidence` | `float` | `ge=0.0, le=1.0` |
| `stage` | `Literal[1,2,3,4]` | 嚴格 |
| `rs_percentile` | `int` | `ge=0, le=99` |
| `trend_template_passed` | `int` | `ge=0, le=8` |
| `vcp_quality` | `Literal["none","forming","textbook","breakout"]` | 嚴格 |
| `pivot_price` | `float \| None` | model_validator 檢查 vcp_quality 不變式 |
| `must_have_check` | `list[MustHaveCheck]` | exactly 3 items |
| `bonus_score` | `int` | `ge=0, le=8` |
| `bonus_breakdown` | `list[BonusBreakdown]` | （長度由 prompt 約定，模型不強制） |
| `proposed_sizing_pct` | `float` | `ge=0.0, le=25.0` |
| `expected_holding_days` | `int` | `ge=1, le=30` |
| `reasoning` | `str` | （長度由 validator 強制，pydantic 不強制） |
| `cited_skills` | `list[str]` | 非空 list |
| `invalidation_conditions` | `list[str]` | 可空 |
| `risk_flags` | `list[str]` | 可空 |
| `tool_calls_summary` | `list[ToolCallSummary]` | 可空 |

`MustHaveCheck`：`{name: str, pass: bool, evidence: str}`；`BonusBreakdown`：`{name: str, pass: bool, evidence: str}`；`ToolCallSummary`：`{tool: str, action: str, elapsed_ms: int}`。

模型 SHALL 使用 `extra="forbid"` config，未知欄位拒收。`pivot_price` 不變式：`vcp_quality ∈ {textbook, breakout}` ↔ `pivot_price` 必為正 float；其餘 → 必為 `None`。

#### Scenario: 完整 v3.1 範例可被 model_validate
- **WHEN** 把 `docs/llm-decision-schema.md` §2 中的範例 JSON（去掉 reasoning 縮寫）餵進 `DeciderOutput.model_validate(...)`
- **THEN** 成功建構，`output.decision == "enter"`、`output.stage == 2`、`output.pivot_price == 832.0`

#### Scenario: pivot_price 不變式違反 raise ValidationError
- **GIVEN** 一個 JSON 物件 `vcp_quality="forming"` 但 `pivot_price=820.0`
- **WHEN** `DeciderOutput.model_validate(json_obj)`
- **THEN** raise `pydantic.ValidationError`，error message 含 `pivot_price` / `vcp_quality`

#### Scenario: must_have_check 不是 3 個 raise ValidationError
- **GIVEN** 一個 JSON 物件 `must_have_check` 為長度 2 的 list
- **WHEN** `DeciderOutput.model_validate(json_obj)`
- **THEN** raise `pydantic.ValidationError`

#### Scenario: 未知欄位拒收
- **GIVEN** 一個 JSON 物件含合法欄位 + 額外 `"foo":"bar"`
- **WHEN** `DeciderOutput.model_validate(json_obj)`
- **THEN** raise `pydantic.ValidationError`，error 提及 `extra` / `foo`

---

### Requirement: validate_decider_output 系統覆寫驗證器

系統 SHALL 提供 `ohmystock.decider.validator.validate_decider_output(raw: DeciderOutput, candidate: CandidateSnapshot) -> ValidationResult` pure function，依 `docs/llm-decision-schema.md` §2.1 套用所有硬約束。

`ValidationResult`：dataclass `(final_decision: DeciderOutput, force_reject_reason: str | None, applied_overrides: list[str])`。

驗證規則 SHALL 依以下順序執行（先觸發者決定 reject reason）：

1. `confidence < 0.6` → `force_reject_reason="confidence_below_0_6"`
2. `len(reasoning) < 200`（依 unicode 字元計數，不是 byte）→ `"reasoning_too_short:<n>"`
3. `len(cited_skills) == 0` → `"cited_skills_empty"`
4. `expected_holding_days ∉ [1, 30]` → `"holding_days_out_of_range:<v>"`（pydantic 已擋，但 validator 仍 defensive 檢查）
5. `proposed_sizing_pct ∉ [0.0, 25.0]` → `"sizing_out_of_range:<v>"`
6. `stage == 4` → `"stage_4_excluded"`
7. **Candidate 一致性**：`raw.stage != candidate.stage` 或 `raw.rs_percentile != candidate.rs_percentile` 或 `raw.trend_template_passed != candidate.trend_template_passed` 或 `raw.vcp_quality != candidate.vcp_quality` 或 `raw.pivot_price != candidate.pivot_price` → `"llm_diverged_from_candidate:<field>"`
8. **must_have name 集合**：必須恰為 `{"trend_template_8_of_8", "stage_2_confirmed", "vcp_pivot_breakout_with_volume"}`；不符 → `"must_have_names_invalid"`
9. **must_have 自動 fail**：依 candidate 數值套用 §2.1 自動 fail：
   - `candidate.rs_percentile < 65` 或 `candidate.trend_template_passed < 8` → `trend_template_8_of_8.pass` 視為 False（即使 LLM 說 True）
   - `candidate.vcp_quality ∈ {none, forming}` → `vcp_pivot_breakout_with_volume.pass` 視為 False
10. **must_have 任一 fail（含自動 fail）**：→ `"must_have_failed:<name>"`
11. `bonus_score < 4` → `"bonus_score_below_4:<v>"`

通過全部 1–11 後再執行 sizing cap：

12. `stage == 3` 且 `proposed_sizing_pct > 10.0` → 把 `final_decision.proposed_sizing_pct` 設為 `10.0`，並 `applied_overrides.append("stage_3_sizing_capped:<orig>->10.0")`。**不** force_reject。

若觸發 1–11 任一條，`final_decision` SHALL 為複製 raw 但將 `decision` 改為 `"reject"`、`confidence` 維持原值、其他欄位不動；`applied_overrides` SHALL 記錄 `"force_rejected:<reason>"`。

#### Scenario: 全部通過的 enter 直通
- **GIVEN** raw 為合法 enter 決策（confidence=0.83 / reasoning 250 字 / cited_skills 7 項 / stage=2 / rs_percentile=87 / trend_template_passed=8 / vcp_quality=breakout / pivot_price=832.0 / bonus_score=6 / proposed_sizing_pct=18.0），candidate 數值與 raw 完全一致
- **WHEN** `validate_decider_output(raw, candidate)`
- **THEN** `result.force_reject_reason is None`，`result.final_decision.decision == "enter"`，`result.applied_overrides == []`

#### Scenario: confidence 0.55 強制 reject
- **GIVEN** raw `confidence=0.55`，其餘合法
- **WHEN** `validate_decider_output(raw, candidate)`
- **THEN** `result.force_reject_reason == "confidence_below_0_6"`，`result.final_decision.decision == "reject"`，`result.final_decision.confidence == 0.55`（confidence 維持，方便復盤）

#### Scenario: stage=4 強制 reject
- **GIVEN** raw `stage=4` 且 candidate `stage=4`，其餘 LLM 自報合法
- **WHEN** `validate_decider_output(raw, candidate)`
- **THEN** `result.force_reject_reason == "stage_4_excluded"`

#### Scenario: stage=3 sizing 被 cap 至 10
- **GIVEN** raw `stage=3 / proposed_sizing_pct=18.0`，其餘合法且通過 must_have / bonus
- **WHEN** `validate_decider_output(raw, candidate)`
- **THEN** `result.force_reject_reason is None`，`result.final_decision.proposed_sizing_pct == 10.0`，`result.applied_overrides` 含 `"stage_3_sizing_capped:18.0->10.0"` 字面值

#### Scenario: candidate 數字不一致 → diverged
- **GIVEN** raw `rs_percentile=90`，candidate `rs_percentile=87`
- **WHEN** `validate_decider_output(raw, candidate)`
- **THEN** `result.force_reject_reason == "llm_diverged_from_candidate:rs_percentile"`

#### Scenario: rs_percentile 60 自動 fail trend_template
- **GIVEN** raw 中 `must_have_check[0]={name:"trend_template_8_of_8", pass:True, ...}`、`stage=2`、其他欄位合法；candidate `rs_percentile=60`、其他與 raw 一致
- **WHEN** `validate_decider_output(raw, candidate)`
- **THEN** `result.force_reject_reason == "must_have_failed:trend_template_8_of_8"`

#### Scenario: vcp_quality=forming 自動 fail vcp 第三柱
- **GIVEN** raw `vcp_quality="forming" / pivot_price=null`、candidate 一致；must_have 第三項 LLM 寫 pass=True
- **WHEN** `validate_decider_output(raw, candidate)`
- **THEN** `result.force_reject_reason == "must_have_failed:vcp_pivot_breakout_with_volume"`

#### Scenario: bonus_score 3 強制 reject
- **GIVEN** raw `bonus_score=3`，其餘合法
- **WHEN** `validate_decider_output(raw, candidate)`
- **THEN** `result.force_reject_reason == "bonus_score_below_4:3"`

#### Scenario: reasoning 短於 200 字強制 reject
- **GIVEN** raw `reasoning` 長度 100 字元，其餘合法
- **WHEN** `validate_decider_output(raw, candidate)`
- **THEN** `result.force_reject_reason == "reasoning_too_short:100"`

#### Scenario: must_have name 集合不對
- **GIVEN** raw `must_have_check[0].name == "old_v3_0_name"`（非 v3.1 三柱之一）
- **WHEN** `validate_decider_output(raw, candidate)`
- **THEN** `result.force_reject_reason == "must_have_names_invalid"`

---

### Requirement: decide_entry 編排函式

系統 SHALL 提供 `ohmystock.decider.orchestrator.decide_entry(entry_input, *, conn, decider, clock=system_clock, decision_id_factory=default_decision_id) -> OrchestrationResult`，串接「LLM 呼叫 → 驗證 → journal write → llm_costs write」一次完成。

`OrchestrationResult`：dataclass `(decision_id: str, final: DeciderOutput, written_kind: Literal["entry","reject"], llm_cost: LLMCost, force_reject_reason: str | None)`。

`default_decision_id(entry_input)` SHALL 回 `f"dec_{entry_input.trigger_at.replace(':','-').replace('+08:00','')}_{entry_input.candidate.symbol}"`（與 `docs/llm-decision-schema.md` §1 範例對齊）。

行為：

1. 呼叫 `decider.decide(entry_input)` 取 `(raw, usage)`。若 raise `DeciderOutputParseError` → 寫一筆 `kind=reject`（reject_layer=llm，reject_reason `"json_parse_error: <exc.raw_text 截 500 字>"`），仍寫 `llm_costs`（若 `usage` 可取得；否則 `input_tokens=output_tokens=0, cost_usd=0.0`），並 re-raise。
2. 跑 `validate_decider_output(raw, entry_input.candidate)` 取 `vr`。
3. `vr.final_decision.decision == "enter"` → 寫 `kind=entry` payload 含 §4.1 全部欄位（`decision_status="pending_confirm"` / `auto_executed=false` / `human_confirmed_by=null` / `human_confirmed_at=null` / `final_sizing_pct=raw.proposed_sizing_pct`（暫等於 proposed，下一個 change 才會被 Sizing Service 改寫） / `stop_loss_price=null`（待 ATR Service 計算） / `atr_at_entry=null`（同前） / `risk_regime_at_entry=null`（待 Risk Gate 計算） / SEPA 五欄從 raw 拷貝），`written_kind="entry"`。
4. `vr.final_decision.decision == "reject"` → 寫 `kind=reject` payload 含 §4.3 欄位（`reject_layer="llm"` / `reject_reason=vr.force_reject_reason` / `decision_status="rejected"`），`written_kind="reject"`。
5. 寫一筆 `llm_costs`（`decision_id` / `model=usage.model` / `input_tokens=usage.input_tokens` / `output_tokens=usage.output_tokens` / `cost_usd=usage.cost_usd` / `created_at=clock.now_iso()`）。
6. 回 `OrchestrationResult(decision_id, vr.final_decision, written_kind, LLMCost(usage), vr.force_reject_reason)`。

整段 SHALL 在同一個 `conn.commit()` 之後 atomic 落盤（用 BEGIN/COMMIT 包起來）。若步驟 3/4/5 任一 raise → rollback 並 re-raise，`OrchestrationResult` 不回。

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

---

### Requirement: 模型成本表

系統 SHALL 提供 `ohmystock.decider._pricing.MODEL_PRICING_USD_PER_MTOK` dict，並提供 `compute_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float` helper，公式為 `input_tokens / 1_000_000 * input_rate + output_tokens / 1_000_000 * output_rate`。

`MODEL_PRICING_USD_PER_MTOK` SHALL 至少包含三個 key：`claude-opus-4-7`（input=15.0, output=75.0）、`claude-sonnet-4-6`（input=3.0, output=15.0）、`claude-haiku-4-5`（input=1.0, output=5.0）。

未列入的 model 名稱 SHALL raise `KeyError`。

#### Scenario: opus 計費精確
- **WHEN** `compute_cost_usd("claude-opus-4-7", 18420, 1240)`
- **THEN** 回傳值 == `18420 / 1_000_000 * 15.0 + 1240 / 1_000_000 * 75.0`（即 `0.36930` ± 1e-9）

#### Scenario: 未知 model raise KeyError
- **WHEN** `compute_cost_usd("claude-fake-99", 100, 50)`
- **THEN** raise `KeyError`，message 含 `"claude-fake-99"`
