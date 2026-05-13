## 1. backend — pydantic body model

- [x] 1.1 在 `src/ohmystock/api/routes/proposals.py` 新增 `class PeriodModel(BaseModel)`（`model_config = ConfigDict(extra="forbid", populate_by_name=True)`、欄位 `from_: str = Field(alias="from")`、`to: str`、`@field_validator("from_", "to")` 檢查 `^\d{4}-\d{2}-\d{2}$`、`@model_validator(mode="after")` 檢查 `from_ <= to`）
- [x] 1.2 新增 `class ValidateRequest(BaseModel)`（`extra="forbid"`），欄位順序：`strategy: str`、`period: PeriodModel`、`param_overrides: list[str]`、`universe: list[str]`（`min_length=1`）、`wfa_windows: int = 5`（`ge=2`）、`in_sample_ratio: float = 0.7`（`gt=0, lt=1`）、`initial_capital: int | None = None`、`dry_run: bool = False`

## 2. backend — module-level factory

- [x] 2.1 在 `routes/proposals.py` 模組頂層新增 `_MARKET_DATA_LOADER_FACTORY: Callable[[], Callable[[str, str, str], list[BarRow]]] = lambda: (lambda sym, s, e: select_bars(get_connection(), sym, s, e))`，註解註明 test-override seam 同 `_PROPOSALS_ROOT_FACTORY` 模式
- [x] 2.2 為 `select_bars` / `get_connection` / `BarRow` 增加 import：`from ohmystock.api.db import get_connection`、`from ohmystock.data.cache import select_bars`、`from ohmystock.data.sources.base import BarRow`

## 3. backend — route handler 骨架

- [x] 3.1 新增 `@router.post("/api/admin/proposals/{slug:path}/validate")` handler `validate_proposal_endpoint(slug: str, body: ValidateRequest = Body(...)) -> JSONResponse`，註冊**在** `transition` 路由**之後**（避免 catch-all `{slug:path}` 截走）
- [x] 3.2 與 `transition` 同步註冊 GET-405 handler：`@router.get("/api/admin/proposals/{slug:path}/validate")` 回 `JSONResponse(status_code=405, content={"detail": "Method Not Allowed"}, headers={"Allow": "POST"})`
- [x] 3.3 handler 步驟 a：`if not _is_safe_slug(slug): return 400 invalid_input`
- [x] 3.4 handler 步驟 b：`root = _PROPOSALS_ROOT_FACTORY()`；`path = _resolve_slug_to_path(root, slug)`；找不到 → return 404 `not_found`

## 4. backend — body parsing + param literal eval

- [x] 4.1 import `ast`；在 `routes/proposals.py` 同模組新增 `_parse_param_pairs(pairs: list[str]) -> dict[str, Any]` 完全比照 `cli._validate_proposal._parse_param_pairs`（key=value、`ast.literal_eval`、ValueError 含 `unparseable_param:` 前綴）。**不要** import CLI 那份，會跨模組耦合
- [x] 4.2 handler 步驟 c：`try: param_overrides_dict = _parse_param_pairs(body.param_overrides)`；`ValueError` → return 400 `invalid_input`，message = `str(exc)` (含 `unparseable_param:` 前綴)
- [x] 4.3 handler 步驟 d：`initial_capital = body.initial_capital if body.initial_capital is not None else Settings().starting_equity_twd`

## 5. backend — invoke validator + verdict envelope

