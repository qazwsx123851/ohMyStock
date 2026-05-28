# eventbus-public-mask Specification

## Purpose
TBD - created by archiving change web-public-shell-and-mask. Update Purpose after archive.
## Requirements

### Requirement: PUBLIC_WHITELIST defines all fields a public payload MAY carry

The module SHALL expose a `PUBLIC_WHITELIST: dict[str, set[str]]` constant keyed by
`event_type`. For each whitelisted `event_type`, the serializer SHALL emit only fields
whose names appear in the corresponding set. Any field not in the set SHALL be silently
dropped, regardless of whether it came from `event.payload` directly or was synthesised
by the serializer.

The mapping SHALL cover all 21 event types listed in `EventType` (the 16 original from
`docs/backend-eventbus.md` §3.2 plus 5 swarm event types). Field sets for the 5 swarm
event types SHALL be:

- `swarm_run_started`: `{"run_id", "preset", "nodes"}` — `params` is excluded because
  it can carry caller-supplied symbols.
- `swarm_run_completed`: `{"run_id", "preset", "elapsed_ms"}`.
- `swarm_run_failed`: `{"run_id", "preset"}` — `failed_node` and `error` are excluded
  to avoid leaking strategy / implementation detail.
- `swarm_node_started`: `{"run_id", "preset", "node"}`.
- `swarm_node_completed`: `{"run_id", "preset", "node", "elapsed_ms"}`.

The remaining 16 event types SHALL keep the field sets specified in
`docs/backend-eventbus.md` §4.2 unchanged.

#### Scenario: Whitelisted field passes through

- **WHEN** an `Event` of type `decider_thinking` has payload
  `{"symbol": "2330", "confidence_so_far": 0.5}`
- **THEN** the serialized output payload SHALL contain `confidence_so_far` with value
  `0.5`

#### Scenario: Unknown event_type yields empty payload

- **WHEN** an `Event` has `event_type="not_in_whitelist"` and payload
  `{"anything": "here"}`
- **THEN** the serialized output payload SHALL be `{}` (no fields copied)

#### Scenario: swarm_run_started payload projects to whitelist

- **GIVEN** `Event(event_type="swarm_run_started", agent="reviewer", payload={"run_id":"swr_abc","preset":"phase5-review","nodes":["data_loader","attributor"],"params":{"symbol":"2330","period":{"from":"2026-04-01","to":"2026-04-30"}}})`
- **WHEN** serialized through `MaskedEventSerializer`
- **THEN** the output payload SHALL equal `{"run_id":"swr_abc","preset":"phase5-review","nodes":["data_loader","attributor"]}`
- **AND** `params` SHALL NOT appear in the output payload

#### Scenario: swarm_run_failed drops failed_node and error

- **GIVEN** `Event(event_type="swarm_run_failed", agent="reviewer", payload={"run_id":"swr_abc","preset":"phase5-review","failed_node":"critic","error":{"code":"llm_timeout","message":"..."}})`
- **WHEN** serialized through `MaskedEventSerializer`
- **THEN** the output payload SHALL equal `{"run_id":"swr_abc","preset":"phase5-review"}`
- **AND** the keys `failed_node` and `error` SHALL NOT appear

#### Scenario: swarm_node_completed exposes elapsed_ms

- **GIVEN** `Event(event_type="swarm_node_completed", agent="reviewer", payload={"run_id":"swr_abc","preset":"phase5-review","node":"data_loader","elapsed_ms":1234})`
- **WHEN** serialized through `MaskedEventSerializer`
- **THEN** the output payload SHALL equal `{"run_id":"swr_abc","preset":"phase5-review","node":"data_loader","elapsed_ms":1234}`

### Requirement: DENYLIST_FIELDS is a hard fail-safe after whitelist

The module SHALL expose a `DENYLIST_FIELDS: frozenset[str]` constant containing at
minimum `{"symbol", "company_name", "price", "expected_price", "quantity", "pnl_twd",
"account_id", "api_key", "broker_order_id", "reasoning", "query", "symbols",
"failure_reason"}`. After the whitelist pass, the serializer SHALL pop every key in
`DENYLIST_FIELDS` from the output payload. The DENYLIST SHALL be a belt-and-suspenders
layer; whitelist enforcement alone should already exclude these fields.

#### Scenario: DENYLIST removes a field even if a future whitelist accidentally allows it

- **WHEN** a contrived `PUBLIC_WHITELIST["test_event"] = {"symbol", "confidence"}` and
  an `Event(event_type="test_event", payload={"symbol": "2330", "confidence": 0.5})` is
  serialized
- **THEN** the output payload SHALL NOT contain the key `symbol`
- **AND** the output payload SHALL contain `confidence` with value `0.5`

#### Scenario: All sixteen documented event types pass parametric DENYLIST test

- **WHEN** a "fat" payload containing every DENYLIST field plus every legal whitelisted
  field across all 16 event types is fed through the serializer once per event type
- **THEN** for every event type, no DENYLIST field SHALL appear in the output payload

### Requirement: symbol → masked_symbol mapping is applied when whitelisted

