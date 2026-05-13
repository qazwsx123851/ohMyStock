# admin-reviews-endpoints Specification

## Purpose
TBD - created by archiving change admin-reviews-endpoints-and-pages. Update Purpose after archive.
## Requirements
### Requirement: List endpoint shape and source

The system SHALL expose `GET /api/admin/reviews` returning the contents of `<reviews_root>/_index.json`'s `reviews[]` array, sliced by pagination and optionally filtered by `?kind=`. The endpoint MUST NOT walk the filesystem to discover review folders — `_index.json` is the single source of truth (per `post-trade-review-pipeline` Requirement "reviews/_index.json").

The endpoint MUST be registered with `Depends(require_admin)` and MUST wrap success in `to_success(...)` and unhandled exceptions in `map_exception_to_envelope(...)`, matching the unified `{ok, data, error}` envelope.

The response `data` SHALL be `{ items: ReviewSummary[], total: int, limit: int, offset: int, has_more: bool }` where each `ReviewSummary` is `{ review_id: str, kind: "monthly" | "quarterly" | "forced" | "manual", period: { from: str, to: str }, trade_count: int, win_rate: float, pf: float, proposals_created: int, completed_at: str }`. Items MUST be sorted by `completed_at` descending, ties broken by `review_id` descending (stable across runs).

When `<reviews_root>/_index.json` does not exist OR exists but contains `reviews: []`, the endpoint MUST return HTTP 200 with `data == { items: [], total: 0, limit: <effective>, offset: 0, has_more: false }`. It MUST NOT return 404.

When `<reviews_root>/_index.json` exists but is not valid JSON, the endpoint MUST return HTTP 500 with `error.code == "internal_error"` and a fixed message `"reviews index is corrupted"` (no stack trace, no raw `JSONDecodeError.msg` leak).

#### Scenario: 200 with mixed-kind index
- **WHEN** an authenticated request hits `GET /api/admin/reviews`
- **AND** `_index.json` contains 3 reviews: one `manual` from `2026-04`, one `monthly` from `2026-03`, one `quarterly` from `2026-Q1`
- **THEN** the response is HTTP 200
- **AND** the body matches `{"ok": true, "data": {"items": [...], "total": 3, "limit": 50, "offset": 0, "has_more": false}}`
- **AND** every item has exactly the 8 keys listed above

#### Scenario: items sorted by completed_at desc
- **WHEN** the index contains rows with `completed_at` of `2026-04-30T19:42:18+08:00`, `2026-03-31T20:14:00+08:00`, `2026-05-12T10:00:00+08:00`
- **THEN** `items[0].completed_at` SHALL be the `2026-05-12` row
- **AND** `items[1].completed_at` SHALL be the `2026-04-30` row
- **AND** `items[2].completed_at` SHALL be the `2026-03-31` row

#### Scenario: missing _index.json returns empty list, not 404
- **WHEN** `<reviews_root>/_index.json` does not exist on disk
- **THEN** the response is HTTP 200
- **AND** `data.items == []` and `data.total == 0` and `data.has_more is false`

#### Scenario: empty reviews array returns empty list
- **WHEN** `_index.json` exists with body `{"schema_version": "v3.0", "reviews": []}`
- **THEN** the response is HTTP 200 with `data.items == []` and `data.total == 0`

#### Scenario: corrupted _index.json returns 500
- **WHEN** `_index.json` exists with body `not valid json {{`
- **THEN** the response is HTTP 500 with `error.code == "internal_error"`
- **AND** `error.message == "reviews index is corrupted"`
- **AND** the response body does NOT contain the literal string `Traceback`

---

### Requirement: List endpoint kind filter

The list endpoint SHALL accept an optional `?kind=` query parameter. When present, its value MUST be one of `monthly` / `quarterly` / `forced` / `manual`; any other value MUST yield HTTP 400 with `error.code == "invalid_input"` and a message naming the offending parameter.

