# admin-skills-endpoints Specification

## Purpose
TBD - created by archiving change web-admin-skills-pages. Update Purpose after archive.
## Requirements
### Requirement: List endpoint shape and source

The system SHALL expose `GET /api/admin/skills` returning the full registry as a list of summary records, sourced from the production registry directory `src/ohmystock/skills/registry/` via `ohmystock.skills.load_skills`.

The endpoint MUST be registered with `Depends(require_admin)` and MUST wrap success in `to_success(...)` and any raised exception in `map_exception_to_envelope(...)`, matching the unified `{ok, data, error}` envelope used by every other admin endpoint.

The response `data` SHALL be a JSON object `{ "items": Skill[] }` where each `Skill` is `{ name: str, description: str, category: str, body_preview: str, body_truncated: bool, cited_specs: list[str] }`.

`body_preview` MUST equal `body[:200]` (Python codepoint slicing). `body_truncated` MUST be `len(body) > 200`. `cited_specs` MUST be returned in the order they appear in the file. Items MUST be sorted by `name` ascending (loader already does this; the endpoint does not re-sort).

#### Scenario: 200 with full registry
- **WHEN** an authenticated request hits `GET /api/admin/skills`
- **AND** `src/ohmystock/skills/registry/` contains the 10 production seed skills
- **THEN** the response is HTTP 200
- **AND** the body equals `{"ok": true, "data": {"items": [...]}}`
- **AND** `items` has 10 entries sorted alphabetically by `name`
- **AND** each entry has exactly the keys `name, description, category, body_preview, body_truncated, cited_specs`

#### Scenario: body_preview truncation flag
- **WHEN** a skill's `body` is 250 characters long
- **THEN** the corresponding item has `body_preview` length 200
- **AND** `body_truncated` is `true`

#### Scenario: short body not truncated
- **WHEN** a skill's `body` is 50 characters long
- **THEN** `body_preview` equals the full body
- **AND** `body_truncated` is `false`

#### Scenario: empty registry returns empty list
- **WHEN** the registry dir contains no `.md` files
- **THEN** the response is HTTP 200 with `data.items == []` (NOT 404)

### Requirement: Detail endpoint shape and source

The system SHALL expose `GET /api/admin/skills/{name}` returning a single skill record with full body and cited specs, sourced via `ohmystock.skills.load_skill` from the production registry directory.

The response `data` on success SHALL be `{ name: str, description: str, category: str, body: str, cited_specs: list[str] }` — the full `body` is returned, never truncated.

The endpoint MUST be registered with `Depends(require_admin)` and MUST use the same envelope wrapping as the list endpoint.

#### Scenario: 200 with full skill
- **WHEN** an authenticated request hits `GET /api/admin/skills/market-data`
- **AND** the file `src/ohmystock/skills/registry/market-data.md` parses successfully
- **THEN** the response is HTTP 200
- **AND** `data.name == "market-data"`
- **AND** `data.body` is the full Markdown body (no truncation)
- **AND** `data.cited_specs` is the list parsed from frontmatter

### Requirement: Path-traversal validation precedes filesystem access