The serializer SHALL apply symbol masking for every event_type whose whitelist contains `masked_symbol`. If the input payload contains a `symbol` key, the serializer SHALL replace it with `masked_symbol = mask_table.mask(symbol)`, and if `industry_hint` is also whitelisted for that event type the serializer SHALL set `industry_hint = mask_table.industry_of(symbol)`. The original `symbol` key SHALL NOT appear in the output (enforced by DENYLIST).

#### Scenario: decision_made event gets symbol replaced and industry injected

- **WHEN** an `Event(event_type="decision_made", payload={"symbol": "2330",
  "confidence": 0.72, "action": "entry", "reasoning": "..."})` is serialized with a
  fresh `SymbolMaskTable` that maps `2330 → "半導體"`
- **THEN** the output payload SHALL contain `masked_symbol="STK-A"` and
  `industry_hint="半導體"` and `confidence=0.72` and `action="entry"`
- **AND** the output payload SHALL NOT contain `symbol` or `reasoning`

### Requirement: reasoning → reasoning_summary strips 4-digit codes

The serializer SHALL produce a `reasoning_summary` field for every event type where `reasoning_summary` is whitelisted (currently `decision_made`). When the input payload contains a `reasoning` string, the serializer SHALL set `reasoning_summary` to `re.sub(r"\b\d{4}\b", "STK-?", reasoning)`. The original `reasoning` key SHALL be dropped (DENYLIST enforced).

The replacement string SHALL be the literal `"STK-?"` (not the masked symbol for that
specific code) so that ambiguous codes (years, share counts) and stock codes are
treated uniformly.

#### Scenario: Real TWSE code in reasoning is stripped

- **WHEN** `reasoning = "2330 突破 20MA + 量能 1.5x"`
- **THEN** `reasoning_summary = "STK-? 突破 20MA + 量能 1.5x"`

#### Scenario: Year-like 4-digit number is also stripped (documented false-positive)

- **WHEN** `reasoning = "since 2026 the trend has held"`
- **THEN** `reasoning_summary = "since STK-? the trend has held"`

#### Scenario: Non-4-digit numbers are left alone

- **WHEN** `reasoning = "突破 20MA + 100 萬成交量 + 5MA"`
- **THEN** `reasoning_summary = "突破 20MA + 100 萬成交量 + 5MA"`

### Requirement: SymbolMaskTable labels are stable in-instance and base-26-encoded

The module SHALL provide a `SymbolMaskTable` class with constructor signature
`__init__(self, industry_lookup: dict[str, str])` and methods:

- `mask(self, symbol: str) -> str` — returns a label. The same input symbol SHALL
  return the same label for the lifetime of the instance.
- `industry_of(self, symbol: str) -> str` — returns the industry from
  `industry_lookup`, or `"其他"` on miss.

Labels SHALL be assigned in encounter order, starting at `"STK-A"`, then `"STK-B"`,
…, `"STK-Z"`, then `"STK-AA"`, `"STK-AB"`, …, following base-26 uppercase rollover.

The instance SHALL NOT persist state across instances; constructing two
`SymbolMaskTable` instances back-to-back SHALL yield independent counter spaces.

#### Scenario: First three distinct symbols get sequential labels

- **WHEN** `t = SymbolMaskTable({})` and `t.mask("2330"); t.mask("2317"); t.mask("2454")`
- **THEN** the returned labels SHALL be `"STK-A"`, `"STK-B"`, `"STK-C"` in that order

#### Scenario: Same symbol returns same label

- **WHEN** `t.mask("2330")` is called twice
- **THEN** both calls SHALL return the same label

#### Scenario: 27th distinct symbol rolls over to STK-AA

- **WHEN** 27 distinct symbols are masked in sequence
- **THEN** the 27th label SHALL be `"STK-AA"`

#### Scenario: industry_of falls through to "其他" on miss

- **WHEN** `t = SymbolMaskTable({"2330": "半導體"})` and `t.industry_of("9999")`
- **THEN** the result SHALL be `"其他"`

#### Scenario: Two instances do not share state

- **WHEN** `t1 = SymbolMaskTable({}); t1.mask("2330"); t2 = SymbolMaskTable({}); t2.mask("2454")`
- **THEN** `t2.mask("2454")` SHALL return `"STK-A"` (not `"STK-B"`)

### Requirement: MaskedEventSerializer envelope is fixed

The serializer SHALL return a dict with exactly the following top-level keys:
`event_id` (str), `timestamp` (ISO 8601 str with timezone), `event_type` (str), `agent`
(str), `payload` (dict). The shape SHALL be structurally identical to
`AdminEventSerializer.serialize(event)`; only the `payload` contents differ. The
serializer SHALL NOT JSON-encode; callers are responsible for `json.dumps`.

#### Scenario: Top-level envelope matches AdminEventSerializer shape

- **WHEN** the same `Event` is serialized by `AdminEventSerializer.serialize` and
  `MaskedEventSerializer(stub_mask_table).serialize`
- **THEN** the set of top-level keys SHALL be identical (`{"event_id", "timestamp",
  "event_type", "agent", "payload"}`)
