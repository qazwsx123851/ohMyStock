## ADDED Requirements

### Requirement: Validate endpoint shape and route registration

The system SHALL expose `POST /api/admin/proposals/{slug:path}/validate` on the existing proposals `APIRouter` (the one already mounted with `dependencies=[Depends(require_admin)]`). The route MUST share the same Bearer-auth guard, the same `_PROPOSALS_ROOT_FACTORY` test seam, and the same `{ok, data, error}` envelope helpers as the sibling list/detail/transition routes.

The `{slug}` path parameter MUST be validated against `_INVALID_NAME_TOKENS` (`/`, `\`, `..`, `os.sep`) BEFORE any disk I/O. A failing slug MUST return HTTP 400 with envelope code `invalid_input`.

After the slug check, the route MUST resolve the proposal via the existing `_resolve_slug_to_path(root, slug)` helper. A missing slug MUST return HTTP 404 with envelope code `not_found`.

#### Scenario: route is registered under the admin auth router
- **WHEN** the FastAPI app is constructed
- **THEN** `POST /api/admin/proposals/{slug}/validate` is registered on the same router as `GET /api/admin/proposals` and `POST /api/admin/proposals/{slug}/transition`
- **AND** the route MUST be reachable only with a valid Bearer token

#### Scenario: missing Authorization header returns 401
- **WHEN** an unauthenticated `POST /api/admin/proposals/example/validate` is issued
- **THEN** the response is HTTP 401 with envelope code `auth_missing`
- **AND** the proposal markdown is NOT read or modified

#### Scenario: path-traversal slug rejected before I/O
- **WHEN** the client sends `POST /api/admin/proposals/..%2Fetc%2Fpasswd/validate`
- **THEN** the response is HTTP 400 with envelope code `invalid_input`
- **AND** no proposal file is opened

#### Scenario: unknown slug returns 404
- **WHEN** the client sends `POST /api/admin/proposals/does-not-exist/validate`
- **THEN** the response is HTTP 404 with envelope code `not_found`

---

### Requirement: Validate request body shape

The request body SHALL be a `ValidateRequest` pydantic model with `extra="forbid"`. Fields:

- `strategy: str` (required) — registered strategy name.
- `period: PeriodModel` (required) — nested object `{from: str, to: str}` where each field matches `^\d{4}-\d{2}-\d{2}$` and `from <= to` (lexicographic ISO date compare). Pydantic SHALL alias `from_` ↔ `from` so callers send JSON `{"period": {"from": "...", "to": "..."}}`.
- `param_overrides: list[str]` (required, may be empty) — list of `key=value` strings; the server SHALL apply `ast.literal_eval` on each value using the same helper signature as `cli._validate_proposal._parse_param_pairs`.
- `universe: list[str]` (required, ≥1 entry) — symbol list.
- `wfa_windows: int = 5` (optional) — MUST be ≥ 2.
- `in_sample_ratio: float = 0.7` (optional) — MUST be in `(0, 1)`.
- `initial_capital: int | None = None` (optional) — when omitted the endpoint falls back to `Settings().starting_equity_twd`.
- `dry_run: bool = False` (optional).

Pydantic ValidationError MUST return HTTP 422 with envelope code `invalid_input` and `message` containing the offending field name(s).

Malformed `param_overrides` entries (failing `ast.literal_eval`) MUST return HTTP 400 with envelope code `invalid_input` and `message` prefixed `unparseable_param: <key>=<raw>`.

#### Scenario: well-formed body is accepted
- **WHEN** the body is `{"strategy":"sma_cross","period":{"from":"2025-01-02","to":"2025-12-30"},"param_overrides":["fast=10"],"universe":["2330"],"dry_run":true}`
- **THEN** the route accepts the body without raising

#### Scenario: missing required field rejected with 422
- **WHEN** the body omits `strategy`
- **THEN** the response is HTTP 422 with envelope code `invalid_input`
- **AND** `error.message` mentions `strategy`

#### Scenario: extra field rejected with 422
- **WHEN** the body adds `{"async": true}` alongside required fields
- **THEN** the response is HTTP 422 with envelope code `invalid_input`
- **AND** `error.message` mentions `async`

#### Scenario: malformed period date rejected with 422
- **WHEN** the body's `period.from` is `2025/01/02`
- **THEN** the response is HTTP 422 with envelope code `invalid_input`

#### Scenario: inverted period rejected with 422
- **WHEN** the body's `period.from` is `2025-12-30` and `period.to` is `2025-01-02`
- **THEN** the response is HTTP 422 with envelope code `invalid_input`

#### Scenario: empty universe rejected
- **WHEN** the body's `universe` is `[]`
- **THEN** the response is HTTP 422 with envelope code `invalid_input`

#### Scenario: unparseable param value returns 400 with named token
- **WHEN** the body's `param_overrides` contains `"foo=bar%bad"`
- **THEN** the response is HTTP 400 with envelope code `invalid_input`
- **AND** `error.message` contains the prefix `unparseable_param`

---

### Requirement: Validate endpoint calls `run_validation` via the new market-data factory

The route SHALL construct the `market_data_loader` via a module-level `_MARKET_DATA_LOADER_FACTORY: Callable[[], Callable[[str, str, str], list[BarRow]]]` that defaults to `lambda: (lambda sym, s, e: select_bars(get_connection(), sym, s, e))`. Tests SHALL monkeypatch this factory to inject synthetic loaders, the same pattern as the existing `_PROPOSALS_ROOT_FACTORY`.

The route SHALL call `ohmystock.validation.run_validation(proposal_path, strategy_name=..., period=..., param_overrides=..., universe=..., wfa_windows=..., in_sample_ratio=..., initial_capital=..., market_data_loader=..., dry_run=...)` synchronously and return its `ValidationReport`. The route MUST NOT directly invoke `_run_one`, `_split_windows`, or any other private helper — all validation flow goes through the public library entry point.

The route MUST NOT mutate proposal state directly; state transitions happen inside `run_validation` via `transition_proposal`.

#### Scenario: factory override drives the run
- **WHEN** a test monkeypatches `_MARKET_DATA_LOADER_FACTORY` to return a lambda that yields synthetic bars
- **AND** issues a valid validate request
- **THEN** `run_validation` is invoked with that lambda
- **AND** no SQLite connection is opened by the route module during the request

#### Scenario: synchronous call returns full ValidationReport shape
- **WHEN** the validator computes a verdict (pass or fail) without raising
- **THEN** the route returns the report's verdict, deltas, and post-transition paths in the response envelope
- **AND** the response is emitted in a single HTTP exchange (no polling/queue)

---

### Requirement: Validate endpoint success envelope shape

On `verdict == "pass"` with `dry_run == false`, the response SHALL be HTTP 200 with `data = { verdict: "pass", slug, new_status: "approved", new_path: "PENDING_REVIEW/<slug>.md", report_path: "PENDING_REVIEW/<slug>.validation.json", deltas: {sharpe, max_drawdown, win_rate}, failures: [] }`.

On `verdict == "fail"` with `dry_run == false`, the response SHALL be HTTP 200 with `data = { verdict: "fail", slug, new_status: "rejected", new_path: "rejected/<slug>.md", report_path: "rejected/<slug>.validation.json", deltas: {...}, failures: [str, ...] }`.

On `dry_run == true` (regardless of computed verdict), the response SHALL be HTTP 200 with `data = { verdict: "pass" | "fail", slug, new_status: "validating", new_path: null, report_path: null, deltas: {...}, failures: [...] }`. No `.validation.json` file MUST exist on disk after a dry-run.

`new_path` and `report_path`, when present, MUST be forward-slash-joined paths relative to `_PROPOSALS_ROOT_FACTORY()`. The conversion MUST use `Path.relative_to(root).as_posix()`.

#### Scenario: pass response payload
- **WHEN** the validator returns `verdict=pass` against a `validating` proposal in non-dry-run mode
- **THEN** the response is HTTP 200
- **AND** `data.verdict == "pass"` and `data.new_status == "approved"`
- **AND** `data.new_path` ends with `/<slug>.md` and starts with `PENDING_REVIEW/`
- **AND** `data.report_path` ends with `/<slug>.validation.json` and starts with `PENDING_REVIEW/`
- **AND** `data.failures == []`

#### Scenario: fail response payload
- **WHEN** the validator returns `verdict=fail` against a `validating` proposal in non-dry-run mode
- **THEN** the response is HTTP 200
- **AND** `data.verdict == "fail"` and `data.new_status == "rejected"`
- **AND** `data.new_path` starts with `rejected/`
- **AND** `data.failures` is a non-empty list of strings

#### Scenario: dry-run response payload
- **WHEN** the validator runs in dry-run mode
- **THEN** the response is HTTP 200
- **AND** `data.new_status == "validating"`
- **AND** `data.new_path is None` and `data.report_path is None`
- **AND** the on-disk proposal markdown's `status` remains `validating`
- **AND** no `.validation.json` file exists in the proposal's directory

---

### Requirement: Validate endpoint error mapping

`WfaValidationError(msg)` raised by the validator MUST be caught at the route boundary and mapped as follows:

- If `msg.startswith("status_not_validating")` → HTTP 409 envelope code `illegal_transition`, preserving the validator's full message.
- Otherwise → HTTP 422 envelope code `wfa_validation_failed`, preserving the validator's full message.

`ProposalStateError` raised during the validator's internal `transition_proposal` call MUST be mapped via the existing `_map_state_error` / `_STATE_ERROR_TO_ENVELOPE` table.

Any other unhandled exception MUST be mapped via `map_exception_to_envelope` to HTTP 500 envelope code `internal_error`. Raw exception messages MUST NOT leak through the response.

#### Scenario: non-validating status returns 409 illegal_transition
- **WHEN** the request targets a proposal whose frontmatter `status` is `pending`
- **THEN** the response is HTTP 409 with envelope code `illegal_transition`
- **AND** `error.message` contains the substring `status_not_validating`

#### Scenario: unknown strategy returns 422 wfa_validation_failed
- **WHEN** the request body has `strategy="made_up_strat"`
- **THEN** the response is HTTP 422 with envelope code `wfa_validation_failed`
- **AND** `error.message` contains `unknown_strategy: made_up_strat`

#### Scenario: missing bars returns 422 wfa_validation_failed
- **WHEN** the injected `market_data_loader` returns `[]` for a symbol in `universe`
- **THEN** the response is HTTP 422 with envelope code `wfa_validation_failed`
- **AND** `error.message` starts with the `missing_bars` token

#### Scenario: period_too_short returns 422 wfa_validation_failed
- **WHEN** the request's period span is fewer than `wfa_windows * 5` calendar days
- **THEN** the response is HTTP 422 with envelope code `wfa_validation_failed`
- **AND** `error.message` contains the substring `period_too_short`

#### Scenario: unexpected exception returns 500 internal_error without leaking
- **WHEN** the validator raises a non-WfaValidationError, non-ProposalStateError exception
- **THEN** the response is HTTP 500 with envelope code `internal_error`
- **AND** `error.message` does NOT contain the literal exception class name or traceback line
