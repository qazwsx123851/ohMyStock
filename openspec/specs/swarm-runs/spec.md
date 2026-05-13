# swarm-runs Specification

## Purpose

Defines the `swarm_runs` SQLite table schema, the `PresetSpec` registry (v0 ships `phase5-review`), the async `run_swarm` runner that wraps `ohmystock.review.pipeline.run_review` and emits 12 swarm events around it, and the 4 admin endpoints (`GET /presets`, `POST /runs`, `GET /runs?limit=N`, `GET /runs/{id}`) that drive the web-admin `/swarm` pages. Owns the spec invariants for "swarm runner never re-raises Exception, fail-fast on missing API key, infers failed_node from on-disk file order on failure".

## Requirements

### Requirement: swarm_runs SQLite 表 schema 與 idempotent 創建

系統 SHALL 提供 `ohmystock.swarm_runs.storage` 模組，含 `init_schema(conn: sqlite3.Connection) -> None` 函式 idempotent 創建 `swarm_runs` 表，schema 至少含以下欄位（型別 / 約束）：

- `id TEXT PRIMARY KEY` — 格式 `swr_<12hex>`
- `preset TEXT NOT NULL` — registry 中的 preset name
- `status TEXT NOT NULL CHECK(status IN ('completed','failed'))`
- `params_json TEXT NOT NULL` — POST body 原樣 echo
- `result_json TEXT NOT NULL` — `run_swarm` 回傳的完整 result（含 node_outputs / failed_node / error）
- `elapsed_ms INTEGER NOT NULL`
- `created_at TEXT NOT NULL` — ISO-8601 含 `+08:00`

`init_schema` SHALL 同時 idempotent 創建 `idx_swarm_runs_created_at` index 在 `created_at` 上。`init_schema` SHALL 在 `api/app.py` 的 `_lifespan` 啟動鉤子內被呼叫，順序在 `backtest_storage.init_schema` 之後、`memory_init_schema` 之前。

#### Scenario: init_schema 重複呼叫不報錯
- **WHEN** 對同一 connection 連續呼叫 `init_schema(conn)` 兩次
- **THEN** 第二次 SHALL 不拋例外
- **AND** `PRAGMA table_info(swarm_runs)` SHALL 回傳 7 個欄位

#### Scenario: status 欄位 CHECK 約束生效
- **WHEN** 嘗試 INSERT 一筆 `status="pending"` 的 row
- **THEN** sqlite3 SHALL 拋 `IntegrityError`（CHECK constraint failed）

#### Scenario: id 欄位主鍵唯一
- **WHEN** 嘗試 INSERT 兩筆相同 `id="swr_abc123def456"` 的 row
- **THEN** 第二次 INSERT SHALL 拋 `IntegrityError`（UNIQUE constraint failed）

---

### Requirement: PresetSpec 與 preset registry

系統 SHALL 在 `ohmystock.swarm_runs.presets` 提供 `PresetSpec` (frozen pydantic, `extra="forbid"`)，欄位：

- `name: str` — kebab-case，1–40 字
- `title: str` — 中文/英文短標題
- `description: str` — 1–2 句說明
- `nodes: list[str]` — 節點順序，至少 1 個
- `params_schema: dict[str, Any]` — JSON schema-like dict 描述 POST body 必填欄位

並 SHALL 提供 `PRESETS: dict[str, PresetSpec]` module-level constant，v0 SHALL 至少含一個 entry：

- `"phase5-review"`：`title="Phase 5 復盤"`、`nodes=["data_loader","attributor","aggregator","critic","proposer"]`、`params_schema={"period_from":"date","period_to":"date","limit_trades":"int|null","dry_run":"bool","force":"bool"}`

並 SHALL 提供 `get_preset(name: str) -> PresetSpec` helper，未知 name SHALL 拋 `KeyError(f"unknown preset: {name!r}")`。

#### Scenario: PRESETS 至少含 phase5-review
- **WHEN** 執行 `from ohmystock.swarm_runs.presets import PRESETS`
- **THEN** `"phase5-review" in PRESETS` SHALL 為 `True`
- **AND** `PRESETS["phase5-review"].nodes` SHALL 等於 `["data_loader","attributor","aggregator","critic","proposer"]`

#### Scenario: get_preset 對未知 name 拋 KeyError
- **WHEN** 執行 `get_preset("nonexistent")`
- **THEN** SHALL 拋 `KeyError`，訊息含 `"unknown preset"` 子字串