When `?kind=` is set, the filter SHALL apply in-memory after reading the index. `total` SHALL reflect the count after filtering (not the index's total row count).

#### Scenario: kind filter narrows to one kind
- **WHEN** `_index.json` contains 4 reviews (one of each kind), and the client sends `?kind=monthly`
- **THEN** `data.items` has length 1
- **AND** the single item has `kind == "monthly"`
- **AND** `data.total == 1`

#### Scenario: invalid kind rejected
- **WHEN** the client sends `?kind=weekly`
- **THEN** the response is HTTP 400 with `error.code == "invalid_input"`
- **AND** the error message names `kind` as the offending parameter

#### Scenario: kind filter with zero matches returns empty
- **WHEN** `_index.json` has no `forced` rows and the client sends `?kind=forced`
- **THEN** the response is HTTP 200 with `data.items == []` and `data.total == 0`

---

### Requirement: List endpoint pagination

The list endpoint SHALL accept `?limit=` (default 50, MUST clamp silently to ≤200) and `?offset=` (default 0).

`offset` < 0 MUST yield HTTP 400 with `error.code == "invalid_input"`. `limit` < 1 MUST yield HTTP 400 with `error.code == "invalid_input"`. `limit` > 200 MUST be clamped silently to 200 (no error, no warning header).

`has_more` SHALL equal `(offset + len(items)) < total`. `total` SHALL be the count after any `?kind=` filter, BEFORE pagination.

#### Scenario: limit clamps to 200
- **WHEN** the client sends `?limit=10000`
- **THEN** the response uses `data.limit == 200`
- **AND** at most 200 items are returned

#### Scenario: negative offset rejected
- **WHEN** the client sends `?offset=-1`
- **THEN** the response is HTTP 400 with `error.code == "invalid_input"`

#### Scenario: limit zero rejected
- **WHEN** the client sends `?limit=0`
- **THEN** the response is HTTP 400 with `error.code == "invalid_input"`

#### Scenario: has_more reflects remaining
- **WHEN** `_index.json` has 75 rows and the client sends `?limit=50&offset=0`
- **THEN** `data.items` has length 50, `data.total == 75`, `data.has_more is true`
- **WHEN** the client sends `?limit=50&offset=50`
- **THEN** `data.items` has length 25, `data.total == 75`, `data.has_more is false`

---

### Requirement: Detail endpoint shape and source

The system SHALL expose `GET /api/admin/reviews/{review_id}` returning a composite payload for a single review.

The endpoint MUST be registered with `Depends(require_admin)` and MUST use the same envelope wrapping as the list endpoint.

On success, `data` SHALL be:

```
{
  review_id: str,
  partial: bool,
  summary: ReviewSummary | null,            // _index.json row, null if not in index
  files: {
    data_json:           { exists: bool, path: str | null },
    attribution_json:    { exists: bool, path: str | null },
    metrics_json:        { exists: bool, path: str | null },
    critique_md:         { exists: bool, path: str | null },
    report_md:           { exists: bool, path: str | null },
    proposals_created_md:{ exists: bool, path: str | null }
  },
  report: str | null,                       // full text of report.md, null if file absent
  metrics_overall: {
    win_rate: float, profit_factor: float, expectancy_pct: float,
    max_drawdown_pct: float, max_consecutive_loss: int, avg_hold_days: float
  } | null,                                 // null if metrics.json absent
  proposals_created: ProposalCreatedRow[]   // [] if proposals_created.md absent or empty
}
```

`ProposalCreatedRow` SHALL be `{ slug: str, status: str, priority: str, target: str }`, parsed from the markdown table in `proposals_created.md`. Rows the route fails to parse MUST be skipped (logged warning).

`path` strings SHALL be forward-slash relative to `<reviews_root>` (e.g. `"manual-2026-04-01-to-2026-04-30/report.md"`), regardless of host OS.

`partial` MUST be `true` when ANY of the 6 standard files (`data.json`, `attribution.json`, `metrics.json`, `critique.md`, `report.md`, `proposals_created.md`) is missing OR `summary` is `null`. Otherwise `partial` MUST be `false`.

#### Scenario: 200 with complete review
- **WHEN** the client requests `GET /api/admin/reviews/manual-2026-04-01-to-2026-04-30`
- **AND** the directory exists with all 6 files and `_index.json` has a matching row
- **THEN** the response is HTTP 200
- **AND** `data.review_id == "manual-2026-04-01-to-2026-04-30"`
- **AND** `data.partial is false`
- **AND** `data.summary` is the `_index.json` row (8 keys per ReviewSummary)
- **AND** every key in `data.files` has `exists: true` with a non-null `path`
- **AND** `data.report` is a non-empty string equal to `report.md` contents
- **AND** `data.metrics_overall` has the 6 listed keys

#### Scenario: 200 with partial review (critique crash)
- **WHEN** the directory exists with only `data.json`, `attribution.json`, `metrics.json` (pipeline crashed in critic node)
- **AND** `_index.json` has no row for that review_id
- **THEN** the response is HTTP 200
- **AND** `data.partial is true`
- **AND** `data.summary is null`
- **AND** `data.files.data_json.exists is true`, `data.files.critique_md.exists is false`
- **AND** `data.report is null` (report.md missing)
- **AND** `data.metrics_overall` is populated from `metrics.json`

#### Scenario: proposals_created.md parsed into rows
- **WHEN** `proposals_created.md` contains a markdown table with 2 rows pointing to `../../proposals/2026-04-30-vcp-volume-threshold.md` (pending/high/cheatsheet §6.4) and `../../proposals/2026-04-30-time-stop-extend-vcp.md` (pending/medium/cheatsheet §7.B)
- **THEN** `data.proposals_created` has length 2
- **AND** `data.proposals_created[0].slug == "2026-04-30-vcp-volume-threshold"`
- **AND** `data.proposals_created[0].priority == "high"`
- **AND** `data.proposals_created[1].slug == "2026-04-30-time-stop-extend-vcp"`

#### Scenario: empty proposals_created.md returns empty list
- **WHEN** `proposals_created.md` contains only the text `本期無提案`
- **THEN** `data.proposals_created` equals `[]`

#### Scenario: malformed proposals_created.md does NOT fail the request
- **WHEN** `proposals_created.md` exists but is missing the table header / has only stray text
- **THEN** the response is HTTP 200
- **AND** `data.proposals_created` equals `[]`
- **AND** a `logger.warning` line was emitted referencing the malformed file path

---

### Requirement: Detail endpoint path-traversal validation

The detail endpoint SHALL reject any `{review_id}` containing `/`, `\`, `..`, or `os.sep` with HTTP 400 and envelope `{"ok": false, "error": {"code": "invalid_input", "message": ...}}`. This validation MUST run BEFORE any disk read.

The route module MUST declare a private constant `_INVALID_NAME_TOKENS` listing the forbidden tokens. An invariant test SHALL assert this constant has the same contents (as a set) as `ohmystock.proposal.loader._INVALID_NAME_TOKENS` (or its equivalent constant on the proposals route module), so divergence between the two security policies is caught at test time.

#### Scenario: forward slash rejected
- **WHEN** the client requests `GET /api/admin/reviews/foo%2F..%2Fbar`
- **THEN** the response is HTTP 400 with `error.code == "invalid_input"`
- **AND** no file under the reviews root is opened

#### Scenario: parent-dir traversal rejected
- **WHEN** the client requests `GET /api/admin/reviews/..%2Fsecrets`
- **THEN** the response is HTTP 400 `invalid_input`

#### Scenario: backslash rejected
- **WHEN** the client requests a review_id containing a literal backslash
- **THEN** the response is HTTP 400 `invalid_input`

---

### Requirement: 404 for missing review

The detail endpoint SHALL return HTTP 404 with envelope `{"ok": false, "error": {"code": "not_found", "message": "review not found: <review_id>"}}` when `{review_id}` passes path-safety validation, but BOTH the corresponding directory `<reviews_root>/<review_id>/` does NOT exist AND `_index.json` has no row with that `review_id`.

The endpoint MUST NOT return 404 if EITHER the directory exists OR the `_index.json` row exists (one alone is enough to qualify as "partial" per the previous requirement).

#### Scenario: neither dir nor index row → 404
- **WHEN** the client requests `GET /api/admin/reviews/manual-2099-12-31-to-2099-12-31`
- **AND** no such directory exists AND `_index.json` has no matching row
- **THEN** the response is HTTP 404 with `error.code == "not_found"`
- **AND** `error.message` includes the requested review_id

#### Scenario: directory only → 200 partial
- **WHEN** the directory exists but `_index.json` has no row
- **THEN** the response is HTTP 200 with `data.partial is true` and `data.summary is null`

#### Scenario: index row only → 200 partial
- **WHEN** `_index.json` has a row but the directory has been removed by hand
- **THEN** the response is HTTP 200 with `data.partial is true` and all `data.files.*.exists` are false

---

### Requirement: Bearer auth enforced on both endpoints

Both endpoints (`GET /api/admin/reviews`, `GET /api/admin/reviews/{review_id}`) SHALL be gated by `Depends(require_admin)`. Requests missing `Authorization` or with an invalid Bearer token MUST receive HTTP 401 with the standard auth envelope (`auth_missing` / `auth_invalid`).

#### Scenario: missing Authorization on list
- **WHEN** the client requests `GET /api/admin/reviews` without `Authorization`
- **THEN** the response is HTTP 401 with `error.code == "auth_missing"`

#### Scenario: invalid token on detail
- **WHEN** the client requests `GET /api/admin/reviews/x` with `Authorization: Bearer wrong`
- **THEN** the response is HTTP 401 with `error.code == "auth_invalid"`
- **AND** no file under the reviews root is opened

---

### Requirement: Reviews root indirection

The route module SHALL expose a module-level `_REVIEWS_ROOT_FACTORY: Callable[[], Path]` whose default returns `Settings().reviews_dir` (or `Path("reviews")` if no such field exists). The factory MUST be invoked once per request to obtain the current root, so that test scopes can override it via `monkeypatch.setattr(routes.reviews, "_REVIEWS_ROOT_FACTORY", lambda: tmp_path / "reviews")`.

The `reviews_root` MUST NOT be readable from query parameters or the request body in production paths.

#### Scenario: production root resolves to repo path
- **WHEN** the route module is imported with default settings
- **THEN** `_REVIEWS_ROOT_FACTORY()` returns a `Path` whose name component is `reviews`

#### Scenario: tests can patch the factory
- **WHEN** a test sets `monkeypatch.setattr(ohmystock.api.routes.reviews, "_REVIEWS_ROOT_FACTORY", lambda: tmp_path)`
- **THEN** subsequent requests on the test client read reviews under `tmp_path` instead of the production dir