- [x] 5.1 handler 步驟 e：`market_data_loader = _MARKET_DATA_LOADER_FACTORY()`
- [x] 5.2 handler 步驟 f：`try: report = run_validation(path, strategy_name=body.strategy, period={"from": body.period.from_, "to": body.period.to}, param_overrides=param_overrides_dict, universe=body.universe, wfa_windows=body.wfa_windows, in_sample_ratio=body.in_sample_ratio, initial_capital=initial_capital, market_data_loader=market_data_loader, dry_run=body.dry_run)`
- [x] 5.3 import `WfaValidationError` from `ohmystock.validation` + `run_validation`
- [x] 5.4 handler 步驟 g：on success 計算 `new_path_str` / `report_path_str`：dry_run → `(None, None)`；否則 `report.verdict == "pass"` → `(<PENDING_REVIEW path>, <report path>)`；`"fail"` → `(<rejected path>, <report path>)`。實作走 `_post_run_state_paths(report, slug, root, dry_run) -> tuple[str | None, str | None]` helper，內部 `try: relative = Path(...).relative_to(root).as_posix() except ValueError: logger.warning(...); fallback to str(...)`
- [x] 5.5 回 `JSONResponse(200, content=to_success({"verdict": report.verdict, "slug": slug, "new_status": new_status, "new_path": new_path_str, "report_path": report_path_str, "deltas": report.deltas, "failures": list(report.failures)}))`，其中 `new_status` map：dry_run → `"validating"`、pass → `"approved"`、fail → `"rejected"`

## 6. backend — error mapping

- [x] 6.1 handler 內 `except WfaValidationError as exc:` 區塊：`msg = str(exc)`；`if msg.startswith("status_not_validating"): return 409 illegal_transition`；`else: return 422 wfa_validation_failed`。兩者 `error.message` = `msg`（保留原始 token）
- [x] 6.2 handler 內 `except ProposalStateError as exc:` 區塊：`http, env = _map_state_error(exc); return JSONResponse(http, env)`
- [x] 6.3 handler 結尾 catch-all `except Exception as exc: http, env = map_exception_to_envelope(exc); return JSONResponse(http, env)`，**不**洩漏 traceback / 原 message
- [x] 6.4 確認 import：`from ohmystock.proposal import ProposalStateError`（已存在）；`from ohmystock.validation import WfaValidationError, run_validation`

## 7. backend — tests

- [x] 7.1 新增 `tests/api/test_admin_proposals_validate_endpoint.py`，imports `pytest`, `from fastapi.testclient import TestClient`, `from ohmystock.api.app import create_app`, `from ohmystock.api.routes import proposals as proposals_route`, `from ohmystock.proposal import ProposalDraft, write_proposal, transition_proposal`, `from ohmystock.data.sources.base import BarRow`, datetime/timezone helpers
- [x] 7.2 fixture `client` 建 TestClient + 設 `OHMYSTOCK_ADMIN_TOKEN` env；fixture `auth_headers` 回 `{"Authorization": f"Bearer {token}"}`；fixture `proposals_root(tmp_path, monkeypatch)` 設 `_PROPOSALS_ROOT_FACTORY` 指向 `tmp_path / "proposals"`
- [x] 7.3 fixture `synthetic_bars` + `loader_factory(monkeypatch)` 設 `_MARKET_DATA_LOADER_FACTORY` 回 synthetic lambda；helper `make_validating_proposal(proposals_root)` 同 wfa-engine 那份
- [x] 7.4 test `test_validate_unauthenticated_returns_401`
- [x] 7.5 test `test_validate_path_traversal_slug_returns_400` — slug `"..%2Fetc"`
- [x] 7.6 test `test_validate_unknown_slug_returns_404`
- [x] 7.7 test `test_validate_malformed_body_missing_strategy_returns_422`
- [x] 7.8 test `test_validate_body_extra_field_returns_422` — 含 `{"async": true}`
- [x] 7.9 test `test_validate_inverted_period_returns_422`
- [x] 7.10 test `test_validate_empty_universe_returns_422`
- [x] 7.11 test `test_validate_unparseable_param_returns_400` — `param_overrides=["foo=bar%bad"]`
- [x] 7.12 test `test_validate_pass_returns_200_with_envelope` — 注入合成 bars + monotonic prices → verdict=pass；assert `data.new_path` 以 `"PENDING_REVIEW/"` 起頭 + `data.new_status == "approved"` + `data.failures == []` + 檔案實際移到 `tmp_path/proposals/PENDING_REVIEW/`
- [x] 7.13 test `test_validate_fail_returns_200_with_failures` — monkeypatch `wfa._run_one` 製造 sharpe_gap 失敗；assert `data.verdict == "fail"`、`data.new_status == "rejected"`、`data.failures` 非空、`data.new_path` 以 `"rejected/"` 起頭
- [x] 7.14 test `test_validate_dry_run_keeps_validating_and_paths_null` — assert `data.new_status == "validating"`、`data.new_path is None`、proposal 仍在原位、`<slug>.validation.json` 不存在
- [x] 7.15 test `test_validate_pending_status_returns_409_illegal_transition` — proposal 留在 pending、assert `error.code == "illegal_transition"` + message 含 `status_not_validating`
- [x] 7.16 test `test_validate_unknown_strategy_returns_422_wfa_validation_failed` — body `strategy="made_up"`
- [x] 7.17 test `test_validate_missing_bars_returns_422_wfa_validation_failed` — loader 對 `"2330"` 回 `[]`
- [x] 7.18 test `test_validate_period_too_short_returns_422` — period 14 天
- [x] 7.19 test `test_validate_get_on_validate_returns_405` — GET `/api/admin/proposals/<slug>/validate`

