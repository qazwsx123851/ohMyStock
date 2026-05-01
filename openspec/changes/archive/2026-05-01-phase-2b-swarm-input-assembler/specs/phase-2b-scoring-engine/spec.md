## ADDED Requirements

### Requirement: Phase 2B candidates are consumable by the swarm input assembler

The system SHALL expose Phase 2B candidate rows (those with `final_score >= 65`) via a stable Python iterator/repository surface that the swarm input assembler can consume without parsing CLI output. Specifically, `ohmystock.scoring` SHALL provide a public function `iter_qualified_candidates(asof_date: str, *, threshold: float = 65.0) -> Iterable[Phase2BCandidate]` that yields `Phase2BCandidate` instances whose `final_score >= threshold`, ordered by `final_score` descending then `symbol` ascending. The function MUST return an empty iterable (not raise) when no candidates qualify.

#### Scenario: Returns qualified candidates ordered by score then symbol
- **WHEN** the scoring run for `2026-04-30` has produced candidates `[("2330", 78), ("2454", 72), ("3008", 72), ("1234", 60)]`
- **THEN** `list(iter_qualified_candidates("2026-04-30"))` returns three `Phase2BCandidate` instances in the order `[2330, 2454, 3008]`
- **AND** the candidate with `final_score == 60` is excluded

#### Scenario: Empty iterable when no qualifying candidates
- **WHEN** every candidate for `2026-04-30` has `final_score < 65`
- **THEN** `list(iter_qualified_candidates("2026-04-30"))` returns `[]`
- **AND** no exception is raised

### Requirement: Phase2BCandidate carries SEPA fields required by v3.1 input schema

`Phase2BCandidate` SHALL include SEPA fields `stage: int`, `rs_percentile: int`, `trend_template_passed: int`, `vcp_quality: Literal["none","forming","textbook","breakout"]`, and `pivot_price: float | None`, populated by the SEPA-aligned sub-scorers, so that the swarm input assembler can mirror them into `CandidateSnapshot` without further computation. These fields MUST be present (non-`None` for `stage`/`rs_percentile`/`trend_template_passed`/`vcp_quality`) on every candidate yielded by `iter_qualified_candidates`. `pivot_price` MAY be `None` only when `vcp_quality in {"none", "forming"}`.

#### Scenario: Qualified candidate has SEPA fields populated
- **WHEN** `iter_qualified_candidates("2026-04-30")` yields a candidate
- **THEN** the candidate's `stage`, `rs_percentile`, `trend_template_passed`, `vcp_quality` are all non-`None`
- **AND** if `vcp_quality in {"textbook", "breakout"}` then `pivot_price > 0`
- **AND** if `vcp_quality in {"none", "forming"}` then `pivot_price is None`
