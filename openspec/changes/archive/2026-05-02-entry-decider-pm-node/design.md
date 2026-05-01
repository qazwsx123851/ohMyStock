## Context

Phase 2B（archive `2026-05-01-phase-2b-swarm-input-assembler` 等）已能由 `ohmystock.swarm._input_assembler.assemble_entry_input(...)` 產出 `EntryInput`。Trade Journal schema（archive `2026-04-30-...` + `live-providers`）已備齊 `journal_entries`（FTS5）與 `llm_costs`。Cost tracker（`src/ohmystock/observability/cost_tracker.py`）已封裝 Anthropic SDK 計費；CLI（`src/ohmystock/cli/__init__.py`）已是 Typer app。

但 `src/ohmystock/decider/__init__.py` 仍是空檔。目前沒有任何模組會：

- 把 `EntryInput` 序列化成 LLM prompt
- 解析 LLM 回的 v3.1 JSON
- 套用 `docs/llm-decision-schema.md` §2.1 系統覆寫
- 寫 `kind=entry`（`decision_status=pending_confirm`）或 `kind=reject`（`reject_layer=llm`）

本 change 補上這條最短路徑。Confirm Gate / Sizing/ATR 覆寫 / Risk Gate / 多代理 swarm 留給後續 change。

## Goals / Non-Goals

**Goals:**
- 新模組 `ohmystock.decider`，對外公開 4 個符號：`PMConclusionNode`（Protocol）、`AnthropicPMConclusionNode`（預設實作）、`DeciderOutput`（Pydantic v3.1）、`decide_entry(...)`（編排）。
- §2.1 全部硬約束（11 條）由 `validator.validate_decider_output(...)` 一處實作，並由表格測試覆蓋每條規則的 pass / fail 邊界。
- Journal 寫入欄位形狀完全對齊 `docs/llm-decision-schema.md` §4.1（entry）/ §4.3（reject），不增不減。
- CLI `ohmystock decide <symbol>` 命令端到端可跑：`ohmystock decide 2330 --asof 2026-04-30 --json` → 印出 `DeciderOutput`（系統覆寫後）+ exit code (0 enter / 1 reject)。
- 單元測試可注入 `FakePMConclusionNode`，**不**呼叫真 Anthropic API；integration test 用 marker 區隔（沿用既有慣例）。

**Non-Goals:**
- ❌ 不實作 entry_decision_team multi-agent swarm 的 specialist 節點（technical / chip / fundamental / sentiment）。PM 結論節點假設 `EntryInput.candidate` 已含 final_score / sub-scores / SEPA 五欄，由 Phase 2B scoring engine 提供。
- ❌ 不實作 Sizing Service（Volatility Targeting）/ ATR Service / Risk Gate。`DeciderOutput.proposed_sizing_pct` 為 LLM 提案；最終 `system_calculated_sizing_pct` / `final_sizing_pct` / stop_loss / risk_gate_status 屬於下一個 change。
- ❌ 不實作 Confirm Gate（人工確認 / `OHMYSTOCK_AUTO_EXECUTE` 雙模式）。本 change 一律寫 `decision_status=pending_confirm`，由 Phase 3.5 補上實際 confirm 流程。
- ❌ 不寫 `kind=exit` / `kind=expire` / `kind=reject(reject_layer=pre_check)` / `kind=reject(reject_layer=risk_gate)`。本 change 只負責 `kind=entry` 與 `kind=reject(reject_layer=llm)`。
- ❌ 不引入 `claude-agent-sdk` runtime；只用 `anthropic` SDK 的 `messages.create()` 加 strict JSON system prompt 約束。

## Decisions

### D1. PM Conclusion Node 介面用 Protocol，不用 ABC

```python
class PMConclusionNode(Protocol):
    def decide(self, entry_input: EntryInput) -> tuple[DeciderOutput, LLMUsage]:
        ...
```

**理由**：測試只需要結構性子型別（duck typing）。Protocol 比 ABC 簡單；fake 實作不必 inherit。

**替代**：`abc.ABC + @abstractmethod`。被淘汰，理由是會讓 fake 實作多寫一行 inheritance、且不利於 `runtime_checkable` 之外的 type-check 場景。

### D2. LLM 輸出用 strict JSON system prompt + Pydantic 解析（不用 SDK tool calling）

`AnthropicPMConclusionNode.decide(...)` 流程：