## 8. backend — smoke

- [x] 8.1 `uv run pytest tests/api/test_admin_proposals_validate_endpoint.py -v` 全綠
- [x] 8.2 regression：`uv run pytest tests/api/test_proposals_endpoint.py tests/validation/test_wfa.py tests/cli/test_validate_proposal_cli.py` 仍綠
- [x] 8.3 `openspec validate admin-proposal-validate-action --strict` 全綠

## 9. frontend — api helper

- [x] 9.1 在 `web-admin/src/lib/api.ts` 新增 type `ValidateRequest = { strategy: string; period: { from: string; to: string }; param_overrides: string[]; universe: string[]; wfa_windows: number; in_sample_ratio: number; initial_capital: number | null; dry_run: boolean }`
- [x] 9.2 新增 type `ValidateResponse = { verdict: "pass" | "fail"; slug: string; new_status: "approved" | "rejected" | "validating"; new_path: string | null; report_path: string | null; deltas: { sharpe: number; max_drawdown: number; win_rate: number }; failures: string[] }`
- [x] 9.3 新增 export `async function validateProposal(slug: string, body: ValidateRequest): Promise<ValidateResponse>`，內部用既有 `apiFetch` wrapper、URL `/api/admin/proposals/${encodeURIComponent(slug)}/validate`、POST、body JSON.stringify(body)
- [x] 9.4 envelope unwrap：if `ok` → return `data`；else throw Error 物件 + `.code = error.code` + `.message = error.message`（沿用既有 `transitionProposal` 的 pattern）

## 10. frontend — validation dialog component

