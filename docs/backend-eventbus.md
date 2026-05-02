# Backend EventBus 設計

> **版本**：v1.0 ｜ **建立日期**：2026-04-27
> **對應程式**：`backend/ohmystock/eventbus/`、`backend/ohmystock/api/{admin,public}/`
> **權威來源**：本檔為 **EventBus 架構 + Event Schema + Serializer 規格**的唯一權威。
> **相關章節**：[`auth-and-mask.md`](auth-and-mask.md)（Mask Spec 完整版）/ [`frontend-public-pixel.md`](frontend-public-pixel.md)（前台 event → 角色 action 對應）/ [`design-zh-TW.md`](design-zh-TW.md) §3

---

## 1. 用途與設計目標

EventBus 是 ohMyStock 兩專案前端架構（web-public + web-admin）的核心通道。所有 LLM agent 行為（screener、決策、復盤、提案、Risk Gate）透過 hook 寫入 EventBus，再透過兩條 SSE channel 廣播：

```
Python LLM Agent
  └─ tool 呼叫 / 決策 / 復盤 → bus.emit(event)
        └─ EventBus broadcast 到兩 channel:
           ├─ admin channel  → AdminEventSerializer  → /api/admin/events  (auth)
           └─ public channel → MaskedEventSerializer → /api/public/events (no auth)
                                                               │
                          ┌────────────────────────────────────┼─────────────────────────────┐
                          ▼                                                                  ▼
                    web-admin/ React app                                              web-public/ React app
                    (Dashboard / Chat / Backtest 等 18 頁)                            (pixel 像素辦公室)
```

**設計目標：**
- 公開 channel 永遠無法洩露 `symbol`、`price`、`pnl_twd`、`account_id` 等敏感欄位（serializer 強制 strip）
- 兩 frontend app 完全 decouple：admin 故障不影響 public 展示，反之亦然
- 業務程式呼叫 `bus.emit(event)` 一次即可，不需各自寫兩種 serialize 邏輯

---

## 2. 架構概覽

### 2.1 模組結構

```
backend/ohmystock/
├── eventbus/
│   ├── __init__.py
│   ├── bus.py                  # EventBus 核心（asyncio Queue pub/sub）
│   ├── events.py               # Event dataclass + EVENT_TYPES 常數
│   └── serializers/
│       ├── __init__.py
│       ├── admin.py            # AdminEventSerializer（全資料）
│       └── public.py           # MaskedEventSerializer（白名單）
├── api/
│   ├── admin/
│   │   └── events.py           # SSE endpoint: GET /api/admin/events
│   └── public/
│       └── events.py           # SSE endpoint: GET /api/public/events
└── hooks/
    ├── pre_tool_use.py         # → emit screener_started / decider_thinking 等
    └── post_tool_use.py        # → emit screener_completed / decision_made 等
```

### 2.2 EventBus 核心介面

```python
# backend/ohmystock/eventbus/bus.py
from asyncio import Queue
from typing import AsyncIterator
from .events import Event

class EventBus:
    """In-memory async pub/sub. v1 單 worker；多 worker 改 Redis pub/sub。"""

    def __init__(self) -> None:
        self._subscribers: list[Queue[Event]] = []

    def subscribe(self) -> Queue[Event]:
        q: Queue[Event] = Queue(maxsize=1024)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: Queue[Event]) -> None:
        self._subscribers.remove(q)

    async def emit(self, event: Event) -> None:
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except Exception:
                pass  # 單一 subscriber 滿了不影響其他人

bus = EventBus()  # 全 process 唯一實例
```

> v1 限制：in-memory + 單 worker。**多 worker / 跨機** 時改 Redis pub/sub（v2 評估，見 §10）。

---

## 3. Event Schema

### 3.1 Event dataclass

```python
# backend/ohmystock/eventbus/events.py
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import uuid4

TPE = timezone(timedelta(hours=8))  # 台北時區

@dataclass(frozen=True, slots=True)
class Event:
    event_type: str                              # 見 §3.2 EVENT_TYPES
    agent: str                                   # scanner / decider / proposer / ...
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: f"evt_{uuid4().hex[:12]}")
    timestamp: datetime = field(default_factory=lambda: datetime.now(TPE))
```