1. `messages.create(model=..., system=SYSTEM_PROMPT, messages=[{"role":"user","content":json.dumps(entry_input.model_dump())}])`
2. 取 `response.content[0].text`
3. `json.loads(...)` → `DeciderOutput.model_validate(...)`
4. 取 `response.usage.input_tokens` / `response.usage.output_tokens`，計算 `cost_usd`（模型常數表：opus-4-7 `$15/MTok` input / `$75/MTok` output）
5. 回 `(DeciderOutput, LLMUsage)`

**理由**：v3.1 schema 已嚴格、欄位多；用 Anthropic 的 tool calling 反而要把整個 schema 翻成 JSON Schema 餵 SDK，且 SDK 的 strict mode 對 `oneOf` / `null`-able pivot_price 支援有限。直接 `messages.create` + Pydantic 解析最直接、最可測試（fake decider 直接 return Pydantic 物件即可）。

**替代**：Anthropic SDK 的 tool-use forced output。被淘汰，理由是 schema 翻譯成本與 v3.1 SEPA 5 欄的條件約束（`pivot_price` 與 `vcp_quality` 的相依）難以在 JSON Schema 直接表達。

### D3. §2.1 系統覆寫實作為 pure function

```python
def validate_decider_output(
    raw: DeciderOutput,
    candidate_snapshot: CandidateSnapshot,
) -> ValidationResult:
    ...
```

回傳 `ValidationResult(final_decision: DeciderOutput, force_reject_reason: str | None, applied_overrides: list[str])`。

`force_reject_reason` 為 `None` 表示 LLM 通過所有檢查；非 `None` 表示系統強制改為 `reject`，原因如 `confidence_below_0_6` / `must_have_failed:trend_template_8_of_8` / `bonus_score_below_4` / `stage_4_excluded` 等。

`applied_overrides` 紀錄被覆寫的欄位，例如 `stage_3_sizing_capped:18.0->10.0`。

**理由**：pure function 容易表格測試、容易在 orchestrator 中用 `if vr.force_reject_reason: write_reject(...)` 一個分支判斷。`candidate_snapshot` 是 input 的一部分，傳進來是因為某些 §2.1 規則（如 `rs_percentile < 65` 自動 fail `trend_template_8_of_8`）依賴 candidate 而非 LLM 自己宣告的數字 — 我們交叉驗證 LLM 回的 `rs_percentile` 必須 == candidate 的 `rs_percentile`，否則視為 LLM 拒絕（這條也算 §2.1 的隱含規則：「LLM 不可繞過」候選快照）。

**替代**：把驗證寫進 `DeciderOutput` 的 `model_validator(mode="after")`。被淘汰，理由是 §2.1 是「系統覆寫」而非「拒收」 — 不合格的 LLM 輸出**仍要落 journal**（作為 `kind=reject`），不能在 Pydantic 層拋 `ValidationError` 直接砍掉。

### D4. 編排 `decide_entry(entry_input, *, conn, decider, clock, decision_id_factory)`

```python
def decide_entry(
    entry_input: EntryInput,
    *,
    conn: sqlite3.Connection,
    decider: PMConclusionNode,
    clock: Clock = system_clock,
    decision_id_factory: Callable[[EntryInput], str] = default_decision_id,
) -> OrchestrationResult:
    ...
```

回傳 `OrchestrationResult(decision_id, final: DeciderOutput, written_kind: Literal["entry","reject"], llm_cost: LLMCost)`。

依賴皆為注入式（conn / decider / clock / id factory），便於 unit test 不接真 SQLite + 不呼叫真 LLM。`default_decision_id` 為 `f"dec_{trigger_at_iso_compact}_{symbol}"`（與 §1 example 對齊）。

**理由**：dependency injection 是既有 codebase 慣例（live providers / cost tracker 都是這樣寫）。

### D5. CLI `ohmystock decide <symbol>` 用既有 live providers 組裝 EntryInput

延續 archive `2026-05-01-live-providers` 與 `2026-04-30-screener-tw-universe` 的 pattern：CLI 命令接 `--symbol` / `--asof` / `--json` 三個旗標，內部呼叫 `assemble_entry_input(...)`（live providers）→ `decide_entry(...)`。實作位置 `src/ohmystock/cli/_decide.py`，由 `cli/__init__.py` 註冊。

**Exit codes**：
- `0` → `final.decision == "enter"`，已寫 `kind=entry` pending_confirm
- `1` → `final.decision == "reject"`，已寫 `kind=reject` reject_layer=llm
- `2` → `entry_input` 組裝失敗（candidate 不存在、live provider error 等）
- `3` → `decide_entry` 內部例外（如 LLM 連線失敗、JSON parse 失敗）

**理由**：與 `ohmystock score watchlist` 既有的 exit code 慣例（0 ok / 1 error）一致；多兩個碼是因為「reject」與「組裝失敗」是不同錯誤類別，自動化呼叫者要能分辨。

