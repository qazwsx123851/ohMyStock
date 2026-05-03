## MODIFIED Requirements

### Requirement: Admin SSE 心跳通道

系統 SHALL 提供 `GET /api/admin/events` 端點，回傳 `Content-Type: text/event-stream`（SSE）的長連線回應。本 capability 將原本的 stub heartbeat 升級為**真實 EventBus 訂閱者**：

- 連線建立時，handler SHALL 呼叫 `bus.subscribe()` 取得一個 `asyncio.Queue[Event]`。
- handler SHALL 進入主迴圈，使用 `asyncio.wait_for(queue.get(), timeout=15.0)` 等待事件：
  - 若收到 `Event` → 以 `AdminEventSerializer.serialize(event)` 取得 dict，`json.dumps` 後以 SSE 格式 yield（`event: <event_type>` line + `data: <json>` line）
  - 若 15 秒內無事件（`asyncio.TimeoutError`）→ yield 一筆 SSE comment 訊框（`: keepalive\n\n` 或等效 `ServerSentEvent(comment="keepalive")`），確保中介 proxy（nginx 預設 60 秒、Cloudflare 預設 100 秒）不因 idle 斷線
- 連線關閉（client 斷開、handler 例外）時，handler SHALL 在 `finally` 區塊呼叫 `bus.unsubscribe(q)`，避免 EventBus 累積死 queue

`/api/admin/events` SHALL 通過 `web-admin-bearer-auth` capability 的 `require_admin` dependency；不帶 token 的 GET 請求 SHALL 回 HTTP 401（不為 200、不進入 streaming），body 為統一 envelope `{"ok": false, "error": {"code": "auth_missing", "message": <human-readable>}}`。token 不符 SHALL 回 HTTP 401，`error.code == "auth_invalid"`。`/api/public/events` 不在本 capability 範圍。Mask serializer 不在本 capability 範圍。

依 `docs/backend-eventbus.md` §5（SSE Endpoint API）與 §3.3（admin JSON 形狀）；emitter 端契約由 `eventbus-emitters` capability 定義；Bearer auth 規範由 `web-admin-bearer-auth` capability 定義。

#### Scenario: `/api/admin/events` 帶合法 token 回 200 + SSE content-type
- **GIVEN** `Settings.ohmystock_admin_token` 設為合法 token、`Authorization: Bearer <valid>` header 帶上
- **WHEN** 對 `/api/admin/events` 發起 `GET` 並讀取 response headers
- **THEN** HTTP 狀態碼為 200，response header `content-type` 開頭為 `text/event-stream`

#### Scenario: 收到真實 bus event 並以 admin JSON 形狀廣播
- **GIVEN** 一個 fresh `EventBus`（test 用 monkeypatch override module-level `bus`）、SSE consumer 透過 `TestClient` 帶合法 Bearer token 開啟連線
- **WHEN** 從另一條 task 執行 `await bus.emit(Event(event_type="decision_made", agent="decider", payload={"symbol":"2330","confidence":0.72,"reasoning":"r","action":"entry"}))`
- **THEN** consumer 收到一筆 SSE message，`event` field 等於 `"decision_made"`，`data` field 為一個 JSON object，含 keys `event_id`, `timestamp`, `event_type`, `agent`, `payload`，且 `payload["symbol"] == "2330"`、`payload["confidence"] == 0.72`

#### Scenario: idle 連線在 15 秒內收到 keepalive
- **GIVEN** SSE consumer 帶合法 Bearer token 開啟連線、bus 無任何事件
- **WHEN** 等待最多 16 秒
- **THEN** consumer 收到至少一筆 SSE comment line（以 `:` 開頭）；連線未被 server 主動關閉

#### Scenario: client 斷線後 handler 呼叫 unsubscribe
- **GIVEN** 一個 spy on `bus.unsubscribe`、SSE consumer 帶合法 Bearer token 開啟連線
- **WHEN** consumer 主動 close
- **THEN** spy 觀察到 `unsubscribe(q)` 被呼叫一次（傳入 subscribe 時取得的同一 queue 物件）

#### Scenario: `/api/admin/events` 缺 token 回 401
- **WHEN** 對 `/api/admin/events` 發起 `GET` 不帶任何 `Authorization` header
- **THEN** HTTP 狀態碼為 401（不為 200、不進入 streaming）；body `["error"]["code"] == "auth_missing"`

#### Scenario: `/api/admin/events` token 不符回 401
- **GIVEN** `Settings.ohmystock_admin_token` 設為合法 token；request 帶 `Authorization: Bearer wrong-token-32-characters-or-more-zz`
- **WHEN** 對 `/api/admin/events` 發起 `GET`
- **THEN** HTTP 401；`["error"]["code"] == "auth_invalid"`