> **v0 wiring status (eventbus-emitters-v0)**: 9 of the 16 event_types below are emitted by already-shipped services (`screener_started`, `screener_completed`, `decider_thinking`, `decision_made`, `awaiting_confirm`, `order_sent`, `journal_written`, `risk_off_triggered`). The 7 deferred — `pattern_detected`, `journal_queried`, `review_node_started`, `review_completed`, `proposal_created`, `wfa_started`, `wfa_passed`, `wfa_failed` — wait for their respective producers (pattern detector, FTS5 query path, Phase 5 reviewer / proposer / WFA validator) to ship.

### 3.2 EVENT_TYPES 清單（v1 範圍 = 14 項）

| event_type | agent | 觸發時機 | 完整 payload 欄位 |
|---|---|---|---|
| `screener_started` | scanner | `screener_tool` 開始跑 | `universe_size: int` |
| `screener_completed` | scanner | `screener_tool` 結束 | `candidate_count: int`, `symbols: list[str]` |
| `pattern_detected` | pattern_analyst | detector 命中 | `symbol: str`, `pattern: "VCP"\|"杯柄"\|"旗形"`, `score: float` |
| `decider_thinking` | decider | `entry_decision_team` swarm 進入 LLM | `symbol: str`, `confidence_so_far: float` |
| `decision_made` | decider | swarm 完成 | `symbol: str`, `confidence: float`, `reasoning: str`, `action: "entry"\|"skip"` |
| `awaiting_confirm` | trader | Confirm Gate 等待 | `symbol: str`, `timeout_at: datetime`, `expected_price: float` |
| `order_sent` | trader | Confirm 通過 → 送 broker | `symbol: str`, `price: float`, `quantity: int`, `broker_order_id: str` |
| `journal_written` | librarian | Trade Journal 寫入 | `journal_kind: "entry"\|"exit"\|"reject"\|"expire"`, `symbol: str` |
| `journal_queried` | librarian | FTS5 查詢 | `query: str`, `result_count: int` |
| `review_node_started` | reviewer | 五節點 DAG 進到節點 N | `review_id: str`, `node_name: str`, `node_index: int` |
| `review_completed` | reviewer | 五節點全部完成 | `review_id: str`, `proposals_created_count: int` |
| `proposal_created` | proposer | 新提案寫入 | `proposal_id: str`, `priority: "high"\|"medium"\|"low"`, `target_section: str` |
| `wfa_started` / `wfa_passed` / `wfa_failed` | validator | WFA 驗證流程 | `proposal_id: str`, `failure_reason?: str` |
| `risk_off_triggered` | guard | Risk Gate 9 條任一觸發 | `reason_category: str`, `severity: "warn"\|"halt"` |

### 3.3 Event 範例（admin channel，未 mask）

```json
{
  "event_id": "evt_a3f1b2c8d7e9",
  "timestamp": "2026-04-27T13:30:00.123+08:00",
  "event_type": "decision_made",
  "agent": "decider",
  "payload": {
    "symbol": "2330",
    "confidence": 0.72,
    "reasoning": "突破 20MA + 量能 1.5x + VCP 收斂完成",
    "action": "entry"
  }
}
```

### 3.4 Event 範例（public channel，已 mask）

```json
{
  "event_id": "evt_a3f1b2c8d7e9",
  "timestamp": "2026-04-27T13:30:00.123+08:00",
  "event_type": "decision_made",
  "agent": "decider",
  "payload": {
    "masked_symbol": "STK-X",
    "industry_hint": "半導體",
    "confidence": 0.72,
    "reasoning_summary": "突破 20MA + 量能 1.5x + VCP 收斂完成",
    "action": "entry"
  }
}
```

> **差異**：`symbol` → `masked_symbol`（同一 session 內 2330 永遠映 STK-X，session 結束後重置）；新增 `industry_hint`（產業類別 OK 公開）；`reasoning` 改名 `reasoning_summary` 並 strip 任何 `\b\d{4}\b` 4 位數股票代號。

---

## 4. Serializer 規格

### 4.1 AdminEventSerializer（後台用，全資料）

```python
# backend/ohmystock/eventbus/serializers/admin.py
from ..events import Event

class AdminEventSerializer:
    """全欄位 serialize，僅做 datetime → ISO string、UUID → str 等基本轉換。"""

    def serialize(self, event: Event) -> dict:
        return {
            "event_id": event.event_id,
            "timestamp": event.timestamp.isoformat(),
            "event_type": event.event_type,
            "agent": event.agent,
            "payload": event.payload,  # 原樣
        }
```