### D6. 模型成本表寫在常數模組

```python
# src/ohmystock/decider/_pricing.py
MODEL_PRICING_USD_PER_MTOK = {
    "claude-opus-4-7":   {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-6": {"input":  3.0, "output": 15.0},
    "claude-haiku-4-5":  {"input":  1.0, "output":  5.0},
}
```

未列入的 model 名稱呼叫 `compute_cost_usd(...)` 時 raise `KeyError`（明確錯誤勝於默默歸零）。

**替代**：吃 `cost-tracking` capability 的價目表。被淘汰，理由是該模組目前是 cost tracker 內部 detail；本 change 暫時自行管，後續若 cost-tracking 暴露 public API 再合併。

## Risks / Trade-offs

- **[LLM 不回合法 JSON 機率非零]** → `AnthropicPMConclusionNode.decide(...)` 在 `json.loads` / `model_validate` 失敗時 raise `DeciderOutputParseError`；orchestrator 捕到後寫一筆 `kind=reject`（reject_layer=llm，reject_reason 含 "json_parse_error" + 原始 raw_text 截斷至 500 字元）並回 exit code 3。**不**重試 — 重試由人工或上層流程決定。
- **[LLM 自報 candidate 數字與 EntryInput 不符]** → §2.1 D3 中提到「交叉驗證 LLM 的 stage / rs_percentile / trend_template_passed / vcp_quality / pivot_price 必須與 candidate 一致」。若不一致，視為 force_reject，原因 `llm_diverged_from_candidate:<field>`。LLM 可能會自行更動數字以求進場，這是必須擋的攻擊面。
- **[Pricing 表過時]** → 模型費率每幾個月會調整。常數表寫在 codebase 內，需要人工更新。風險 acceptable，因為 LLM 成本本身不是熱路徑指標；月底對 Anthropic 帳單時若有偏差再校正即可。
- **[Confirm Gate 尚未實作，pending_confirm 紀錄會永遠卡住]** → 本 change 階段 acceptable：`kind=entry` 在 `decision_status=pending_confirm` 不會自動轉成 `confirmed`，也不會送 broker；下一個 change 補完 Confirm Gate 流程。但要在 README / CLI help 寫清楚「目前只跑到 pending_confirm，不會下單」。
- **[`fake://` model 名稱與 OHMYSTOCK_DECIDER_MODEL 共用一個 env var 容易誤用]** → 在 production 環境若不小心設成 `fake://something`，AnthropicPMConclusionNode 會 raise；CLI 啟動前檢查 `decider_model` 不以 `fake://` 開頭，否則拒絕（除非 `OHMYSTOCK_ALLOW_FAKE_DECIDER=true`，僅供測試）。

## Migration Plan

無需 data migration（既有 schema 不動）。Roll-out 順序：

1. 合 PR → 跑 `make test`
2. 在本機 `.env` 設好 `ANTHROPIC_API_KEY`、`OHMYSTOCK_DECIDER_MODEL=claude-opus-4-7`
3. 手動跑一次 `ohmystock decide 2330 --asof 2026-04-30 --json`，確認真實 LLM 回應通過 §2.1 驗證並寫進 journal
4. 若 LLM 回應結構與 v3.1 schema 偏差，先記到 `docs/llm-decision-schema.md` 的 §6 演進條目，再決定是 prompt 工程修還是 schema 加欄位

回滾：移除 `decide` CLI 註冊與 `decider/` 模組即可；journal 中已寫的 `kind=entry`/`kind=reject` 是合法歷史紀錄，不必清理。

## Open Questions

1. **prompt language**：system prompt 用中文還是英文？候選資料、規則摘要本身是中文（cheatsheet 是中文），LLM 回的 reasoning 也需要中文（依 §2.1 reasoning ≥ 200 字以中文計）。**初步決定**：system prompt 用英文（指令類），但要求 LLM 用繁體中文寫 `reasoning`，且 cited_skills / decision enum 等結構欄位用英文。
2. **token 上限**：opus-4-7 有 1M context，但單筆 EntryInput 預估 8–15K tokens、reasoning 上限 ~2K tokens。`max_tokens` 設 4096 應足夠。**初步決定**：`max_tokens=4096`，後續若被截斷再上調。
3. **prompt cache**：是否在 system prompt 部分啟用 Anthropic prompt caching？省 ~50% input 成本。**初步決定**：本 change 先**不**啟用，等 LLM 結構穩定再加（避免 caching key 漂移做白工）。後續用 `claude-api` skill 引導加上。
