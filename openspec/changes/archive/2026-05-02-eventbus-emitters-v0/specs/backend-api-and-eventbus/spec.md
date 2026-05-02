## MODIFIED Requirements

### Requirement: Admin SSE 心跳通道

系統 SHALL 提供 `GET /api/admin/events` 端點，回傳 `Content-Type: text/event-stream`（SSE）的長連線回應。本 change 將原本的 stub heartbeat 升級為**真實 EventBus 訂閱者**：

- 連線建立時，handler SHALL 呼叫 `bus.subscribe()` 取得一個 `asyncio.Queue[Event]`。
- handler SHALL 進入主迴圈，使用 `asyncio.wait_for(queue.get(), timeout=15.0)` 等待事件：
  - 若收到 `Event` → 以 `AdminEventSerializer.serialize(event)` 取得 dict，`json.dumps` 後以 SSE 格式 yield（`event: <event_type>` line + `data: <json>` line）
  - 若 15 秒內無事件（`asyncio.TimeoutError`）→ yield 一筆 SSE comment 訊框（`: keepalive\n\n` 或等效 `ServerSentEvent(comment="keepalive")`），確保中介 proxy（nginx 預設 60 秒、Cloudflare 預設 100 秒）不因 idle 斷線
- 連線關閉（client 斷開、handler 例外）時，handler SHALL 在 `finally` 區塊呼叫 `bus.unsubscribe(q)`，避免 EventBus 累積死 queue

本 change 階段 `/api/admin/events` SHALL 仍為**無認證**端點（Bearer auth 由後續 change `web-admin-bearer-auth` 在 Phase 4 加上）。`/api/public/events` 不在本 change 範圍。Mask serializer 不在本 change 範圍。

依 `docs/backend-eventbus.md` §5（SSE Endpoint API）與 §3.3（admin JSON 形狀）；emitter 端契約由 `eventbus-emitters` capability 定義。

#### Scenario: `/api/admin/events` 回 200 + SSE content-type
- **WHEN** 對 `/api/admin/events` 發起 `GET` 並讀取 response headers
- **THEN** HTTP 狀態碼為 200，response header `content-type` 開頭為 `text/event-stream`

#### Scenario: 收到真實 bus event 並以 admin JSON 形狀廣播
- **GIVEN** 一個 fresh `EventBus`（test 用 monkeypatch override module-level `bus`）、SSE consumer 透過 `TestClient` 開啟連線
- **WHEN** 從另一條 task 執行 `await bus.emit(Event(event_type="decision_made", agent="decider", payload={"symbol":"2330","confidence":0.72,"reasoning":"r","action":"entry"}))`
- **THEN** consumer 收到一筆 SSE message，`event` field 等於 `"decision_made"`，`data` field 為一個 JSON object，含 keys `event_id`, `timestamp`, `event_type`, `agent`, `payload`，且 `payload["symbol"] == "2330"`、`payload["confidence"] == 0.72`

#### Scenario: idle 連線在 15 秒內收到 keepalive
- **GIVEN** SSE consumer 開啟連線、bus 無任何事件
- **WHEN** 等待最多 16 秒
- **THEN** consumer 收到至少一筆 SSE comment line（以 `:` 開頭）；連線未被 server 主動關閉

#### Scenario: client 斷線後 handler 呼叫 unsubscribe
- **GIVEN** 一個 spy on `bus.unsubscribe`、SSE consumer 開啟連線
- **WHEN** consumer 主動 close
- **THEN** spy 觀察到 `unsubscribe(q)` 被呼叫一次（傳入 subscribe 時取得的同一 queue 物件）

#### Scenario: `/api/admin/events` 不要求認證
- **WHEN** 對 `/api/admin/events` 發起 `GET` 不帶任何 `Authorization` header
- **THEN** HTTP 狀態碼為 200（不為 401 / 403）；連線正常進入 streaming 模式
