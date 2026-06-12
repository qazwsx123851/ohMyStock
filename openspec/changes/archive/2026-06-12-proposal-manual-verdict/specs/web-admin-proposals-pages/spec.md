## MODIFIED Requirements

### Requirement: ValidationDialog manual-verdict copy

`<ValidationDialog>` SHALL describe the manual flow: running validation produces a report and keeps the proposal in `validating`; the operator reviews the report then uses Approve/Reject. The dialog description and the success toast MUST NOT claim the file was moved.

Toast copy（non-dry-run）:
- pass → `Validated: verdict=pass — 報告已產出，請審閱後 Approve/Reject`
- fail → `Validated: verdict=fail — 報告已產出（N failure(s)），請審閱後 Approve/Reject`

Dry-run toast copy is unchanged.

#### Scenario: non-dry-run toast reflects manual flow
- **WHEN** a non-dry-run validation returns verdict `fail` with 2 failures
- **THEN** the toast contains `verdict=fail`、`2 failure(s)` and `請審閱後 Approve/Reject`
- **AND** does not contain `moved to`

### Requirement: TransitionDialog approve prefills report path

When `<TransitionDialog target="approved">` opens, the `validation_report_path` input SHALL be prefilled with `<slug>.validation.json`（the manual-mode report location）. The value remains editable.

#### Scenario: approve dialog prefilled
- **WHEN** the operator opens Approve… on proposal `2026-06-01-foo`
- **THEN** the Validation report path input initial value is `2026-06-01-foo.validation.json`
