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
