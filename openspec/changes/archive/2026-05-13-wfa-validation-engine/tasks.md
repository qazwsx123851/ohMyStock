## 1. validation package skeleton

- [x] 1.1 新增目錄 `src/ohmystock/validation/`、檔案 `__init__.py`,re-export `WfaWindow`, `ValidationReport`, `WfaValidationError`, `run_validation`(從 `wfa.py`)
- [x] 1.2 新增 `src/ohmystock/validation/wfa.py`,docstring + spec link、imports(`json`, `os`, `tempfile`, `dataclasses.dataclass`/`asdict`、`datetime`, `pathlib.Path`, `Any`, `Callable`, `Literal`,reuse `run_backtest` / `compute_metrics` / `BarRow` / `available_strategies` / `transition_proposal` / `parse_proposal` / `Settings`)
- [x] 1.3 宣告 module-level 常數 `_THRESHOLDS = {"sharpe_gap_max": 0.30, "sharpe_relative_min": 0.95, "drawdown_relative_max": 1.20}`、`_DEFAULT_WFA_WINDOWS = 5`、`_DEFAULT_IS_RATIO = 0.7`、`_REPORT_SUFFIX = ".validation.json"`、`logger = logging.getLogger(__name__)`

## 2. dataclasses + exception

- [x] 2.1 定義 `@dataclass(frozen=True) class WfaWindow`(6 個欄位:`in_sample`, `out_of_sample`, `baseline_is_metrics`, `baseline_oos_metrics`, `candidate_is_metrics`, `candidate_oos_metrics`,皆為 `dict[str, Any]`)
- [x] 2.2 定義 `@dataclass(frozen=True) class ValidationReport`(16 個欄位,順序鎖死同 spec:`proposal_id`、`slug`、`validated_at`、`strategy`、`period`、`param_overrides`、`effective_kwargs`、`universe`、`wfa_windows`、`baseline_oos_aggregate`、`candidate_oos_aggregate`、`candidate_is_oos_sharpe_gap_pct`、`deltas`、`thresholds`、`verdict`、`failures`)
- [x] 2.3 定義 `class WfaValidationError(RuntimeError)` — 單一 message 參數,no extra attrs

## 3. window splitter (純函式,無 I/O)

- [x] 3.1 實作 `_split_windows(period: dict[str, str], n: int, is_ratio: float) -> list[dict[str, dict[str, str]]]`:把 `period["from"]` ~ `period["to"]` 的天數均分成 n 個 chunk;每 chunk 取前 `is_ratio` 為 IS、後段為 OOS;回 `[{"in_sample": {from,to}, "out_of_sample": {from,to}}, ...]`,日期均為 ISO 字串
- [x] 3.2 加入防呆:`days_between(from, to) < n * 5` → 拋 `WfaValidationError("period_too_short: ...")`;`is_ratio` 不在 `(0, 1)` → 拋 `WfaValidationError("invalid_in_sample_ratio: ...")`;`n < 2` → 拋 `WfaValidationError("invalid_wfa_windows: ...")`
- [x] 3.3 確保相鄰 chunk 完全不重疊:`windows[i].out_of_sample.to < windows[i+1].in_sample.from`(實作上由切分定義即自動成立,但加 invariant check 作 defensive guard)

## 4. backtest invocation helper

- [x] 4.1 實作 `_run_one(strategy, bars_by_symbol, period, initial_capital) -> dict[str, float]`:呼叫 `run_backtest`,從 envelope 抽 `data.metrics`,filter 出 `{sharpe, max_drawdown, win_rate}` 三個 key;`ok=False` → 拋 `WfaValidationError(f"backtest_failed: {error['code']}: {error['message']}")`
- [x] 4.2 實作 `_slice_bars(all_bars: dict[str, list[BarRow]], period: dict[str, str]) -> dict[str, list[BarRow]]`:per-symbol filter `[b for b in bars if period.from <= b.ts <= period.to]`,空 list → skip 該 symbol(讓 `_run_one` 自己決定怎麼處理);若全空 → 拋 `WfaValidationError("window_has_no_bars: ...")`

## 5. aggregator + threshold evaluator

- [x] 5.1 實作 `_aggregate_oos(windows_metrics: list[dict[str, float]]) -> dict[str, float]`:回 `{"sharpe": mean(per-window OOS sharpe), "max_drawdown": min(per-window OOS max_drawdown) (最負, 最深 drawdown), "win_rate": mean(per-window OOS win_rate)}`
- [x] 5.2 實作 `_sharpe_gap_pct(is_metrics: dict, oos_metrics: dict) -> float`:`abs(is_sharpe - oos_sharpe) / max(abs(is_sharpe), 1e-9)`
- [x] 5.3 實作 `_evaluate_thresholds(candidate_gap: float, candidate_agg: dict, baseline_agg: dict) -> tuple[Literal["pass","fail"], list[str]]`:依宣告順序檢查 3 條件,組裝 `failures` list,verdict = `"pass"` iff 三條件皆通過;每條失敗 message 含 slug(`sharpe_gap` / `sharpe_degradation` / `drawdown_degradation`)、actual、threshold 數字(4 decimal places)

