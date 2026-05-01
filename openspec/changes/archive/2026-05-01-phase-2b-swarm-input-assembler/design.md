## Context

Phase 2B scoring (shipped + deferred sub-scorers) writes `Phase2BCandidate` rows. Phase 3 — `entry_decision_team` swarm with bull / bear / rule_checker / risk_simulator / pm_conclusion nodes — needs a single shared input object so each node sees identical context. `docs/design-zh-TW.md` §4.7.0 already declares the assembler the SSOT and points at `docs/llm-decision-schema.md` §1 for the JSON shape (v3.1, with SEPA fields).

Today the repo has:
- `src/ohmystock/scoring/` producing `Phase2BCandidate` (`final_score`, `tech_subtotal`, `chip_subtotal`, `fund_subtotal`, `sent_subtotal`, `subscores[]`, `risk_off_applied`, `classification`).
- `src/ohmystock/swarm/__init__.py` — empty package, no runner yet.
- `strategies/risk_gate.py`, `journal/`, `tools/_registry.py`, `skills/` YAML — all callable from the assembler.
- No `decider/` or `swarm/runner.py` module yet; no `EntryDecisionInput` Pydantic class.

Constraint: `EntryDecisionInput` JSON shape MUST match `llm-decision-schema.md` §1 exactly (v3.1). The schema is also referenced by Phase 3's `pm_conclusion` system prompt — drift breaks both contract tests and live decisions.

Stakeholder: solo developer + LLM agents. No team; the bar is "future-me reads cheatsheet §6.3/§6.4 and trusts the digest matches".

## Goals / Non-Goals

**Goals:**
- One pure function `build_entry_decision_input(...)` that is deterministic given its inputs (same inputs → same JSON, byte-identical) — testable without network or DB.
- Strict Pydantic model `EntryDecisionInput` matching `llm-decision-schema.md` §1; assembler MUST `model_dump(mode="json")` to a payload that round-trips through that model.
- Clear separation between **adapters** (slow, side-effecting: portfolio fetch, journal queries, market index fetch) and the **pure assembler** (no I/O). Adapters live behind small interfaces so tests can swap them.
- Cheatsheet rules digest is loaded once at process start and frozen as an immutable object; not re-read per candidate.
- CLI subcommand for offline fixture capture (`oms assemble-entry-input <symbol>`), used both by humans and by snapshot tests.

**Non-Goals:**
- Calling Claude / running the swarm — that's Phase 3.
- Persisting assembled inputs (the swarm runner persists, not the assembler).
- Defining the LLM **output** schema — already in `llm-decision-schema.md` §2.
- Modifying Phase 2B scoring math.
- API endpoint exposure (Phase 3 owns `/api/decisions`).

## Decisions

### D1. Module layout
Place the assembler under `src/ohmystock/swarm/` since `design-zh-TW.md` §4.7.0 specifies `swarm/runner.py::build_entry_decision_input`. Pydantic models go in `src/ohmystock/swarm/models.py` (not `decider/`) — keeps the swarm input/output contract co-located with the runner. Phase 3's LLM-output models can later live under `src/ohmystock/decider/` without confusion.

```
src/ohmystock/swarm/
├── __init__.py
├── runner.py                # public: build_entry_decision_input()
├── _input_assembler.py      # pure assembly logic
├── _rules_digest.py         # cheatsheet §6.3/§6.4/§6.6 → RulesDigest
├── models.py                # EntryDecisionInput + Pydantic dependencies
└── _adapters.py             # MarketSnapshotAdapter, PortfolioSnapshotAdapter, JournalStatsAdapter (Protocols + default impls)
```

Alternatives considered:
- `src/ohmystock/decider/` — rejected because §4.7.0 explicitly names `swarm/runner.py` as the owner.
- One big `assembler.py` — rejected: rules digest, adapters, and pure assembly have very different test needs.

### D2. EntryDecisionInput shape: strict mirror of llm-decision-schema.md §1 v3.1
We define exactly the fields shown in §1 — no additions, no renames. Snapshot test pins the field set so future drift is loud.

```python
class CandidateSnapshot(BaseModel):
    symbol: str
    name: str
    final_score: int                       # rounded from Phase2BCandidate.final_score
    tech_score: int
    chip_score: int
    fundamental_score: int
    sentiment_score: int
    ema20_distance_pct: float
    atr_14_pct: float
    current_price: float
    stage: Literal[1, 2, 3, 4]
    rs_percentile: int                     # 0..99
    trend_template_passed: int             # 0..8
    vcp_quality: Literal["none", "forming", "textbook", "breakout"]
    pivot_price: float | None
    distance_from_52w_high_pct: float
    distance_from_52w_low_pct: float

class ExistingPosition(BaseModel):
    symbol: str
    sector: str
    exposure_pct: float

class MarketContext(BaseModel):
    risk_off: bool
    monthly_pnl_pct: float
    recent_20_winrate: float               # 0..1
    consecutive_loss: int
    existing_positions: list[ExistingPosition]
    total_exposure_pct: float
    same_sector_count: int

class RulesDigest(BaseModel):
    must_have: list[str]                   # exactly 3 items (SEPA three pillars)
    bonus_items: list[str]                 # 8 items per cheatsheet §6.4

class EntryDecisionInput(BaseModel):
    input_schema_version: Literal["v3.1"] = "v3.1"
    decision_id: str                       # dec_<iso8601>_<symbol>
    trigger_at: str                        # ISO 8601 with +08:00
    candidate: CandidateSnapshot
    market_context: MarketContext
    rules_summary: RulesDigest
    available_tools: list[str]
    available_skills: list[str]
```