#### Scenario: PresetSpec 對 extra 欄位拒絕
- **WHEN** 嘗試 `PresetSpec(name="x", title="y", description="z", nodes=["a"], params_schema={}, extra_field="boom")`
- **THEN** SHALL 拋 pydantic `ValidationError`

---

### Requirement: run_swarm 薄包裝 run_review 並 emit 5 個事件

系統 SHALL 在 `ohmystock.swarm_runs.runner` 提供 `run_swarm(preset_name: str, params: dict, *, db_conn, out_dir, proposals_dir, market_data_loader, cheatsheet_path, llm_factory=None, now=None) -> SwarmRunResult` async 函式：

行為（happy path）：

1. `get_preset(preset_name)` 取得 `PresetSpec`；未知 preset → 拋 `SwarmRunnerError("unknown_preset: <name>")`
2. 對 phase5-review preset：驗 `params` 有 `period_from`/`period_to`（ISO date）、`from <= to`；缺欄 / 格式錯 → `SwarmRunnerError("invalid_params: <detail>")`
3. 生成 `run_id = "swr_" + uuid4().hex[:12]`；`started_at = datetime.now(TPE)`
4. `await safe_emit(Event(event_type=EventType.SWARM_RUN_STARTED, agent=Agent.REVIEWER, payload={"run_id": run_id, "preset": preset_name, "nodes": preset.nodes, "params": params}))`
5. 對每個節點 `n in preset.nodes`：
   - `_current_node = n`
   - `await safe_emit(Event(event_type=EventType.SWARM_NODE_STARTED, agent=Agent.REVIEWER, payload={"run_id": run_id, "preset": preset_name, "node": n}))`
   - 跑該節點（v0 直接呼叫 `run_review` 一次跑完全部 5 節點，並從 `ReviewResult` 取對應欄位填 `node_outputs[n]`；節點細粒度 emit 由 runner 內部依序發 — 因 `run_review` 是同步整段呼叫，runner SHALL 在「呼叫前發 `data_loader started`、回來後依序發 `data_loader completed` → `attributor started` → ... → `proposer completed`」即可）
   - `await safe_emit(Event(event_type=EventType.SWARM_NODE_COMPLETED, agent=Agent.REVIEWER, payload={"run_id": run_id, "preset": preset_name, "node": n, "elapsed_ms": int}))`
6. `await safe_emit(Event(event_type=EventType.SWARM_RUN_COMPLETED, agent=Agent.REVIEWER, payload={"run_id": run_id, "preset": preset_name, "elapsed_ms": int}))`
7. INSERT 一筆 row 到 `swarm_runs`（`status="completed"`）
8. Return `SwarmRunResult(run_id, status="completed", preset=preset_name, params=params, result=..., elapsed_ms=..., created_at=...)`

行為（failure path）：

任何節點 raise `Exception` SHALL：
- catch 住，**不**讓 exception 傳出 `run_swarm`
- emit `SWARM_RUN_FAILED` 含 `payload={"run_id": run_id, "preset": preset_name, "failed_node": _current_node, "error": {"code": str, "message": str}}`
- INSERT row（`status="failed"`、`result_json` 含 `{"failed_node": _current_node, "completed_nodes": [...], "error": {"code": ..., "message": ...}}`）
- Return `SwarmRunResult(status="failed", ...)`

但 `BaseException` 子類（`asyncio.CancelledError` / `KeyboardInterrupt`）SHALL **不**被 catch。

`Settings().anthropic_api_key` 缺失 SHALL 在步驟 4 之前 fail-fast，拋 `SwarmRunnerError("missing_api_key: ANTHROPIC_API_KEY not set")`，**不**入 row、**不**發任何 event。

#### Scenario: happy path emit 12 個 event 並寫 row
- **GIVEN** fresh bus + spy queue + valid params + `Settings().anthropic_api_key` 已設、`run_review` mock 為立即回傳成功
- **WHEN** 呼叫 `await run_swarm("phase5-review", {"period_from":"2026-04-01","period_to":"2026-04-30","dry_run":True,"force":False,"limit_trades":None}, db_conn=conn, ...)`
- **THEN** spy queue 依序含 `swarm_run_started` (1) → `swarm_node_started`/`swarm_node_completed` 配對 5 組 (10) → `swarm_run_completed` (1) 共 12 個 event
- **AND** `SELECT COUNT(*) FROM swarm_runs WHERE status='completed'` 等於 1

