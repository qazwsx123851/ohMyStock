## MODIFIED Requirements

### Requirement: Validate endpoint runs in manual-verdict mode

`POST /api/admin/proposals/{slug:path}/validate` SHALL call `run_validation` with `auto_transition=False` unconditionally. The request body（`ValidateRequest`, `extra="forbid"`）is unchanged — no new field is exposed.

For a non-dry-run 200 response the envelope `data` SHALL be:

- `verdict` — `"pass"` or `"fail"`（unchanged）
- `new_status` — always `"validating"`（the proposal is NOT moved）
- `new_path` — always `null`
- `report_path` — `"<slug>.validation.json"`（forward-slash, relative to proposals root）
- `deltas` / `failures` — unchanged

Dry-run responses are unchanged（`new_status: "validating"`, `new_path: null`, `report_path: null`）.

Human verdict confirmation then uses the existing `POST .../transition` endpoint over the legal edges `validating → approved`（requires `validation_report_path`）and `validating → rejected`（requires `reason`）.

#### Scenario: pass verdict no longer moves the file
- **WHEN** a non-dry-run validate completes with verdict `pass`
- **THEN** the response has `new_status: "validating"`, `new_path: null`, `report_path: "<slug>.validation.json"`
- **AND** `<root>/<slug>.md` still exists with frontmatter `status: validating`
- **AND** `<root>/PENDING_REVIEW/<slug>.md` does NOT exist

#### Scenario: fail verdict no longer moves the file
- **WHEN** a non-dry-run validate completes with verdict `fail`
- **THEN** the response has `new_status: "validating"`, `new_path: null`
- **AND** `<root>/rejected/<slug>.md` does NOT exist
- **AND** the operator can subsequently `POST .../transition` to `rejected` with a reason