### 4.2 MaskedEventSerializer（前台用，白名單）

```python
# backend/ohmystock/eventbus/serializers/public.py
import re
from ..events import Event

# 各 event_type 的白名單欄位（不在白名單一律 drop）
PUBLIC_WHITELIST: dict[str, set[str]] = {
    "screener_started":     {"universe_size"},
    "screener_completed":   {"candidate_count"},
    "pattern_detected":     {"masked_symbol", "industry_hint", "pattern", "score"},
    "decider_thinking":     {"masked_symbol", "industry_hint", "confidence_so_far"},
    "decision_made":        {"masked_symbol", "industry_hint", "confidence",
                             "reasoning_summary", "action"},
    "awaiting_confirm":     {"masked_symbol", "industry_hint", "timeout_at"},
    "order_sent":           {"masked_symbol", "industry_hint"},
    "journal_written":      {"journal_kind", "masked_symbol"},
    "journal_queried":      {"result_count"},
    "review_node_started":  {"review_id", "node_name", "node_index"},
    "review_completed":     {"review_id", "proposals_created_count"},
    "proposal_created":     {"proposal_id", "priority", "target_section"},
    "wfa_started":          {"proposal_id"},
    "wfa_passed":           {"proposal_id"},
    "wfa_failed":           {"proposal_id"},  # 不洩 failure_reason 細節
    "risk_off_triggered":   {"reason_category", "severity"},
}

# 任何 event 都絕對禁止出現的欄位（防呆）
DENYLIST_FIELDS: frozenset[str] = frozenset({
    "symbol", "company_name", "price", "expected_price", "quantity",
    "pnl_twd", "account_id", "api_key", "broker_order_id",
    "reasoning",  # 原始 reasoning 可能含真 symbol；只允許 reasoning_summary
    "query",      # FTS5 查詢字串可能含 symbol
    "symbols",    # screener_completed 的清單；只允許 candidate_count
    "failure_reason",
})

# 4 位數股票代號 regex（防 reasoning_summary 漏網）
TWSE_CODE_RE = re.compile(r"\b\d{4}\b")


class MaskedEventSerializer:
    def __init__(self, mask_table: "SymbolMaskTable") -> None:
        self._mask_table = mask_table

    def serialize(self, event: Event) -> dict:
        whitelist = PUBLIC_WHITELIST.get(event.event_type, set())
        out: dict = {}

        # 1. symbol → masked_symbol 對映 + industry_hint 注入
        if "symbol" in event.payload and "masked_symbol" in whitelist:
            out["masked_symbol"] = self._mask_table.mask(event.payload["symbol"])
            out["industry_hint"] = self._mask_table.industry_of(event.payload["symbol"])

        # 2. reasoning → reasoning_summary（strip 4 位數代號）
        if "reasoning" in event.payload and "reasoning_summary" in whitelist:
            out["reasoning_summary"] = TWSE_CODE_RE.sub("STK-?", event.payload["reasoning"])

        # 3. 白名單欄位直通
        for k in whitelist:
            if k in {"masked_symbol", "industry_hint", "reasoning_summary"}:
                continue  # 已處理
            if k in event.payload:
                out[k] = event.payload[k]

        # 4. 防呆：DENYLIST 二次過濾
        for f in DENYLIST_FIELDS:
            out.pop(f, None)

        return {
            "event_id": event.event_id,
            "timestamp": event.timestamp.isoformat(),
            "event_type": event.event_type,
            "agent": event.agent,
            "payload": out,
        }
```

### 4.3 SymbolMaskTable（代碼對映表）

```python
# backend/ohmystock/eventbus/serializers/mask_table.py
from string import ascii_uppercase

class SymbolMaskTable:
    """同一 process 內 symbol 永遠映同一個 masked_symbol；process 重啟重置。"""

    def __init__(self, industry_lookup: dict[str, str]) -> None:
        self._map: dict[str, str] = {}
        self._counter = 0
        self._industry = industry_lookup  # symbol → 「半導體」「金融」等

    def mask(self, symbol: str) -> str:
        if symbol not in self._map:
            self._map[symbol] = self._next_label()
        return self._map[symbol]

    def industry_of(self, symbol: str) -> str:
        return self._industry.get(symbol, "其他")

    def _next_label(self) -> str:
        # STK-A, STK-B, ..., STK-Z, STK-AA, STK-AB, ...
        n = self._counter
        self._counter += 1
        chars = []
        n += 1
        while n > 0:
            n, r = divmod(n - 1, 26)
            chars.append(ascii_uppercase[r])
        return "STK-" + "".join(reversed(chars))
```