Validation:
- `pivot_price is None` ⇔ `vcp_quality in {"none","forming"}`; otherwise must be `> 0`.
- `existing_positions` must be sorted by `(-exposure_pct, symbol)` so output is deterministic.
- `available_tools` and `available_skills` sorted ascending — same reason.
- `decision_id` format `dec_YYYY-MM-DDTHH-MM-SS_<symbol>` (colons replaced with `-` for filesystem safety).

### D3. Adapters as Protocols
Each adapter is a `typing.Protocol` so tests can pass fakes without monkeypatching globals.

```python
class MarketSnapshotProvider(Protocol):
    def get(self) -> MarketSnapshot: ...

class PortfolioSnapshotProvider(Protocol):
    def get(self) -> PortfolioSnapshot: ...

class JournalStatsProvider(Protocol):
    def recent_winrate(self, n: int = 20) -> float: ...
    def consecutive_loss(self) -> int: ...
```

Default implementations live in `_adapters.py` and wrap the existing tools (`market_data_tool`, `portfolio_tool`, `trade_journal_tool`). The assembler itself accepts the snapshots as data — never calls a tool directly. This keeps `build_entry_decision_input()` pure.

### D4. RulesDigest source
The cheatsheet is in `docs/workflow-cheatsheet.md`. We do **not** parse markdown at runtime — too brittle. Instead we curate `docs/_rules_digest.json` (or `.yaml`) checked into the repo, generated by a small one-shot script (`scripts/build_rules_digest.py`) that reads the cheatsheet sections § 6.3 / § 6.4 and writes structured data. The digest file ships with the repo; the loader simply `json.load`s it.

Why this over a generic markdown parser:
- Cheatsheet section headings change; regex parsing rots.
- A curated JSON gets reviewed in PRs alongside cheatsheet edits — same diff, same eyes.
- One-shot script keeps the parsing logic out of production code paths.

The digest file is the SSOT for what the LLM sees as `rules_summary`. CI test checks `len(must_have) == 3` and `len(bonus_items) == 8`.

### D5. Determinism + reproducibility
- `trigger_at` is supplied by the caller, not generated inside the assembler — the runner injects it. Tests pass a fixed timestamp.
- `decision_id` is derived from `trigger_at` + `candidate.symbol` — no UUIDs, no clocks inside the function.
- Pure function: no global state, no logging side effects beyond `logger.debug()`.

### D6. CLI surface
Add `oms assemble-entry-input <symbol> [--asof YYYY-MM-DD] [--out fixture.json]`. It:
1. Loads the `Phase2BCandidate` for that symbol from the scoring repository (or runs scoring on demand if `--asof` matches today).
2. Pulls live market / portfolio / journal snapshots via default adapters.
3. Calls `build_entry_decision_input`.
4. Prints (or writes) the JSON.

Used both by Mark for sanity-checking and by tests to capture fixtures.

### D7. Error handling
- If `Phase2BCandidate.final_score < 65`: raise `AssemblerInputError("score below threshold")`. Phase 3 swarm should not run on rejects.
- If any adapter raises: bubble up with context (symbol, adapter name). No silent fallback to defaults — the swarm running on stale data is worse than failing loudly.
- If a SEPA field is missing from the candidate (e.g., `vcp_quality is None`): raise `AssemblerInputError`. v3.1 requires SEPA fields populated; the upstream scorer must fill them.

### D8. Schema version pinning
`input_schema_version: Literal["v3.1"]` — bumping requires editing the model, the digest, and the snapshot test in one PR. Prevents accidental partial migrations.

## Risks / Trade-offs

- **[Drift between schema doc and Pydantic model]** → Mitigation: snapshot test that loads `tests/fixtures/entry_decision_input_sample.json` (manually copied from `llm-decision-schema.md` §1 example) and validates it through `EntryDecisionInput.model_validate`. Any unknown / missing field fails CI.
- **[RulesDigest staleness when cheatsheet evolves]** → Mitigation: regenerate `_rules_digest.json` via the one-shot script and gate it with a CI check that re-runs the script and diffs the output.
- **[Adapter slowness blocks the swarm]** → Mitigation: adapters are I/O-bounded by design; the assembler itself is pure and fast. Profile if it becomes a problem; add caching at the adapter layer, not the assembler.
- **[Position sorting churn]** → Mitigation: explicit `sorted(..., key=lambda p: (-p.exposure_pct, p.symbol))`. Document in the model docstring.
- **[Symbol/sector mapping]** → For now, sector comes from `chip_data_tool` cached metadata; if missing, raise (don't default to `"未知"`). Better to fail than mislead Risk Gate.
- **[Time zone bugs]** → All timestamps use `Asia/Taipei` (`+08:00`). Tests cover DST-free TW so it's stable, but explicit assertion on `.utcoffset()`.

## Migration Plan

This is greenfield code — no migration. Rollout:
1. Land Pydantic models + assembler + tests; assembler is unused in production.
2. Land CLI command; manual smoke test on 2–3 symbols.
3. Phase 3 change (`phase-3-llm-decider`) imports `build_entry_decision_input` and wires it into the swarm.

Rollback: revert the change; nothing else depends on the assembler yet.

## Open Questions

- **Q1**: Should `available_skills` filter to only swarm-relevant categories (technical / chip / fundamental / tw_specific) or include everything? Decision: include everything for now — `entry_decision_team.yaml` already pins which skills each node uses; the assembler just advertises availability. Revisit if input token cost is an issue.
- **Q2**: `consecutive_loss` semantics — only realised exits, or include open positions trending negative? Decision: realised exits only (matches `trade_journal_tool` semantics). Confirm with cheatsheet §0 risk-off rules during apply.
- **Q3**: Where does `monthly_pnl_pct` come from? `portfolio_tool` exposes equity history; we compute MTD pct on the fly. Confirm during apply that the equity curve has enough history; otherwise return `0.0` for the first month.