## 6. report writer + state transition wiring

- [x] 6.1 實作 `_write_report_atomic(target_path: Path, report: ValidationReport) -> None`:`tempfile.NamedTemporaryFile(dir=target_path.parent, suffix=".validation.json.tmp", delete=False)` → 寫 `json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=False)` → `flush` + `os.fsync(fd)` → `os.replace(tmp_path, target_path)`;finally 清理 tmp 殘留
- [x] 6.2 實作 `_transition_after_verdict(proposal_path: Path, slug: str, verdict, failures, report_path: Path) -> Path`:pass → `transition_proposal(proposal_path, "approved", actor="wfa-validator", validation_report_path=Path(f"{slug}.validation.json"))`;fail → `transition_proposal(proposal_path, "rejected", actor="wfa-validator", reason="; ".join(failures)[:200])`;接著若 `new_path.parent != proposal_path.parent` 就把 report 一起搬:`report_path.rename(new_path.parent / report_path.name)`;回 `new_path`

## 7. `run_validation` orchestrator

- [x] 7.1 實作 `run_validation(proposal_path, *, strategy_name, period, param_overrides, universe, wfa_windows=5, in_sample_ratio=0.7, initial_capital, market_data_loader, dry_run=False) -> ValidationReport`,流程:a) `parse_proposal(proposal_path)` 取 `proposal_id` / `status`;b) `status != "validating"` → 拋 `WfaValidationError(f"status_not_validating: actual={status}")`;c) 查 `available_strategies()` 找 strategy class;找不到 → 拋 `WfaValidationError(f"unknown_strategy: {strategy_name}")`;d) 嘗試 `strategy_cls()` 取 default kwargs(可從 `__init__.__defaults__` 或實際建構物件後 `vars()` 抽);失敗 → 拋 `WfaValidationError(...)`;e) 計算 `effective_kwargs = default_kwargs | param_overrides`;f) 建立 baseline + candidate 兩個 strategy instance
- [x] 7.2 流程(續):g) `_split_windows(period, wfa_windows, in_sample_ratio)`;h) per symbol 呼叫 `market_data_loader(sym, period.from, period.to)`,空 → 拋 `WfaValidationError(f"missing_bars: {sym}")`;i) per window per IS/OOS 跑 baseline + candidate 4 次 backtest,組裝 `WfaWindow`;j) `_aggregate_oos` 兩次(baseline / candidate);k) 計算 `candidate_is_oos_sharpe_gap_pct = mean(per-window candidate gap)`;l) `_evaluate_thresholds` 取 `(verdict, failures)`;m) 組裝 `ValidationReport`(`validated_at` 用 `datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")`)
- [x] 7.3 流程(續):n) 若 `dry_run` → 直接 return report;o) 否則 `_write_report_atomic(proposal_path.parent / f"{slug}.validation.json", report)`,再 `_transition_after_verdict(...)`;return report

## 8. CLI subcommand

- [x] 8.1 新增 `src/ohmystock/cli/_validate_proposal.py`:docstring + spec link、imports
- [x] 8.2 實作 `def validate_proposal(slug: str, strategy: str, period: str, param: list[str] = [], wfa_windows: int = 5, in_sample_ratio: float = 0.7, universe: str = "2330,0050,2317", initial_capital: int = ..., dry_run: bool = False)` typer handler
- [x] 8.3 handler 步驟:a) 解析 `--period from=YYYY-MM-DD,to=YYYY-MM-DD` 為 dict;b) `_resolve_proposal_path(slug)` 在 4 個子目錄找 `{slug}.md`,找不到 → `typer.echo` + `raise typer.Exit(2)`;c) `parse_proposal` 讀 frontmatter,`status != "validating"` → exit 2;d) 解析 `--param key=value` list 為 `dict[str, Any]`,用 `ast.literal_eval` 對 value 端;e) `available_strategies()` 找 strategy;f) `try: strategy_cls(**effective_kwargs)` 預檢 kwargs 合法性,TypeError → exit 2 `unknown_param`
- [x] 8.4 handler 步驟(續):g) `market_data_loader = lambda sym, s, e: select_bars(get_connection(), sym, s, e)`;h) `run_validation(...)`;捕捉 `WfaValidationError` → exit 2;i) 列印一行 summary:`verdict=<pass|fail> slug=<slug> sharpe_delta=<+N.NN%> mdd_delta=<+N.NN%>`;j) exit code 0 (pass) / 1 (fail) / dry-run 永遠 0
- [x] 8.5 在 `src/ohmystock/cli/__init__.py` 註冊 `@app.command("validate-proposal", help="...")` 並 dispatch 到 `_validate_proposal.validate_proposal`(注意:既有的 stub `propose` 命令保留,本命令是獨立 `validate-proposal`)

