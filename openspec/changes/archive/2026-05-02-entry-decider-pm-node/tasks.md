## 1. Decider 模組骨架與 Pydantic 模型

- [x] 1.1 在 `src/ohmystock/decider/` 建檔：`__init__.py`（re-export public API）、`models.py`、`_pricing.py`、`node.py`、`validator.py`、`orchestrator.py`、`_journal_writer.py`
- [x] 1.2 在 `src/ohmystock/decider/models.py` 定義 `MustHaveCheck` / `BonusBreakdown` / `ToolCallSummary` / `DeciderOutput` Pydantic 模型，含 `extra="forbid"` 與 v3.1 欄位（含 SEPA 五欄）+ `pivot_price` 不變式 model_validator
- [x] 1.3 在 `tests/test_decider_models.py` 寫 `DeciderOutput` 的 happy-path（解析 `docs/llm-decision-schema.md` §2 範例）+ 失敗案例（pivot_price 不變式違反、must_have_check 長度不對、未知欄位）
- [x] 1.4 在 `src/ohmystock/decider/_pricing.py` 寫 `MODEL_PRICING_USD_PER_MTOK` dict（opus / sonnet / haiku 三 key）+ `compute_cost_usd(...)` helper
- [x] 1.5 在 `tests/test_decider_pricing.py` 測 `compute_cost_usd("claude-opus-4-7", 18420, 1240)` 等於 `0.36930`、未知 model 拋 KeyError

## 2. PMConclusionNode 介面與 Anthropic 預設實作

- [x] 2.1 在 `src/ohmystock/decider/node.py` 定義 `PMConclusionNode` Protocol、`LLMUsage` dataclass、`DeciderOutputParseError` 例外
- [x] 2.2 在同檔實作 `AnthropicPMConclusionNode`：`__init__(client, model, max_tokens=4096)`，`decide(entry_input)` 串 `messages.create` → 解析 JSON → 計算 cost → 回 `(DeciderOutput, LLMUsage)`
- [x] 2.3 在同檔定義 `SYSTEM_PROMPT` 字串：英文指令、要求 strict JSON 輸出、reasoning 用繁體中文、含 v3.1 欄位 schema 摘要、cite §2.1 約束
- [x] 2.4 在 `tests/test_decider_node.py` 寫 mock anthropic client 測：正常路徑回 `(DeciderOutput, LLMUsage)` 且 cost_usd 計算正確；非 JSON 文字 raise `DeciderOutputParseError(cause=JSONDecodeError)`；缺欄位 raise `DeciderOutputParseError(cause=ValidationError)`；未知 model raise `KeyError`
- [x] 2.5 在同檔加 `FakePMConclusionNode`（test fixture，回固定 `DeciderOutput`），用於後續 orchestrator / CLI 測試

## 3. validate_decider_output 系統覆寫驗證器

- [x] 3.1 在 `src/ohmystock/decider/validator.py` 定義 `ValidationResult` dataclass `(final_decision, force_reject_reason, applied_overrides)`
- [x] 3.2 在同檔實作 `validate_decider_output(raw, candidate)`，依 spec §2.1 的 11 條規則 + sizing cap (rule 12) 順序執行
- [x] 3.3 在 `tests/test_decider_validator.py` 用 pytest parametrize 為每條規則寫 pass / fail 邊界案例（至少 11 個案例）
- [x] 3.4 額外加表格測試：candidate 一致性（rs_percentile / stage / trend_template_passed / vcp_quality / pivot_price 各自不一致）、rs_percentile=64 vs 65 邊界、bonus_score=3 vs 4 邊界、reasoning 199 vs 200 字元邊界（unicode 字元，含中文）

## 4. journal writer + orchestrator