> 不用 `hash(symbol)` 是因為要維持 STK-A、STK-B 順序好讀；session 內穩定但跨 session 重置（避免訪客累積對映表破解）。

---

## 5. SSE Endpoint API

### 5.1 Public endpoint（無 auth）

```
GET /api/public/events
Accept: text/event-stream

→ 伺服器持續推送：

event: decision_made
id: evt_a3f1b2c8d7e9
data: {"event_id":"evt_a3f1b2c8d7e9","timestamp":"2026-04-27T13:30:00.123+08:00","event_type":"decision_made","agent":"decider","payload":{...masked...}}

event: screener_started
...
```

```python
# backend/ohmystock/api/public/events.py
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
from ...eventbus.bus import bus
from ...eventbus.serializers.public import MaskedEventSerializer

router = APIRouter(prefix="/api/public", tags=["public"])
serializer = MaskedEventSerializer(mask_table=...)

@router.get("/events")
async def events():
    async def stream():
        q = bus.subscribe()
        try:
            while True:
                event = await q.get()
                yield {
                    "event": event.event_type,
                    "id": event.event_id,
                    "data": json.dumps(serializer.serialize(event)),
                }
        finally:
            bus.unsubscribe(q)
    return EventSourceResponse(stream())
```

### 5.2 Admin endpoint（需 auth）

```
GET /api/admin/events
Authorization: Bearer <jwt>
Accept: text/event-stream
```

```python
# backend/ohmystock/api/admin/events.py
from fastapi import APIRouter, Depends
from ...auth import require_admin
from ...eventbus.bus import bus
from ...eventbus.serializers.admin import AdminEventSerializer

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])
serializer = AdminEventSerializer()

@router.get("/events")
async def events():
    async def stream():
        q = bus.subscribe()
        try:
            while True:
                event = await q.get()
                yield {
                    "event": event.event_type,
                    "id": event.event_id,
                    "data": json.dumps(serializer.serialize(event)),
                }
        finally:
            bus.unsubscribe(q)
    return EventSourceResponse(stream())
```

### 5.3 Admin action endpoints（v0，server-action-endpoints capability）

下列 6 個 write 端點包裝既有核心函式，提供 admin UI 用的 HTTP 觸發接口。
全部走統一 envelope `{"ok": true, "data": ...}` 或 `{"ok": false, "error": {"code", "message"}}`，
HTTP status 對應 `code` 一一映射（見對應 spec 與 `src/ohmystock/api/routes/_envelope.py`）。

| Method | Path | Body / Query | Wraps | 主要 success data | 主要 error code (HTTP) |
|---|---|---|---|---|---|
| POST | `/api/admin/screener/run` | `{universe, custom_symbols?, filters?, asof_date?}` | `screen_universe()` | `asof_date_used`, `candidates`, `elapsed_ms` | `invalid_input` (400) / `data_unavailable` (503) / `upstream_error` (502) |
| GET | `/api/admin/confirm-gate/pending` | `?timeout_minutes=int?` | `list_pending()` | `items`, `timeout_minutes` | `invalid_input` (400) |
| POST | `/api/admin/confirm-gate/confirm` | `{decision_id, user}` | `confirm()` | `decision_id`, `fill`, `qty` | `not_found` (404) / `not_pending` (409) / `payload_invalid` (409) / `broker_failed` (502) |
| POST | `/api/admin/confirm-gate/reject` | `{decision_id, user, reason}` | `reject()` | `decision_id`, `reject_row_id` | `invalid_input` (400) / `not_found` (404) / `not_pending` (409) |
| POST | `/api/admin/confirm-gate/sweep-expired` | `{timeout_minutes?}` | `sweep_expired()` | `swept_decision_ids`, `swept_count`, `timeout_minutes` | `invalid_input` (400) |
| POST | `/api/admin/exit-engine/run` | `{asof_date?, symbol?}` | `evaluate_open_positions()` | `results`, `evaluated_count`, `closed_count`, `held_count`, `asof_date_used` | `invalid_input` (400) / `market_data_unavailable` (503) |