## 9. tests — library unit

- [x] 9.1 新增 `tests/validation/__init__.py`、`tests/validation/test_wfa.py`,docstring + spec link
- [x] 9.2 fixture `synthetic_bars(symbol, n_days, base_price)`:產生 n_days 個 BarRow(`ts` 從 `2025-01-02` 起的工作日 ISO 字串,`o=h=l=c=base_price + i * 0.5`,`v=1_000_000`,`amount=...`),回 `list[BarRow]`;另一 fixture 提供 `synthetic_loader(bars_by_symbol_full)` lambda 給 `market_data_loader`
- [x] 9.3 helper `make_validating_proposal(tmp_path, slug, topic)` — 用 `write_proposal` + `transition_proposal` 把一份 proposal 推到 `validating` status,回 path
- [x] 9.4 test `test_split_windows_5_disjoint_over_250_days` 對應 spec scenario "5 disjoint windows over a 250-day period"
- [x] 9.5 test `test_split_windows_period_too_short_raises` 對應 spec scenario "period_too_short refuses degenerate input"
- [x] 9.6 test `test_run_validation_dry_run_does_not_transition_or_write`(用 fixture proposal + 1 symbol + 250-day period + sma_cross + override `fast=10`)
- [x] 9.7 test `test_run_validation_pass_transitions_to_approved_and_moves_report`(構造一個 baseline/candidate 都會 pass 的合成 bars,assert frontmatter `status=approved`、frontmatter `validation_report_path` 存在、report 檔在 `PENDING_REVIEW/<slug>.validation.json`)
- [x] 9.8 test `test_run_validation_fail_transitions_to_rejected_with_reason`(構造一份 candidate 故意爆過 30% Sharpe gap 的 bars,assert frontmatter `status=rejected`、frontmatter `rejected_reason` 含 `sharpe_gap`)
- [x] 9.9 test `test_run_validation_status_not_validating_raises`(把 proposal 留在 `pending`,呼叫 `run_validation` 拋 `WfaValidationError("status_not_validating: actual=pending")`)
- [x] 9.10 test `test_run_validation_missing_bars_raises`(`market_data_loader` 對 `"2330"` 回空 list,拋 `WfaValidationError("missing_bars: 2330")`)
- [x] 9.11 test `test_run_validation_unknown_strategy_raises`(`strategy_name="made_up"` 拋 `WfaValidationError("unknown_strategy: made_up")`)
- [x] 9.12 test `test_report_dataclass_field_order` — `[f.name for f in fields(ValidationReport)][:5] == ["proposal_id","slug","validated_at","strategy","period"]`,鎖 JSON top-down 可讀性
- [x] 9.13 test `test_threshold_evaluator_three_failures_in_declared_order` — 喂三條件全爆的合成 metrics,assert `failures` 長度 3 且 slug 順序為 `sharpe_gap` → `sharpe_degradation` → `drawdown_degradation`

## 10. tests — CLI integration

- [x] 10.1 新增 `tests/cli/test_validate_proposal_cli.py`,使用 `typer.testing.CliRunner` + monkeypatch `_REVIEWS_ROOT_FACTORY` 同 pattern 的方式 patch proposals_dir + market data loader 注入 synthetic bars
- [x] 10.2 test `test_cli_happy_path_pass_exits_0`
- [x] 10.3 test `test_cli_fail_exits_1` — 同上但 candidate 爆 threshold
- [x] 10.4 test `test_cli_dry_run_always_exits_0_no_write_no_transition`
- [x] 10.5 test `test_cli_status_not_validating_exits_2` — proposal 仍 `pending`
- [x] 10.6 test `test_cli_unknown_strategy_exits_2`
- [x] 10.7 test `test_cli_unparseable_param_exits_2` — `--param foo=bar%bad`(literal_eval 失敗)
- [x] 10.8 test `test_cli_proposal_not_found_exits_2` — slug 不存在於 4 個子目錄

## 11. 收尾

- [x] 11.1 `uv run pytest tests/validation/test_wfa.py tests/cli/test_validate_proposal_cli.py -v` 全綠
- [x] 11.2 跑既有測試確認無 regression:`uv run pytest tests/api/test_proposals_endpoint.py tests/test_proposal_state_machine.py 2>&1` 仍綠
- [x] 11.3 `openspec validate wfa-validation-engine --strict` 全綠
- [x] 11.4 手動 smoke:`uv run ohmystock validate-proposal --help` 顯示 help,選一份 fixture proposal 跑 `--dry-run` 確認 stdout summary 格式正確
