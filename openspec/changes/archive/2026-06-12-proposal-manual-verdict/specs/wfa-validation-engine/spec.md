## MODIFIED Requirements

### Requirement: run_validation auto_transition parameter

`run_validation` SHALL accept a keyword-only `auto_transition: bool = True` parameter.

When `auto_transition=True`（預設）, behaviour is unchanged: non-dry-run runs write the report and drive `transition_proposal` to `approved`（pass, 搬 `PENDING_REVIEW/`）or `rejected`（fail, 搬 `rejected/`）, co-locating the report.

When `auto_transition=False` and `dry_run=False`, the engine SHALL:
- write `<slug>.validation.json` atomically next to the proposal markdown（proposals root）,
- emit `WFA_PASSED` / `WFA_FAILED` exactly as before,
- return the `ValidationReport` WITHOUT calling `transition_proposal` — the markdown stays in place with frontmatter `status: validating`.

`dry_run=True` SHALL keep precedence: no report file and no transition regardless of `auto_transition`.

#### Scenario: manual mode keeps proposal in validating
- **WHEN** `run_validation(..., dry_run=False, auto_transition=False)` completes with verdict pass or fail
- **THEN** `<root>/<slug>.validation.json` exists
- **AND** the proposal markdown remains at `<root>/<slug>.md` with frontmatter `status: validating`
- **AND** no changelog line is appended

#### Scenario: default remains auto
- **WHEN** `run_validation` is called without `auto_transition`（e.g. CLI `ohmystock validate-proposal`）
- **THEN** pass/fail still auto-transitions to `approved`/`rejected` as previously specified