設計細節（per-request connection lifecycle、unified envelope mapping、no-auth invariant、
不洩漏 stack trace / SQL / 絕對路徑）見 `openspec/specs/server-action-endpoints/spec.md`（archive 後）。

Phase 4 接 Bearer auth 由獨立 capability `web-admin-bearer-auth` 補上；本 v0 維持無認證、
僅綁 `localhost`。

### 5.4 CORS / Rate Limit

| 端點 | CORS 允許來源 | Rate Limit |
|---|---|---|
| `/api/public/events` | web-public production domain（如 `https://ohmystock.example.com`） + `localhost:5173`（dev） | 10 連線 / IP / 分鐘 |
| `/api/admin/events` | `localhost:5174`（admin dev port） + Tunnel domain | 無限制（已認證） |

---

## 6. Hook 整合點

業務程式碼透過 hook 在 tool 執行前後 emit event：

```python
# backend/ohmystock/hooks/pre_tool_use.py
from ..eventbus.bus import bus
from ..eventbus.events import Event

PRE_TOOL_EVENT_MAP = {
    "screener_tool":            ("screener_started",  "scanner"),
    "entry_decision_team":      ("decider_thinking",  "decider"),
    # ...
}

async def on_tool_call(tool_name: str, tool_input: dict) -> None:
    if tool_name in PRE_TOOL_EVENT_MAP:
        event_type, agent = PRE_TOOL_EVENT_MAP[tool_name]
        await bus.emit(Event(
            event_type=event_type,
            agent=agent,
            payload=_extract_pre_payload(event_type, tool_input),
        ))
```

```python
# backend/ohmystock/hooks/post_tool_use.py
POST_TOOL_EVENT_MAP = {
    "screener_tool":           ("screener_completed", "scanner"),
    "entry_decision_team":     ("decision_made",      "decider"),
    "post_trade_review_tool":  ("review_completed",   "reviewer"),
    "proposal_tool.create":    ("proposal_created",   "proposer"),
    # ...
}

async def on_tool_result(tool_name: str, tool_input: dict, tool_result: dict) -> None:
    mapping = POST_TOOL_EVENT_MAP.get(tool_name)
    if not mapping:
        return
    event_type, agent = mapping
    await bus.emit(Event(
        event_type=event_type,
        agent=agent,
        payload=_extract_post_payload(event_type, tool_input, tool_result),
    ))
```

> Hook 不負責 mask；mask 由 serializer 統一做。Hook 只負責「觸發點對應 event_type」。

### 6.1 業務服務直接 emit

部分事件不對應單一 tool（如 Confirm Gate timeout、Risk Gate 觸發），由服務層直接呼叫：

```python
# backend/ohmystock/services/risk_gate.py
async def check(...):
    if violated:
        await bus.emit(Event(
            event_type="risk_off_triggered",
            agent="guard",
            payload={"reason_category": "monthly_drawdown", "severity": "halt"},
        ))
```

---

## 7. 測試策略

### 7.1 Unit test：Serializer DENYLIST 防呆

```python
# backend/tests/test_public_serializer.py
import pytest
from ohmystock.eventbus.events import Event
from ohmystock.eventbus.serializers.public import (
    MaskedEventSerializer, PUBLIC_WHITELIST, DENYLIST_FIELDS
)

@pytest.mark.parametrize("event_type", list(PUBLIC_WHITELIST.keys()))
def test_no_denylist_fields_leak(event_type, mask_table_fixture):
    """每個 event_type 用最大 payload（含所有可能欄位）跑一次，斷言輸出無 DENYLIST。"""
    s = MaskedEventSerializer(mask_table_fixture)
    fat_payload = {
        "symbol": "2330", "company_name": "台積電", "price": 800.0,
        "expected_price": 798.0, "quantity": 1000, "pnl_twd": 50000,
        "account_id": "F123456789", "api_key": "secret",
        "broker_order_id": "BRK-001", "reasoning": "2330 突破 20MA",
        "query": "VCP 2330", "symbols": ["2330", "2317"],
        "failure_reason": "WFA Sharpe < 0",
        # 加合法欄位
        "confidence": 0.72, "reasoning_summary": "突破 20MA",
        "candidate_count": 12, "pattern": "VCP", "score": 0.8,
        "industry_hint": "半導體", "action": "entry",
        "review_id": "2026-04", "node_name": "data_loader",
        "proposal_id": "p001", "priority": "high",
        "target_section": "§6.4", "reason_category": "monthly_drawdown",
        "severity": "halt", "journal_kind": "entry",
        "result_count": 5, "node_index": 1,
        "universe_size": 1700,
        "timeout_at": "2026-04-27T14:00:00+08:00",
        "confidence_so_far": 0.5,
        "proposals_created_count": 3,
    }
    event = Event(event_type=event_type, agent="test", payload=fat_payload)
    out = s.serialize(event)["payload"]
    for forbidden in DENYLIST_FIELDS:
        assert forbidden not in out, f"{event_type}: leaked {forbidden}"

def test_4digit_code_stripped_in_reasoning(mask_table_fixture):
    s = MaskedEventSerializer(mask_table_fixture)
    event = Event(
        event_type="decision_made",
        agent="decider",
        payload={"symbol": "2330", "reasoning": "2330 突破 20MA",
                 "confidence": 0.7, "action": "entry"},
    )
    out = s.serialize(event)["payload"]
    assert "2330" not in out["reasoning_summary"]
```

