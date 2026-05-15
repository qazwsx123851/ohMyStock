# admin-public-events-endpoint Specification

## Purpose
TBD - created by archiving change web-public-shell-and-mask. Update Purpose after archive.
## Requirements

### Requirement: GET /api/public/events SHALL stream masked events without authentication

The route `GET /api/public/events` SHALL be registered on the FastAPI app and SHALL
NOT carry any auth dependency. Any request, regardless of headers, SHALL be accepted
and upgraded to an SSE stream (`text/event-stream`). The handler SHALL subscribe to
the same process-wide `bus` instance used by the admin SSE handler.

#### Scenario: Request without Authorization header succeeds

- **WHEN** a client issues `GET /api/public/events` with no `Authorization` header
- **THEN** the response status SHALL be `200`
- **AND** the `Content-Type` SHALL begin with `text/event-stream`

#### Scenario: Request with bogus Authorization header is still accepted

- **WHEN** a client issues `GET /api/public/events` with `Authorization: Bearer xxx`
- **THEN** the response status SHALL be `200` (auth header is ignored, not rejected)

### Requirement: Streamed payloads SHALL be MaskedEventSerializer output

Each SSE `data:` frame on `/api/public/events` SHALL be the JSON encoding of
`MaskedEventSerializer(...).serialize(event)` where `event` is the same `Event`
instance that the admin stream sees. The handler SHALL NOT bypass the serializer, SHALL
NOT inject raw `event.payload`, and SHALL NOT add or remove top-level envelope keys.

#### Scenario: Public stream payload contains masked_symbol, not symbol

- **WHEN** an `Event(event_type="decision_made", payload={"symbol": "2330", ...})` is
  emitted on `bus` while a client is connected to `/api/public/events`
- **THEN** the next SSE frame's `data` JSON's `payload` field SHALL contain
  `masked_symbol` (e.g. `"STK-A"`)
- **AND** the same frame SHALL NOT contain the substring `"symbol":"2330"` anywhere

### Requirement: Connection lifecycle mirrors admin endpoint

The handler SHALL:

- Call `bus.subscribe()` at stream start.
- Call `bus.unsubscribe(q)` in a `finally` block so dead queues do not leak when the
  client disconnects.
- Emit a `: keepalive` comment frame every 15 s of idle time (same constant the admin
  endpoint uses) so HTTP intermediaries do not drop the connection.

#### Scenario: Disconnect releases the subscriber

- **WHEN** a client opens `/api/public/events`, the server confirms one new subscriber
  on `bus`, then the client closes the connection
- **THEN** within one event loop tick after disconnect, `bus._subscribers` SHALL have
  the same length as before the client connected

#### Scenario: Idle stream emits keepalive

- **WHEN** no event has been emitted for 15+ seconds while a client is connected
- **THEN** the server SHALL have sent at least one frame whose raw bytes contain
  `: keepalive`

### Requirement: CORS for /api/public/* SHALL allow dev origins

The app SHALL register a CORS configuration that allows requests to `/api/public/*`
from `http://localhost:5173` and `http://localhost:5174`. Allowed methods SHALL include
`GET`. Allowed headers SHALL include `Accept`, `Cache-Control`, `Last-Event-ID`. CORS
configuration SHALL NOT widen access for `/api/admin/*` routes.

#### Scenario: Preflight from web-public dev origin passes

- **WHEN** a browser at `http://localhost:5173` issues a preflight `OPTIONS /api/public/events`
- **THEN** the response SHALL include `Access-Control-Allow-Origin: http://localhost:5173`

#### Scenario: Public CORS does not leak into admin routes

- **WHEN** a browser at `http://localhost:5173` issues a preflight `OPTIONS /api/admin/events`
- **THEN** the response SHALL NOT include `Access-Control-Allow-Origin: http://localhost:5173`

### Requirement: SymbolMaskTable is one process-scoped instance per app lifetime

The app's `_lifespan` SHALL construct exactly one `SymbolMaskTable` instance at
startup, populate its `industry_lookup` dict from the available rows in
`universe_daily` (using whatever industry-source column exists, or an empty dict if
the column does not exist), and inject the same instance into the
`MaskedEventSerializer` used by the public route. On lifespan exit, the module-level
reference SHALL be cleared so that any reference after shutdown raises rather than
serving stale data.

#### Scenario: Same masked label across two requests in one app lifetime

- **WHEN** two clients connect to `/api/public/events` sequentially within the same
  app lifetime, and both observe a `decision_made` for the same underlying symbol
- **THEN** both observed `masked_symbol` values SHALL be equal

#### Scenario: Masked label may change across app restarts

- **WHEN** the app shuts down and starts up again, and the same underlying symbol is
  the first to be observed in each lifetime
- **THEN** the `masked_symbol` SHALL be `"STK-A"` in both lifetimes (i.e. counter
  resets); this is intentional and SHALL be considered correct behaviour

### Requirement: Public route module SHALL NOT import any admin auth symbols

The new module `src/ohmystock/api/routes/public_events.py` SHALL NOT import
`require_admin`, `AuthError`, or any symbol from `ohmystock.api.auth`. A grep against
the source file SHALL return zero matches for the literal string `auth`.

#### Scenario: Static check passes

- **WHEN** the test suite reads `src/ohmystock/api/routes/public_events.py` as text
- **THEN** the lowercased text SHALL NOT contain the substring `auth`