#### Scenario: 中途節點失敗 emit run_failed 並寫 failed row
- **GIVEN** `run_review` mock 在第 3 個節點 (`aggregator`) 拋 `RuntimeError("aggregator boom")`
- **WHEN** 呼叫 `await run_swarm(...)`
- **THEN** spy queue 含 `swarm_run_failed`，payload `failed_node="aggregator"`、`error.message` 含 `"aggregator boom"` 子字串
- **AND** `SELECT status, json_extract(result_json,'$.failed_node') FROM swarm_runs` 回 `("failed", "aggregator")`
- **AND** `run_swarm` SHALL 正常 return `SwarmRunResult(status="failed", ...)`，**不**重新 raise

#### Scenario: 缺 ANTHROPIC_API_KEY fail-fast 不入 row
- **GIVEN** `Settings().anthropic_api_key` 為空
- **WHEN** 呼叫 `await run_swarm(...)`
- **THEN** SHALL 拋 `SwarmRunnerError`，訊息以 `"missing_api_key:"` 開頭
- **AND** `SELECT COUNT(*) FROM swarm_runs` 等於 0
- **AND** spy queue **不**含任何 `swarm_*` event

#### Scenario: 未知 preset 拋 SwarmRunnerError
- **WHEN** 呼叫 `await run_swarm("unknown-preset", {}, ...)`
- **THEN** SHALL 拋 `SwarmRunnerError`，訊息以 `"unknown_preset:"` 開頭
- **AND** 不入 row、不發 event

#### Scenario: invalid params 拋 SwarmRunnerError
- **WHEN** 呼叫 `await run_swarm("phase5-review", {"period_from":"2026-04-30","period_to":"2026-04-01"}, ...)`（period 顛倒）
- **THEN** SHALL 拋 `SwarmRunnerError`，訊息以 `"invalid_params:"` 開頭

---

### Requirement: GET /api/admin/swarm/presets 列出 registry

系統 SHALL 在 `/api/admin/swarm/presets` 暴露 `GET` 端點，Bearer auth + `{ok,data,error}` envelope。回傳 `data` SHALL 為 `{items: PresetSummary[]}`，每個 `PresetSummary` 含 `name`/`title`/`description`/`nodes`/`params_schema` 5 個 key（直接從 `PRESETS` dict 序列化）。

未認證 SHALL 回 401（`auth_missing` / `auth_invalid`）。

#### Scenario: 200 列出全部 preset
- **WHEN** authenticated request `GET /api/admin/swarm/presets`
- **THEN** response HTTP 200，body `{"ok": true, "data": {"items": [...]}}`
- **AND** `data.items` 至少 1 個元素，且該元素 `name == "phase5-review"`

#### Scenario: 缺 Authorization 401
- **WHEN** request 不帶 Authorization
- **THEN** HTTP 401 with `error.code == "auth_missing"`

---

### Requirement: POST /api/admin/swarm/runs sync 跑並回完整 row

系統 SHALL 在 `/api/admin/swarm/runs` 暴露 `POST` 端點，Bearer auth + envelope。Body schema (`SwarmRunRequest`, pydantic `extra="forbid"`)：

- `preset: str`（必填）
- `params: dict[str, Any]`（必填，內容由 preset 自行 validate）

handler 行為：

1. `get_preset(preset)` 失敗 → 400 `invalid_input: unknown preset`
2. `await run_swarm(preset, params, db_conn=Depends(get_db), ...)`
3. `run_swarm` raise `SwarmRunnerError` 開頭為 `missing_api_key:` → 422 `missing_api_key`
4. `run_swarm` raise `SwarmRunnerError` 開頭為 `invalid_params:` → 400 `invalid_input`
5. 其他 `SwarmRunnerError` → 422 `swarm_runner_failed`
6. `run_swarm` return `SwarmRunResult` （含 status="completed" 或 "failed"）→ 200 with `data` = SwarmRunRow（含 `result_json` 完整內容）

`SwarmRunRow` 序列化 `result_json` SHALL 是 nested dict（已 parse），不是 raw string。

#### Scenario: happy path 200 回完整 row
- **GIVEN** Settings.anthropic_api_key 已設、run_review mock 成功
- **WHEN** `POST /api/admin/swarm/runs` body `{"preset":"phase5-review","params":{"period_from":"2026-04-01","period_to":"2026-04-30","dry_run":true,"force":false,"limit_trades":null}}`
- **THEN** HTTP 200，`data.id` matches `^swr_[0-9a-f]{12}$`、`data.status == "completed"`、`data.preset == "phase5-review"`、`data.result` 為 nested dict 含 `node_outputs` key

