## MODIFIED Requirements

### Requirement: PUBLIC_WHITELIST defines all fields a public payload MAY carry

The module SHALL expose a `PUBLIC_WHITELIST: dict[str, set[str]]` constant keyed by
`event_type`. For each whitelisted `event_type`, the serializer SHALL emit only fields
whose names appear in the corresponding set. Any field not in the set SHALL be silently
dropped, regardless of whether it came from `event.payload` directly or was synthesised
by the serializer.

The mapping SHALL cover all 21 event types listed in `EventType` (the 16 original +
5 swarm). Field sets for the 5 swarm event types SHALL be:

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
