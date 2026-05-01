## ADDED Requirements

### Requirement: build_entry_decision_input is the sole assembler entry point

The system SHALL expose a single public function `build_entry_decision_input(candidate, market, portfolio, journal_stats, rules_digest, available_tools, available_skills, *, trigger_at)` in `ohmystock.swarm.runner` that returns an `EntryDecisionInput` instance whose JSON serialization matches `docs/llm-decision-schema.md` §1 (v3.1) byte-for-byte for the same inputs. The function MUST be deterministic: given identical inputs (including `trigger_at`), repeated calls MUST produce the same `EntryDecisionInput.model_dump(mode="json")`. The function MUST NOT perform network or database I/O — all upstream data MUST be supplied via the snapshot parameters.

#### Scenario: Same inputs produce byte-identical JSON
- **WHEN** `build_entry_decision_input` is called twice with identical `candidate`, `market`, `portfolio`, `journal_stats`, `rules_digest`, `available_tools`, `available_skills`, and `trigger_at="2026-04-30T14:30:00+08:00"`
- **THEN** both calls return objects whose `.model_dump(mode="json", by_alias=True)` are equal
- **AND** the JSON contains `"input_schema_version": "v3.1"`

#### Scenario: Function performs no I/O
- **WHEN** `build_entry_decision_input` is called inside a context that monkeypatches `socket.socket`, `httpx.Client`, and `sqlite3.connect` to raise on use
- **THEN** the function still returns successfully

### Requirement: EntryDecisionInput Pydantic contract mirrors schema v3.1

The system SHALL provide Pydantic v2 models `CandidateSnapshot`, `ExistingPosition`, `MarketContext`, `RulesDigest`, and `EntryDecisionInput` in `ohmystock.swarm.models`, importable as `from ohmystock.swarm import EntryDecisionInput`. `EntryDecisionInput` MUST have fields exactly matching `docs/llm-decision-schema.md` §1: `input_schema_version: Literal["v3.1"]`, `decision_id: str`, `trigger_at: str`, `candidate: CandidateSnapshot`, `market_context: MarketContext`, `rules_summary: RulesDigest`, `available_tools: list[str]`, `available_skills: list[str]`. `CandidateSnapshot` MUST include all SEPA fields (`stage`, `rs_percentile`, `trend_template_passed`, `vcp_quality`, `pivot_price`) with the constraints listed below.

#### Scenario: Round-trip from llm-decision-schema sample JSON
- **WHEN** `EntryDecisionInput.model_validate_json(sample_json)` is called with the exact JSON example shown in `docs/llm-decision-schema.md` §1
- **THEN** validation succeeds without raising
- **AND** the model instance's `.model_dump(mode="json")` equals the original JSON object (after key ordering)

#### Scenario: Unknown fields are rejected
- **WHEN** `EntryDecisionInput.model_validate({...valid payload..., "extra_field": 1})` is called
- **THEN** Pydantic raises `ValidationError` with a message identifying the unexpected key

#### Scenario: input_schema_version mismatch is rejected
- **WHEN** `EntryDecisionInput.model_validate({...valid payload..., "input_schema_version": "v3.0"})` is called
- **THEN** Pydantic raises `ValidationError`

### Requirement: SEPA field validation

`CandidateSnapshot` SHALL enforce SEPA invariants. `stage` MUST be one of `1, 2, 3, 4`. `rs_percentile` MUST be an integer in `[0, 99]`. `trend_template_passed` MUST be an integer in `[0, 8]`. `vcp_quality` MUST be one of `"none" | "forming" | "textbook" | "breakout"`. `pivot_price` MUST be `None` if and only if `vcp_quality in {"none", "forming"}`; otherwise it MUST be a positive float.

#### Scenario: pivot_price required when vcp_quality is breakout
- **WHEN** `CandidateSnapshot(..., vcp_quality="breakout", pivot_price=None, ...)` is constructed
- **THEN** Pydantic raises `ValidationError` referencing `pivot_price`

#### Scenario: pivot_price forbidden when vcp_quality is forming
- **WHEN** `CandidateSnapshot(..., vcp_quality="forming", pivot_price=832.0, ...)` is constructed
- **THEN** Pydantic raises `ValidationError` referencing `pivot_price`

#### Scenario: rs_percentile out of range
- **WHEN** `CandidateSnapshot(..., rs_percentile=100, ...)` is constructed
- **THEN** Pydantic raises `ValidationError`

### Requirement: Deterministic ordering of list fields

The assembler SHALL sort `market_context.existing_positions` by `(-exposure_pct, symbol)` and SHALL sort `available_tools` and `available_skills` ascending by string comparison before returning. The `same_sector_count` field SHALL be derived as the count of `existing_positions` whose `sector` equals the candidate's sector (resolved via portfolio metadata), excluding the candidate itself.

#### Scenario: existing_positions sorted by exposure descending then symbol ascending
- **WHEN** `build_entry_decision_input` receives a portfolio snapshot with positions `[{"symbol":"2317","exposure_pct":12.0},{"symbol":"2454","exposure_pct":18.0},{"symbol":"3008","exposure_pct":18.0}]`
- **THEN** the resulting `market_context.existing_positions` is ordered `[2454, 3008, 2317]`

#### Scenario: same_sector_count counts existing positions in candidate's sector
- **WHEN** the candidate's sector is "半導體" and `existing_positions` contains 2 entries with sector "半導體" and 1 with sector "電子組裝"
- **THEN** `market_context.same_sector_count == 2`