#### Scenario: 失敗 row 也是 200（non-2xx 留給 endpoint-level 錯誤）
- **GIVEN** run_review mock 在 critic 節點拋例外
- **WHEN** `POST /api/admin/swarm/runs` 同 body
- **THEN** HTTP 200，`data.status == "failed"`、`data.result.failed_node == "critic"`、`data.result.error.code` 為非空字串

#### Scenario: 未知 preset 400
- **WHEN** body `{"preset":"unknown","params":{}}`
- **THEN** HTTP 400 with `error.code == "invalid_input"`、message 含 `"unknown preset"`

#### Scenario: 缺 ANTHROPIC_API_KEY 422
- **GIVEN** Settings.anthropic_api_key 為空
- **WHEN** body 同 happy path
- **THEN** HTTP 422 with `error.code == "missing_api_key"`

#### Scenario: extra 欄位拒絕
- **WHEN** body `{"preset":"phase5-review","params":{...},"extra":"boom"}`
- **THEN** HTTP 422 (FastAPI pydantic validation error)

---

### Requirement: GET /api/admin/swarm/runs?limit=N 列出近期 run

系統 SHALL 在 `/api/admin/swarm/runs` 暴露 `GET` 端點，Bearer auth + envelope。

回傳 `data` SHALL 為 `{items: SwarmRunSummary[], limit: int}`，每個 `SwarmRunSummary` 含 `id`/`preset`/`status`/`elapsed_ms`/`created_at` 5 個 key — **不**含 `params_json` / `result_json`（避免列表頁拉太大 payload）。

`?limit=` 預設 50；`limit > 100` SHALL silently clamp 到 100；`limit < 1` SHALL 回 400 `invalid_input`。

排序 SHALL 為 `created_at DESC`，ties 用 `id DESC`。

#### Scenario: 200 列出近期 row
- **GIVEN** swarm_runs 表已有 3 筆 row（不同 created_at）
- **WHEN** authenticated request `GET /api/admin/swarm/runs`
- **THEN** HTTP 200，`data.items` 長度 3、按 `created_at DESC` 排
- **AND** 每個 item 只有 5 個 key（無 `params_json` / `result_json`）

#### Scenario: limit clamp 到 100
- **WHEN** `GET /api/admin/swarm/runs?limit=999`
- **THEN** `data.limit == 100`、`data.items` 長度 ≤ 100

#### Scenario: limit < 1 回 400
- **WHEN** `GET /api/admin/swarm/runs?limit=0`
- **THEN** HTTP 400 with `error.code == "invalid_input"`

#### Scenario: 空表回空 list
- **WHEN** swarm_runs 為空
- **THEN** HTTP 200，`data.items == []`

---

### Requirement: GET /api/admin/swarm/runs/{id} 回完整 row 或 404

系統 SHALL 在 `/api/admin/swarm/runs/{id}` 暴露 `GET` 端點，Bearer auth + envelope。回傳 `data` SHALL 為單筆 `SwarmRunRow`，含 `id`/`preset`/`status`/`params`(parsed)/`result`(parsed)/`elapsed_ms`/`created_at` 7 個 key。

`{id}` 不存在於表中 SHALL 回 404 with `error.code == "not_found"`、message 含 `"swarm run not found: <id>"` 子字串。

`{id}` 含 `/`、`\`、`..` 等 path-traversal token SHALL 在 BEFORE DB 讀取前拒絕回 400 `invalid_input`（與 admin-proposals-endpoints 相同 `_INVALID_NAME_TOKENS` 模式）。

#### Scenario: 200 回完整 row 含 parsed result
- **GIVEN** swarm_runs 已有一筆 `id="swr_abc123def456"` 的 row
- **WHEN** `GET /api/admin/swarm/runs/swr_abc123def456`
- **THEN** HTTP 200，`data.id == "swr_abc123def456"`、`data.params` 為 dict、`data.result` 為 dict

#### Scenario: 404 對未知 id
- **WHEN** `GET /api/admin/swarm/runs/swr_doesnotexist`
- **THEN** HTTP 404 with `error.code == "not_found"`、message 含 `"swr_doesnotexist"` 子字串

#### Scenario: path-traversal 400
- **WHEN** `GET /api/admin/swarm/runs/..%2Fsecrets`
- **THEN** HTTP 400 with `error.code == "invalid_input"`
- **AND** DB 不被讀取
