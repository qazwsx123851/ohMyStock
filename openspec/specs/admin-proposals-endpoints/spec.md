# admin-proposals-endpoints Specification

## Purpose
TBD - created by archiving change admin-proposals-endpoints-and-pages. Update Purpose after archive.

## Requirements

### Requirement: List endpoint shape and source

The system SHALL expose `GET /api/admin/proposals` returning the parsed-frontmatter summary of every proposal markdown found by walking, in this order, `<proposals_root>/`, `<proposals_root>/PENDING_REVIEW/`, `<proposals_root>/merged/`, `<proposals_root>/rejected/` and listing only direct `.md` children at each level. Files in the root MUST exclude any whose stem matches a sub-dir name.

The endpoint MUST be registered with `Depends(require_admin)` and MUST wrap success in `to_success(...)` and any unhandled exception in `map_exception_to_envelope(...)`, matching the unified `{ok, data, error}` envelope.

The response `data` SHALL be `{ items: ProposalSummary[], total: int, limit: int, offset: int, has_more: bool }` where each `ProposalSummary` is `{ slug: str, proposal_id: str, status: ProposalStatus, topic: str, target_section: str, created_by: str, created_at: str, review_id: str | null, priority: "high" | "medium" | "low" }`. Items MUST be sorted by `created_at` descending, ties broken by `slug` descending (stable across runs).

`limit` SHALL default to 50, MUST clamp to ≤200; values >200 MUST be clamped silently. `offset` SHALL default to 0; negative values MUST yield HTTP 400 `code: "invalid_input"`. `total` SHALL be the count of all qualifying files (after status filter, before pagination). `has_more` SHALL equal `offset + len(items) < total`.

Files whose frontmatter cannot be parsed MUST be skipped silently with a `logger.warning("skipping malformed proposal: %s", path)` log line; they MUST NOT appear in `items` and MUST NOT count toward `total`.

#### Scenario: 200 with mixed-status registry
- **WHEN** an authenticated request hits `GET /api/admin/proposals`
- **AND** the proposals tree contains 1 pending file at root, 1 validating file at root, 1 approved file under `PENDING_REVIEW/`, 1 merged file under `merged/`, 1 rejected file under `rejected/`
- **THEN** the response is HTTP 200
- **AND** the body equals `{"ok": true, "data": {"items": [...], "total": 5, "limit": 50, "offset": 0, "has_more": false}}`
- **AND** every item has exactly the keys listed above

#### Scenario: items sorted by created_at desc
- **WHEN** the directory contains files with `created_at` values `2026-04-30T...`, `2026-05-10T...`, `2026-05-02T...`
- **THEN** `items[0].created_at` SHALL be the `2026-05-10` row
- **AND** `items[1].created_at` SHALL be the `2026-05-02` row
- **AND** `items[2].created_at` SHALL be the `2026-04-30` row

#### Scenario: empty directory returns empty list
- **WHEN** the proposals root contains no `.md` files at any of the 4 levels
- **THEN** the response is HTTP 200
- **AND** `data.items == []` and `data.total == 0` and `data.has_more is false`
- **AND** the response is NOT 404

#### Scenario: malformed proposal silently skipped
- **WHEN** the directory contains 1 valid pending file plus 1 file with no YAML frontmatter
- **THEN** `data.items` has length 1
- **AND** `data.total == 1`
- **AND** the malformed file path appears in the structured warning logs
- **AND** the malformed file does NOT cause a non-200 response

#### Scenario: limit clamps to 200
- **WHEN** the client sends `?limit=10000`
- **THEN** the response uses `data.limit == 200`
- **AND** at most 200 items are returned

#### Scenario: negative offset rejected
- **WHEN** the client sends `?offset=-1`
- **THEN** the response is HTTP 400 with `error.code == "invalid_input"`

---

### Requirement: List endpoint status filter