The detail endpoint SHALL reject any `{name}` containing `/`, `\`, `..`, or `os.sep` with HTTP 400 and envelope `{"ok": false, "error": {"code": "invalid_input", "message": ...}}`. This validation MUST run BEFORE any disk read or call into the loader.

The validation token tuple MUST equal the loader's `_INVALID_NAME_TOKENS` value (`("/", "\\", "..", os.sep)`); this equality MUST be enforced by an automated test that imports both constants.

#### Scenario: forward slash rejected
- **WHEN** the client requests `GET /api/admin/skills/foo%2Fbar` (URL-decoded to `foo/bar`)
- **THEN** the response is HTTP 400 with body `{"ok": false, "error": {"code": "invalid_input", ...}}`
- **AND** no entry under the registry dir is opened

#### Scenario: parent-dir traversal rejected
- **WHEN** the client requests `GET /api/admin/skills/..%2Fsecrets`
- **THEN** the response is HTTP 400 `invalid_input`
- **AND** no entry under the registry dir is opened

#### Scenario: backslash rejected
- **WHEN** the client requests a name containing a literal backslash
- **THEN** the response is HTTP 400 `invalid_input`

### Requirement: 404 for well-formed but missing skill

The detail endpoint SHALL return HTTP 404 with envelope `{"ok": false, "error": {"code": "not_found", "message": "skill not found: <name>"}}` when `{name}` passes path-safety validation but `load_skill(...)` returns `None`.

#### Scenario: missing skill returns 404
- **WHEN** the client requests `GET /api/admin/skills/does-not-exist`
- **AND** no file `does-not-exist.md` exists in the registry dir
- **THEN** the response is HTTP 404
- **AND** `error.code == "not_found"`
- **AND** `error.message` includes the requested name

### Requirement: Bearer auth enforced on both endpoints

Both endpoints SHALL be gated by `Depends(require_admin)`. Requests missing the `Authorization` header or with an invalid Bearer token MUST receive HTTP 401 with the standard auth envelope (`auth_missing` / `auth_invalid`) — the same behaviour as every other `/api/admin/*` route.

#### Scenario: missing Authorization
- **WHEN** the client requests `GET /api/admin/skills` without `Authorization`
- **THEN** the response is HTTP 401 with `error.code == "auth_missing"`

#### Scenario: invalid token
- **WHEN** the client requests `GET /api/admin/skills/market-data` with `Authorization: Bearer wrong`
- **THEN** the response is HTTP 401 with `error.code == "auth_invalid"`

### Requirement: Loader errors map to 500 envelope

If `load_skills` or `load_skill` raises `SkillLoadError` (e.g. malformed frontmatter on a deployed file), the endpoint MUST NOT leak the traceback. It SHALL map the exception via `map_exception_to_envelope(...)` to a 500 response with `ok: false` and `error.code == "internal_error"` (or whatever code the shared mapper emits for unexpected exceptions), and the message SHALL be the safe string from the mapper.

#### Scenario: malformed skill file surfaced as 500
- **WHEN** a skill file in the registry has invalid YAML frontmatter
- **AND** the client requests `GET /api/admin/skills`
- **THEN** the response is HTTP 500 with `ok: false`
- **AND** the envelope does not contain a stack trace or the raw `SkillLoadError` `__str__` payload

### Requirement: Registry directory is hardcoded

The endpoint module SHALL resolve the registry directory once at import time as a module-level constant `_REGISTRY_DIR` pointing at `src/ohmystock/skills/registry/`. The directory MUST NOT be readable from `Settings`, environment variables, or query parameters in production paths.

Tests MAY override `_REGISTRY_DIR` via `monkeypatch.setattr` to point at a temporary directory.

#### Scenario: production registry resolves to repo path
- **WHEN** the route module is imported
- **THEN** `_REGISTRY_DIR` equals the absolute path of `<repo>/src/ohmystock/skills/registry`
- **AND** that directory contains the 10 seed `.md` files

#### Scenario: tests can patch the constant
- **WHEN** a test sets `monkeypatch.setattr(ohmystock.api.routes.skills, "_REGISTRY_DIR", tmp_path)`
- **THEN** subsequent requests on the test client load from `tmp_path` instead of the production dir

### Requirement: No SSE, no write methods

The capability SHALL NOT introduce any SSE event types and SHALL NOT register any HTTP method other than `GET` on `/api/admin/skills` or `/api/admin/skills/{name}`. POST/PUT/PATCH/DELETE on these paths MUST return HTTP 405.

#### Scenario: PUT not allowed
- **WHEN** the client sends `PUT /api/admin/skills/market-data` with any body
- **THEN** the response is HTTP 405

#### Scenario: POST not allowed
- **WHEN** the client sends `POST /api/admin/skills`
- **THEN** the response is HTTP 405