- [x] 4.1 在 `src/ohmystock/decider/_journal_writer.py` 寫 `write_entry_pending_confirm(conn, decision_id, entry_input, raw, usage)` 與 `write_reject_llm(conn, decision_id, entry_input, raw_or_none, usage_or_none, reject_reason, applied_overrides)` 兩個 helper，payload 形狀對齊 trade-journal-schema delta spec
- [x] 4.2 在同檔（或 `_pricing.py` / 別處）寫 `write_llm_cost(conn, decision_id, usage, clock)` helper（呼叫 SQLite `INSERT INTO llm_costs ...`）
- [x] 4.3 在 `src/ohmystock/decider/orchestrator.py` 實作 `decide_entry(entry_input, *, conn, decider, clock=system_clock, decision_id_factory=default_decision_id)`，依 spec 步驟 1-6 串接，整段用 `BEGIN/COMMIT` 包成 atomic
- [x] 4.4 處理 `DeciderOutputParseError`：catch 後寫 reject + llm_costs（usage 取不到則 0），re-raise
- [x] 4.5 在 `tests/test_decider_orchestrator.py` 用 in-memory sqlite + `init_schema(conn)` + `FakePMConclusionNode` 測：enter 路徑寫 1 筆 `kind=entry` + 1 筆 `llm_costs`、LLM 自願 reject、系統 force_reject、parse error、寫入失敗 rollback
- [x] 4.6 額外測試：FTS5 命中（寫入後用 `MATCH '杯柄突破'` 確認 entry_thesis 被索引）、`auto_executed=false` / `human_confirmed_by=null` / `stop_loss_price=null` 三個 null 欄位

## 5. CLI 整合

- [x] 5.1 在 `src/ohmystock/config.py` 新增 `ohmystock_decider_model: str = "claude-opus-4-7"` 與 `ohmystock_allow_fake_decider: bool = False` 兩個 Settings 欄位，env 對應 `OHMYSTOCK_DECIDER_MODEL` / `OHMYSTOCK_ALLOW_FAKE_DECIDER`
- [x] 5.2 更新 `.env.example` 新增 `OHMYSTOCK_DECIDER_MODEL=claude-opus-4-7` 與 `OHMYSTOCK_ALLOW_FAKE_DECIDER=false` 兩行
- [x] 5.3 在 `tests/test_cli.py`（既有 settings 測試所在）追加 case：兩個新 env var 預設值 + env 覆寫 + truthy bool
- [x] 5.4 在 `src/ohmystock/cli/_decide.py` 新建 Typer 子命令 `decide(symbol, asof, json_)`，串 `_run_assemble` → `init_schema` → `decide_entry` → 印 stdout + exit code 0/1/2/3/4
- [x] 5.5 在 `src/ohmystock/cli/__init__.py` 註冊新子命令，並在 root help 與 `decide --help` 中含字面 `pending_confirm` 警告
- [x] 5.6 在 `tests/test_cli_decide.py` 用 Typer `CliRunner` + monkeypatch 測 6 個 scenario：help 含旗標、enter exit 0、reject exit 1、assembler 失敗 exit 2、parse error exit 3、`fake://` model 在非測試 env 拒絕 exit 4
- [x] 5.7 `--json` 路徑：測 `json.loads(stdout)` 為合法 dict 且含 `decision_id` / `decision` / `force_reject_reason` / `cost_usd` 四 key

## 6. 文件與驗證

- [x] 6.1 在 `docs/design-zh-TW.md` §4.7.1 entry_decision_team swarm 段落補一行：「PM 結論節點 + 系統覆寫驗證器已實作；specialist 節點待後續 change」
- [x] 6.2 在 `docs/llm-decision-schema.md` 開頭 metadata 列「v3.1 schema 已由 `ohmystock.decider.models.DeciderOutput` 實作」（不改 schema 內容）
- [x] 6.3 在 CLAUDE.md §5 唯一權威表追加一列：「LLM Decider 系統覆寫規則 → `openspec/specs/entry-decider/spec.md` (archive 後)」
- [x] 6.4 跑 `make test`，確認所有新測試 pass、舊測試無 regression（573 passed in 3.62s）
- [ ] 6.5 跑 `uv run ohmystock decide --symbol 2330 --asof <最近交易日> --json`（用真 ANTHROPIC_API_KEY），確認端到端可跑（手動驗證；不寫成 integration test）— **DEFERRED**：需要 user 手動跑（要真 API key + 交易日），不在 LLM agent 範圍

## 7. OpenSpec 收尾

- [x] 7.1 全部任務完成後，跑 `openspec status --change entry-decider-pm-node`，確認 4/4 artifacts 完成 + `--strict` validation 通過
- [ ] 7.2 預備 archive：用 `/opsx:archive entry-decider-pm-node` 啟動歸檔（user 手動觸發）