### Requirement: decision_id format

The assembler SHALL construct `decision_id` as `f"dec_{trigger_at_normalized}_{symbol}"` where `trigger_at_normalized` is the `trigger_at` ISO-8601 string with `:` and the `+08:00` suffix removed (e.g., `2026-04-30T14:30:00+08:00` → `2026-04-30T14-30-00`). The function MUST NOT generate or read the current time itself; `trigger_at` MUST be provided by the caller.

#### Scenario: decision_id formatting
- **WHEN** `build_entry_decision_input` is called with `candidate.symbol == "2330"` and `trigger_at == "2026-04-30T14:30:00+08:00"`
- **THEN** the returned object's `.decision_id == "dec_2026-04-30T14-30-00_2330"`

#### Scenario: trigger_at must be timezone-aware
- **WHEN** `build_entry_decision_input` is called with `trigger_at == "2026-04-30T14:30:00"` (no offset)
- **THEN** `AssemblerInputError` is raised referencing `trigger_at`

### Requirement: Score-threshold gate

The assembler SHALL raise `AssemblerInputError` if the input `Phase2BCandidate.final_score < 65`. The function MUST NOT silently downgrade or default the candidate; the upstream Phase 2B scoring pipeline is responsible for filtering before invoking the assembler, but the assembler enforces the contract.

#### Scenario: Below threshold raises
- **WHEN** `build_entry_decision_input` is called with a candidate whose `final_score == 64.9`
- **THEN** `AssemblerInputError` is raised with a message containing "score below threshold"

#### Scenario: Exactly at threshold succeeds
- **WHEN** `build_entry_decision_input` is called with a candidate whose `final_score == 65`
- **THEN** the function returns successfully and `.candidate.final_score == 65`

### Requirement: Missing SEPA field raises

The assembler SHALL raise `AssemblerInputError` if any of `stage`, `rs_percentile`, `trend_template_passed`, `vcp_quality`, or `pivot_price` (when required by `vcp_quality`) is `None` on the input candidate.

#### Scenario: vcp_quality missing
- **WHEN** the input candidate has `vcp_quality is None`
- **THEN** `AssemblerInputError` is raised with a message containing "vcp_quality"

### Requirement: RulesDigest is loaded from a curated repo file

The system SHALL load `RulesDigest` from `docs/_rules_digest.json`, a curated file checked into the repository whose `must_have` field has exactly 3 entries (the SEPA three pillars from `docs/workflow-cheatsheet.md` §6.3) and whose `bonus_items` field has exactly 8 entries (from §6.4). The loader function SHALL be `ohmystock.swarm.load_rules_digest()`. The loader MUST raise `RulesDigestError` if the file is missing, malformed JSON, or violates the count invariants.

#### Scenario: Valid digest loads
- **WHEN** `load_rules_digest()` is called and `docs/_rules_digest.json` contains exactly 3 must_have and 8 bonus_items
- **THEN** the function returns a `RulesDigest` with `len(must_have) == 3` and `len(bonus_items) == 8`

#### Scenario: Wrong count raises
- **WHEN** `docs/_rules_digest.json` has 2 entries in `must_have`
- **THEN** `load_rules_digest()` raises `RulesDigestError`

### Requirement: available_tools and available_skills discovery

The system SHALL provide `discover_available_tools()` returning a sorted `list[str]` of registered tool names from `ohmystock.tools._registry`, and `discover_available_skills()` returning a sorted `list[str]` of skill identifiers (e.g., `"technical/breakout"`) derived from each skill's YAML frontmatter `name` under `src/ohmystock/skills/`. Both functions MUST be importable as `from ohmystock.swarm import discover_available_tools, discover_available_skills`.

#### Scenario: discover_available_tools returns registered tool names sorted
- **WHEN** the tool registry contains `chip_data_tool`, `market_data_tool`, `pattern_recognition_tool`
- **THEN** `discover_available_tools()` returns `["chip_data_tool", "market_data_tool", "pattern_recognition_tool"]`

#### Scenario: discover_available_skills returns sorted skill identifiers
- **WHEN** the skills directory contains `technical/breakout.yaml` and `chip/three-major-investors.yaml`
- **THEN** `discover_available_skills()` returns `["chip/three-major-investors", "technical/breakout"]`

### Requirement: CLI subcommand for offline assembly

The system SHALL provide a CLI subcommand `oms assemble-entry-input <symbol> [--asof YYYY-MM-DD] [--out PATH] [--trigger-at ISO-8601]` registered in `ohmystock.cli`. Without `--out`, the command prints the assembled JSON to stdout. With `--out`, it writes the JSON to the given path. The exit code MUST be `0` on success, non-zero on `AssemblerInputError` with a stderr message identifying the cause.

#### Scenario: Successful assembly prints JSON to stdout
- **WHEN** `oms assemble-entry-input 2330 --asof 2026-04-30 --trigger-at 2026-04-30T14:30:00+08:00` is invoked and the symbol's candidate has `final_score >= 65`
- **THEN** the CLI exits 0 and stdout contains a JSON object with `"input_schema_version": "v3.1"` and `"candidate": {"symbol": "2330", ...}`

#### Scenario: Score below threshold returns non-zero
- **WHEN** the candidate's `final_score < 65`
- **THEN** the CLI exits non-zero and stderr contains "score below threshold"