### 7.2 E2E test：未登入瀏覽器掃 SSE

見 [`auth-and-mask.md`](auth-and-mask.md) §6 Playwright test plan。

---

## 8. 觀察性 / Debug

- **Admin debug page**：`/admin/eventbus`（後台 18 頁之一）顯示最近 100 筆 event（兩 channel 並列），方便比對 mask 結果
- **Log**：每筆 event 寫 `audit_logs/eventbus.jsonl`（保留 90 天，依 v1 決策 #5）

---

## 9. 與既有 Trade Journal 的關係

| 元件 | 寫入 | 讀取 | 用途 |
|---|---|---|---|
| EventBus | hook / service emit | SSE subscriber | 即時前端動畫驅動 |
| Trade Journal (SQLite + FTS5) | 業務服務寫入 | 後台查詢、月度復盤 | 持久化決策史、可搜尋 |

EventBus 是**短暫**（in-memory，process 重啟即失），Trade Journal 是**持久**。**同一筆決策會同時寫兩處**：emit `decision_made` event + 寫 journal entry。

---

## 10. v2 規劃（暫不實作）

| 主題 | 觸發條件 | 方案 |
|---|---|---|
| 多 worker / 跨機 | 後台跑成 multi-process（如 gunicorn -w 4） | Redis pub/sub 取代 in-memory Queue |
| Event 持久化 | 想 replay 過去 event 重現某天場景 | append-only `eventbus_log.parquet`（每日 rotate） |
| Backpressure | subscriber 慢於 producer | bounded queue + drop_oldest 策略 |
| Schema 演進 | event 加新欄位 | EVENT_TYPES 加版本號（如 `decision_made.v2`），舊 client 用 .v1 fallback |

---

## 11. FAQ

**Q：為什麼 reasoning 不直接整段對外，而要 mask？**
A：reasoning 文字常含 `2330`、`台積電` 等具體標的；對外可能踩 SITC「公開薦股」線。`reasoning_summary` 強制把 4 位數代號換成 `STK-?`。

**Q：mask_table 跨 session 重置是否會讓前台訪客「同一檔股票每次刷新都不同代號」？**
A：是的。session = process 生命週期。重啟後 STK-A 可能對應到不同 symbol，這是刻意設計，避免訪客長期觀察累積對映表反推真實 symbol。

**Q：為什麼用 SSE 不用 WebSocket？**
A：本系統流向是**單向 server → client**（agent 行為事件），不需要 client 反向送命令。SSE 比 WS 簡單（瀏覽器原生 EventSource）、自動 reconnect、走 HTTP/2 多工免額外連線管理。

**Q：v1 為什麼用 in-memory？多 worker 怎辦？**
A：v1 預期單 worker（個人專案，無 throughput 壓力）。若 v2 需要多 worker，改 Redis pub/sub，介面（`bus.emit` / `bus.subscribe`）不變。

**Q：Hook 跟業務服務都能 emit，會不會重複？**
A：每個 event_type 只應有一個觸發來源，由 §3.2 表格定義。Hook 適用於「對應特定 tool 名」的事件；業務服務 emit 適用於「跨 tool 的閘門」（如 Risk Gate、Confirm Gate timeout）。