- [x] 10.1 新增 `web-admin/src/components/validation-dialog.tsx`，結構 clone 自 `web-admin/src/components/transition-dialog.tsx`：`<Dialog>` primitive + Header + form body + Footer (Cancel + 主 button)
- [x] 10.2 Props interface：`{ open: boolean; onOpenChange: (open: boolean) => void; slug: string; strategies: Strategy[] }`（`strategies` 由父 page 用 `useQuery(['strategies'], listStrategies)` 預載）
- [x] 10.3 localStorage key constant `LAST_VALIDATION_KEY = "ohmystock.admin.lastValidation"`；helper `loadPersisted(): Partial<PersistedFields>` + `persist(fields: PersistedFields): void`
- [x] 10.4 form state via `useState`：`strategy`、`periodFrom`、`periodTo`、`universeRaw`、`paramOverridesRaw`、`wfaWindows`、`inSampleRatio`、`initialCapital`、`dryRun`、`submitting`、`inlineError: string | null`
- [x] 10.5 `useEffect(() => { if (!open) return; const p = loadPersisted(); setStrategy(p.strategy ?? strategies[0]?.name ?? ""); setUniverseRaw(p.universe ?? "2330,0050,2317"); setWfaWindows(p.wfa_windows ?? 5); setInSampleRatio(p.in_sample_ratio ?? 0.7); setInitialCapital(p.initial_capital ?? 1_000_000); /* periodFrom/To, paramOverridesRaw, dryRun 永遠 reset */ }, [open])`
- [x] 10.6 render 9 fields 順序同 spec（Strategy select / Period from-to / Universe input / Param overrides textarea / WFA windows / IS ratio / Initial capital / Dry-run checkbox）；每欄含 label + descriptive helper text
- [x] 10.7 submit handler `onSubmit(e)`：preventDefault → build body（universe split + trim filter / paramOverrides split lines filter） → set `submitting=true` + clear `inlineError` → call `validateProposal(slug, body)` → on success: `persist(...)` + `queryClient.invalidateQueries({queryKey: ["proposal", slug]})` + `toast(message)` + `onOpenChange(false)` → on error: `setInlineError(`${err.code}: ${err.message}`)` + keep dialog open → finally `setSubmitting(false)`
- [x] 10.8 toast message factory：dry_run + pass → `"Dry run: verdict=pass — no state change"`；dry_run + fail (N) → `"Dry run: verdict=fail — no state change — ${N} failure(s)"`；pass → `"Validated: verdict=pass — moved to PENDING_REVIEW"`；fail (N) → `"Validated: verdict=fail — moved to rejected — ${N} failure(s)"`
- [x] 10.9 inline error region 在 footer 上方，class 同 `<TransitionDialog>` error pattern（`text-destructive text-sm`）
- [x] 10.10 submit button `disabled={submitting}` + spinner via existing `<Loader2>` lucide icon；Cancel 永遠 enabled

## 11. frontend — wire dialog into ProposalDetailPage

- [x] 11.1 在 `web-admin/src/pages/ProposalDetailPage.tsx` import `<ValidationDialog>` + `listStrategies`
- [x] 11.2 在 component 內 `useQuery(["strategies"], listStrategies)` 預載 strategies；handle loading（顯示 disabled button + "載入中…" tooltip）+ error（hide button）
- [x] 11.3 新增 state `const [validationOpen, setValidationOpen] = useState(false)`
- [x] 11.4 在 status-aware action row 的 `case "validating"` 分支：保留既有 `[Approve…][Reject…]`，**前面** prepend 新 button `<Button variant="default" onClick={() => setValidationOpen(true)} disabled={strategiesQuery.isLoading}>Run Validation…</Button>`
- [x] 11.5 在 component return 樹的 `<TransitionDialog>` 旁邊 mount `<ValidationDialog open={validationOpen} onOpenChange={setValidationOpen} slug={slug} strategies={strategiesQuery.data ?? []} />`

## 12. frontend — smoke

- [x] 12.1 `pnpm --filter web-admin typecheck`（或 `npm run typecheck`，依 repo 設定）全綠
- [x] 12.2 `pnpm --filter web-admin build` 全綠
- [ ] 12.3 手動 smoke：`uv run ohmystock api --no-reload`（已存在 `validating` proposal）→ open `/proposals/<slug>` → 點 `Run Validation…` → 對話框出現、`Strategy` 預設值正確、`Universe` 預設 `2330,0050,2317`、勾 Dry run → submit → toast 出現含 `Dry run: verdict=…`、proposal status 仍 `validating`

## 13. 收尾

- [x] 13.1 跑既有測試確認無 regression：`uv run pytest tests/api/ tests/validation/ tests/cli/test_validate_proposal_cli.py 2>&1` 仍綠
- [x] 13.2 `openspec validate admin-proposal-validate-action --strict` 全綠（再跑一次）
- [ ] 13.3 手動 smoke：`uv run ohmystock api --no-reload` + open web-admin → 確認 happy-path pass、happy-path fail（用合成資料）、unauth (打 curl)、unknown slug 都行為符合 spec