The list endpoint SHALL accept an optional `?status=` query parameter. When present, its value MUST be one of the 5 `ProposalStatus` literals (`pending`, `validating`, `approved`, `merged`, `rejected`); any other value MUST yield HTTP 400 `code: "invalid_input"`.

When `?status=` is set, the directory walk SHALL still cover all 4 sub-locations (the file's frontmatter `status` is the source of truth, not its containing directory); the filter SHALL apply in-memory after frontmatter parsing.

#### Scenario: status filter narrows to one bucket
- **WHEN** the directory contains 5 files (one of each status), and the client sends `?status=approved`
- **THEN** `data.items` has length 1
- **AND** the single item has `status == "approved"`
- **AND** `data.total == 1`

#### Scenario: status filter is source-of-truth, not directory-of-truth
- **WHEN** a file with frontmatter `status: pending` was manually moved into `<proposals_root>/merged/` (legacy / human edit)
- **AND** the client sends `?status=pending`
- **THEN** that file SHALL appear in `data.items`
- **AND** the same client sending `?status=merged` SHALL NOT include it

#### Scenario: invalid status rejected
- **WHEN** the client sends `?status=approve` (typo, missing `d`)
- **THEN** the response is HTTP 400 with `error.code == "invalid_input"`
- **AND** the error message names the offending parameter

---

### Requirement: Detail endpoint shape and source

The system SHALL expose `GET /api/admin/proposals/{slug}` returning the full body + parsed changelog for a single proposal.

The endpoint MUST be registered with `Depends(require_admin)` and MUST use the same envelope wrapping as the list endpoint.

On success, `data` SHALL be `{ slug, proposal_id, status, topic, target_section, created_by, created_at, review_id, priority, body: { description, motivation, diff_draft, expected_impact, risk_assessment, validation_plan, expected_improvement }, changelog: ChangelogEntry[], extra_frontmatter: { validation_report_path?, merged_to_version?, merged_at?, rejected_reason? } }`.

`body` fields MUST be the verbatim text of `## 1.` through `## 7.` sections (parsed by `ohmystock.proposal.writer.parse_proposal`). The `## 8. 變更紀錄` section MUST be parsed line-by-line into `ChangelogEntry` objects. `extra_frontmatter` MUST contain only those of `validation_report_path` / `merged_to_version` / `merged_at` / `rejected_reason` that are present in the file (omit absent keys; do NOT emit `null`).

A `ChangelogEntry` SHALL be one of:
- `{ kind: "transition", timestamp: str, from_status: ProposalStatus, to_status: ProposalStatus, actor: str, reason: str | null }` — for lines matching `^- (?P<ts>\S+) status: (?P<from>\w+) → (?P<to>\w+) by (?P<actor>.+?)(?: \((?P<reason>.*)\))?$`
- `{ kind: "created", timestamp: str, actor: str }` — for lines matching `^- (?P<ts>\S+) created by (?P<actor>.+)$`
- `{ kind: "raw", text: str }` — for any non-empty, non-comment, non-matching line (HTML comments and blank lines MUST be skipped)

#### Scenario: 200 with full payload
- **WHEN** an authenticated request hits `GET /api/admin/proposals/2026-04-30-vcp-volume-threshold`
- **AND** the file `proposals/2026-04-30-vcp-volume-threshold.md` exists with status `pending`, all 7 body sections, and one `created` changelog line
- **THEN** the response is HTTP 200
- **AND** `data.slug == "2026-04-30-vcp-volume-threshold"`
- **AND** `data.proposal_id == "2026-04-30-vcp-volume-threshold"`
- **AND** `data.status == "pending"`
- **AND** `data.body.description` is the verbatim `## 1.` section text
- **AND** `data.changelog` has length 1 with `kind == "created"`
- **AND** `data.extra_frontmatter` is `{}` (no extra keys present)

#### Scenario: changelog parses status transition lines
- **WHEN** the file has been transitioned `pending → validating → approved`
- **AND** the `## 8.` section therefore contains 3 lines (one created, two transition)
- **THEN** `data.changelog` has length 3
- **AND** `data.changelog[0].kind == "created"`
- **AND** `data.changelog[1].kind == "transition"` with `from_status == "pending"`, `to_status == "validating"`
- **AND** `data.changelog[2].kind == "transition"` with `from_status == "validating"`, `to_status == "approved"`

#### Scenario: changelog includes reason when present
- **WHEN** a transition line is `- 2026-05-10T15:30:00+08:00 status: validating → rejected by mark (WFA Sharpe drop > 30%)`
- **THEN** the corresponding `ChangelogEntry` has `kind == "transition"` and `reason == "WFA Sharpe drop > 30%"`

#### Scenario: detail surfaces extra_frontmatter for merged file
- **WHEN** the file has frontmatter keys `status: merged`, `merged_to_version: v3.1`, `merged_at: 2026-05-12T10:00:00+08:00`
- **THEN** `data.extra_frontmatter` equals `{"merged_to_version": "v3.1", "merged_at": "2026-05-12T10:00:00+08:00"}`
- **AND** `data.extra_frontmatter` does NOT contain `validation_report_path` or `rejected_reason`

#### Scenario: detail finds file regardless of containing sub-dir
- **WHEN** the slug `2026-05-01-x` exists only under `<proposals_root>/PENDING_REVIEW/`
- **THEN** `GET /api/admin/proposals/2026-05-01-x` returns HTTP 200 with the parsed payload
- **AND** the route does not require the slug to live at the root

---

### Requirement: Detail endpoint path-traversal validation

The detail endpoint SHALL reject any `{slug}` containing `/`, `\`, `..`, or `os.sep` with HTTP 400 and envelope `{"ok": false, "error": {"code": "invalid_input", "message": ...}}`. This validation MUST run BEFORE any disk read or call into `parse_proposal`.

The same validation MUST apply to the transition endpoint's path parameter.

#### Scenario: forward slash rejected
- **WHEN** the client requests `GET /api/admin/proposals/foo%2F..%2Fbar` (URL-decoded to `foo/..  /bar`)
- **THEN** the response is HTTP 400 with `error.code == "invalid_input"`
- **AND** no file under the proposals root is opened

#### Scenario: parent-dir traversal rejected
- **WHEN** the client requests `GET /api/admin/proposals/..%2Fsecrets`
- **THEN** the response is HTTP 400 `invalid_input`

#### Scenario: backslash rejected
- **WHEN** the client requests a slug containing a literal backslash
- **THEN** the response is HTTP 400 `invalid_input`

---

### Requirement: 404 for well-formed but missing slug

The detail endpoint SHALL return HTTP 404 with envelope `{"ok": false, "error": {"code": "not_found", "message": "proposal not found: <slug>"}}` when `{slug}` passes path-safety validation but no file `<slug>.md` exists in any of the 4 sub-locations.

#### Scenario: missing slug returns 404
- **WHEN** the client requests `GET /api/admin/proposals/2099-12-31-does-not-exist`
- **AND** no such file exists under any of the 4 directories
- **THEN** the response is HTTP 404
- **AND** `error.code == "not_found"`
- **AND** `error.message` includes the requested slug

---

### Requirement: 422 for malformed proposal body on detail

When `parse_proposal()` raises `ProposalParseError` (e.g. a missing body section), the detail endpoint SHALL return HTTP 422 with envelope `{"ok": false, "error": {"code": "malformed_proposal", "message": <safe summary>}}`. The envelope `message` MUST NOT contain a stack trace or the raw exception `__str__` value verbatim — the route SHALL emit a fixed-format string like `"proposal markdown is malformed: <field-or-section-name>"`.

#### Scenario: missing body section surfaces 422
- **WHEN** a file lacks the `## 5. 風險評估` section
- **AND** the client requests `GET /api/admin/proposals/<that-slug>`
- **THEN** the response is HTTP 422 with `error.code == "malformed_proposal"`
- **AND** the message references the offending section by name
- **AND** the response body does NOT contain the literal string `Traceback`

---

### Requirement: Transition endpoint shape and behaviour

The system SHALL expose `POST /api/admin/proposals/{slug}/transition` accepting a JSON body and returning the new path on success.

Request body schema: `{ new_status: ProposalStatus, actor: str, reason: str | null, validation_report_path: str | null, merged_to_version: str | null }`. `new_status` and `actor` are required; the other three are conditional on `new_status` per the state machine. The endpoint MUST translate string `validation_report_path` to `pathlib.Path` before calling `transition_proposal`.

The endpoint MUST be registered with `Depends(require_admin)` and MUST be the *only* HTTP method on this path; GET/PUT/DELETE on `/api/admin/proposals/{slug}/transition` SHALL return HTTP 405.

On success, the endpoint MUST return HTTP 200 with `data == { slug: str, new_status: ProposalStatus, new_path: str }` where `new_path` is the path returned by `transition_proposal()` rendered relative to the proposals root (using forward slashes regardless of host OS for client-side stability).

The endpoint MUST resolve the input file path by the same 4-directory probe as the detail endpoint (root → PENDING_REVIEW → merged → rejected); the first match wins. If no file matches, the response is HTTP 404 `not_found` (the same shape as the detail endpoint's 404).

#### Scenario: pending → validating succeeds
- **WHEN** the client POSTs `{"new_status": "validating", "actor": "mark"}` to `/api/admin/proposals/2026-04-30-x/transition`
- **AND** the file is currently at `<proposals_root>/2026-04-30-x.md` with `status: pending`
- **THEN** the response is HTTP 200
- **AND** `data.new_status == "validating"`
- **AND** `data.new_path == "2026-04-30-x.md"`
- **AND** the file's frontmatter on disk has `status: validating`
- **AND** the file's `## 8.` section has one new transition line ending in `by mark`

#### Scenario: validating → approved succeeds and moves file
- **WHEN** the client POSTs `{"new_status": "approved", "actor": "mark", "validation_report_path": "proposals/x.validation.json"}` to `/api/admin/proposals/2026-04-30-x/transition`
- **AND** the file is currently at `<proposals_root>/2026-04-30-x.md` with `status: validating`
- **THEN** the response is HTTP 200
- **AND** `data.new_path == "PENDING_REVIEW/2026-04-30-x.md"`
- **AND** the original root path no longer contains the file
- **AND** `<proposals_root>/PENDING_REVIEW/2026-04-30-x.md` exists with `status: approved` and `validation_report_path: proposals/x.validation.json` in frontmatter

#### Scenario: missing slug returns 404
- **WHEN** the client POSTs to `/api/admin/proposals/does-not-exist/transition`
- **THEN** the response is HTTP 404 with `error.code == "not_found"`

#### Scenario: GET on transition path returns 405
- **WHEN** the client sends `GET /api/admin/proposals/<any-slug>/transition`
- **THEN** the response is HTTP 405

---

### Requirement: ProposalStateError → envelope mapping

The transition endpoint SHALL catch `ProposalStateError` raised by `transition_proposal` and map by message-substring to the unified envelope as follows. The mapping MUST be defined as an ordered list `_STATE_ERROR_TO_ENVELOPE: list[tuple[str, int, str]]` in the route module and scanned in declared order; a fallback row matches any other `ProposalStateError` message and emits HTTP 500 `internal_error`.

| `ProposalStateError` substring | HTTP | envelope `code` |
|---|---|---|
| `unknown_status` | 400 | `invalid_input` |
| `illegal_transition` | 409 | `illegal_transition` |
| `missing_actor` | 400 | `invalid_input` |
| `missing_validation_report` | 400 | `invalid_input` |
| `missing_merged_to_version` | 400 | `invalid_input` |
| `missing_rejection_reason` | 400 | `invalid_input` |
| `destination_exists` | 409 | `conflict` |
| `malformed_changelog` | 422 | `unprocessable_entity` |

Each row MUST be exercised by an automated test (one `ProposalStateError` per row). The envelope `message` SHALL be the exception's `str(exc)` value.

`ProposalParseError` raised by the `parse_proposal` step (used to load the file before transitioning) MUST be mapped to HTTP 422 `malformed_proposal` per the detail-endpoint requirement.

#### Scenario: illegal_transition mapped to 409
- **WHEN** the client POSTs `{"new_status": "approved", "actor": "mark", "validation_report_path": "x"}` against a `pending` file
- **THEN** the response is HTTP 409 with `error.code == "illegal_transition"`
- **AND** the file on disk is unchanged

#### Scenario: missing required arg mapped to 400 invalid_input
- **WHEN** the client POSTs `{"new_status": "approved", "actor": "mark"}` (omitting `validation_report_path`) against a `validating` file
- **THEN** the response is HTTP 400 with `error.code == "invalid_input"`
- **AND** the message contains the substring `missing_validation_report`

#### Scenario: destination_exists mapped to 409 conflict
- **WHEN** transitioning a `validating` file to `approved` with `validation_report_path` set, and a stale `<proposals_root>/PENDING_REVIEW/<same-slug>.md` already exists
- **THEN** the response is HTTP 409 with `error.code == "conflict"`
- **AND** both source and destination files SHALL remain unchanged

#### Scenario: unknown_status mapped to 400 invalid_input
- **WHEN** the client POSTs `{"new_status": "approve", "actor": "mark"}` (typo)
- **THEN** the response is HTTP 400 with `error.code == "invalid_input"`

---

### Requirement: Bearer auth enforced on all three endpoints

All three endpoints (`GET /api/admin/proposals`, `GET /api/admin/proposals/{slug}`, `POST /api/admin/proposals/{slug}/transition`) SHALL be gated by `Depends(require_admin)`. Requests missing `Authorization` or with an invalid Bearer token MUST receive HTTP 401 with the standard auth envelope (`auth_missing` / `auth_invalid`) — the same as every other `/api/admin/*` route.

CSRF SHALL NOT be required (admin uses Bearer tokens, not cookies).

#### Scenario: missing Authorization on list
- **WHEN** the client requests `GET /api/admin/proposals` without `Authorization`
- **THEN** the response is HTTP 401 with `error.code == "auth_missing"`

#### Scenario: invalid token on transition
- **WHEN** the client POSTs to `/api/admin/proposals/x/transition` with `Authorization: Bearer wrong`
- **THEN** the response is HTTP 401 with `error.code == "auth_invalid"`
- **AND** no file is modified

---

### Requirement: Proposals root indirection

The route module SHALL expose a module-level `_PROPOSALS_ROOT_FACTORY: Callable[[], Path]` whose default returns `Settings().proposals_dir` (or `Path("proposals")` if no such field exists). The factory MUST be invoked once per request to obtain the current root, so that test scopes can override it via `monkeypatch.setattr(routes.proposals, "_PROPOSALS_ROOT_FACTORY", lambda: tmp_path / "proposals")`.

The `proposals_root` MUST NOT be readable from query parameters or the request body in production paths.

#### Scenario: production root resolves to repo path
- **WHEN** the route module is imported with default settings
- **THEN** `_PROPOSALS_ROOT_FACTORY()` returns a `Path` whose name component is `proposals`

#### Scenario: tests can patch the factory
- **WHEN** a test sets `monkeypatch.setattr(ohmystock.api.routes.proposals, "_PROPOSALS_ROOT_FACTORY", lambda: tmp_path)`
- **THEN** subsequent requests on the test client read and write proposals under `tmp_path` instead of the production dir

---

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
