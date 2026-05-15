"""Async chat agent runtime backing the streaming endpoint.

Spec: openspec/changes/admin-chat-sessions-endpoints-and-pages/specs/chat-agent-runtime/spec.md

``ChatAgent.stream`` is an async generator that yields a fixed taxonomy of
event dicts which the FastAPI route serialises directly as SSE frames:

* ``{"event": "delta", "text": str}``                              — text chunk
* ``{"event": "tool_call", "id": str, "name": str, "args": dict}`` — tool requested
* ``{"event": "tool_result", "tool_call_id": str, "result": dict}``— tool returned
* ``{"event": "done", "message_id": str, ...}``                    — end of turn
* ``{"event": "error", "code": str, "message": str}``              — fatal error

v0 implementation note
----------------------
The Anthropic Python SDK supports real token-level streaming via
``client.messages.stream(...)``. v0 instead uses the simpler
non-streaming ``client.messages.create(...)`` (same shape as the existing
``decider.node.AnthropicPMConclusionNode``) and **chunks the response
text into ``delta`` events** before yielding. The event sequence the
client sees is still correct — only the per-token timing is coarser.
Swapping the inner SDK call to true streaming is a localised follow-up
that does not touch the route, the SSE parser, or the UI.

Cost accounting is per Anthropic *turn*: every call to
``client.messages.create`` produces one ``llm_costs`` row keyed by
``decision_id=f"chat:{message_id}"`` so monthly chat cost can be queried
via ``WHERE decision_id LIKE 'chat:%'``.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

from ohmystock.chat.schema import ChatMessage
from ohmystock.chat.tools import (
    BUILTIN_TOOLS,
    ToolHandler,
    dispatch_tool,
)
from ohmystock.decider._pricing import compute_cost_usd


_TPE = timezone(timedelta(hours=8))
_DEFAULT_MAX_HISTORY = 40
_DEFAULT_MAX_TOKENS = 4096
_DELTA_CHUNK_CHARS = 24
_MAX_TOOL_TURNS = 5

DEFAULT_SYSTEM_PROMPT = (
    "你是 ohMyStock 的助手 agent，協助 Mark 在台股操作流程中查資料、"
    "解讀紀錄、做事後復盤。\n\n"
    "可用 tool：query_journal / search_memory / get_market_symbol / "
    "list_skills，全部都是唯讀。**你不能下單、不能改 confirm-gate 狀態、"
    "不能修改任何設定**。如果使用者要求你做寫入動作，請禮貌拒絕並說明你只有讀取權限。\n\n"
    "回答時：\n"
    "1. 講清楚自己用了哪個 tool、為什麼用、得到什麼\n"
    "2. 不要捏造資料；查不到就說查不到\n"
    "3. 用繁體中文回答；技術名詞（symbol、RS、SEPA 等）保留英文/縮寫\n"
)


def _new_message_id() -> str:
    return "msg_" + secrets.token_hex(6)


def _now_tpe_iso() -> str:
    return datetime.now(_TPE).isoformat()


def _serialise_chat_messages(
    history: list[ChatMessage], *, max_history: int
) -> list[dict[str, Any]]:
    """Build the ``messages=`` payload from the most recent ``max_history`` rows.

    Tool-result rows are inlined as ``{"role":"user", "content":[{"type":
    "tool_result", ...}]}`` blocks so a follow-up assistant turn can see
    them. Assistant rows with ``tool_calls_json`` set fold their stored
    JSON list back into ``{"type":"tool_use", ...}`` content blocks.
    """

    trimmed = history[-max_history:]
    out: list[dict[str, Any]] = []
    for msg in trimmed:
        if msg.role == "user":
            out.append({"role": "user", "content": msg.content})
            continue
        if msg.role == "assistant":
            blocks: list[dict[str, Any]] = []
            if msg.content:
                blocks.append({"type": "text", "text": msg.content})
            if msg.tool_calls_json:
                try:
                    tool_uses = json.loads(msg.tool_calls_json)
                except (TypeError, ValueError):
                    tool_uses = []
                for tu in tool_uses if isinstance(tool_uses, list) else []:
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": tu.get("id", ""),
                            "name": tu.get("name", ""),
                            "input": tu.get("args", {}) or {},
                        }
                    )
            if not blocks:
                continue
            out.append({"role": "assistant", "content": blocks})
            continue
        if msg.role == "tool_result":
            out.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.tool_result_for or "",
                            "content": msg.content,
                        }
                    ],
                }
            )
    return out


def _extract_blocks(response: Any) -> tuple[str, list[dict[str, Any]]]:
    """Return ``(text, tool_uses)`` parsed from an Anthropic ``Message``.

    The structure expected:

    * ``response.content`` is iterable; each item has ``type``.
    * Type ``"text"``     → object has ``.text``.
    * Type ``"tool_use"`` → object has ``.id`` / ``.name`` / ``.input``.

    Both real SDK responses and ``MagicMock`` doubles using dicts work.
    """

    content = getattr(response, "content", None) or []
    text_parts: list[str] = []
    tool_uses: list[dict[str, Any]] = []
    for block in content:
        block_type = getattr(block, "type", None) or (
            block.get("type") if isinstance(block, dict) else None
        )
        if block_type == "text":
            text = (
                getattr(block, "text", None)
                if not isinstance(block, dict)
                else block.get("text")
            )
            if isinstance(text, str):
                text_parts.append(text)
        elif block_type == "tool_use":
            tu_id = (
                getattr(block, "id", None)
                if not isinstance(block, dict)
                else block.get("id")
            )
            name = (
                getattr(block, "name", None)
                if not isinstance(block, dict)
                else block.get("name")
            )
            tu_input = (
                getattr(block, "input", None)
                if not isinstance(block, dict)
                else block.get("input")
            )
            tool_uses.append(
                {
                    "id": str(tu_id or ""),
                    "name": str(name or ""),
                    "input": tu_input if isinstance(tu_input, dict) else {},
                }
            )
    return "".join(text_parts), tool_uses


def _chunk_text(text: str, *, size: int = _DELTA_CHUNK_CHARS) -> list[str]:
    """Split ``text`` into roughly ``size``-char chunks for pseudo-streaming."""

    if not text:
        return []
    return [text[i : i + size] for i in range(0, len(text), size)]


def _insert_llm_cost_row(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    created_at: str,
) -> str:
    cursor = conn.execute(
        "INSERT INTO llm_costs "
        "(decision_id, model, input_tokens, output_tokens, cost_usd, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (decision_id, model, input_tokens, output_tokens, cost_usd, created_at),
    )
    conn.commit()
    return str(cursor.lastrowid)


class ChatAgent:
    """Async generator–driven chat agent."""

    def __init__(
        self,
        *,
        model: str,
        tools: list[ToolHandler] | None = None,
        anthropic_client: Any,
        conn: sqlite3.Connection,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        max_history: int = _DEFAULT_MAX_HISTORY,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> None:
        self.model = model
        self.tools = tools if tools is not None else BUILTIN_TOOLS
        self.anthropic_client = anthropic_client
        self.conn = conn
        self.system_prompt = system_prompt
        self.max_history = max_history
        self.max_tokens = max_tokens

    def _build_tool_schemas(self) -> list[dict[str, Any]]:
        """Convert ``ToolHandler``s into Anthropic ``tools=`` payloads."""

        out: list[dict[str, Any]] = []
        for tool in self.tools:
            schema = tool.args_model.model_json_schema()
            # Anthropic expects {"type":"object","properties":{...},"required":[...]}
            payload = {
                "name": tool.name,
                "description": tool.description,
                "input_schema": {
                    "type": "object",
                    "properties": schema.get("properties", {}),
                    "required": schema.get("required", []),
                },
            }
            out.append(payload)
        return out

    async def stream(
        self, history: list[ChatMessage]
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield agent events for the next assistant turn(s).

        See module docstring for event taxonomy and the v0 chunking
        trade-off versus true token-level streaming.
        """

        start = time.perf_counter()
        message_id = _new_message_id()
        accumulated_text_parts: list[str] = []
        accumulated_tool_uses: list[dict[str, Any]] = []
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0
        llm_cost_id: str | None = None

        # Anthropic conversation we accumulate across tool-use turns.
        api_messages = _serialise_chat_messages(
            history, max_history=self.max_history
        )

        tool_schemas = self._build_tool_schemas()

        for _turn in range(_MAX_TOOL_TURNS):
            try:
                response = await asyncio.to_thread(
                    self.anthropic_client.messages.create,
                    model=self.model,
                    system=self.system_prompt,
                    max_tokens=self.max_tokens,
                    tools=tool_schemas,
                    messages=api_messages,
                )
            except Exception as exc:  # noqa: BLE001
                yield {
                    "event": "error",
                    "code": _classify_anthropic_error(exc),
                    "message": f"{type(exc).__name__}: {exc!s}"[:300],
                }
                return

            # Accumulate token usage.
            usage = getattr(response, "usage", None)
            if usage is not None:
                input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
                output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
            else:
                input_tokens = output_tokens = 0
            total_input_tokens += input_tokens
            total_output_tokens += output_tokens
            total_cost += compute_cost_usd(
                self.model, input_tokens, output_tokens
            )

            text, tool_uses = _extract_blocks(response)

            # Emit deltas for the visible text portion of this turn.
            for chunk in _chunk_text(text):
                yield {"event": "delta", "text": chunk}
                # Yield to the event loop so the route can flush bytes
                # to the client between chunks.
                await asyncio.sleep(0)
            if text:
                accumulated_text_parts.append(text)

            stop_reason = getattr(response, "stop_reason", None)
            if not tool_uses or stop_reason != "tool_use":
                # Final assistant turn; persist record and emit done.
                created_at = _now_tpe_iso()
                if total_input_tokens or total_output_tokens or total_cost:
                    llm_cost_id = _insert_llm_cost_row(
                        self.conn,
                        decision_id=f"chat:{message_id}",
                        model=self.model,
                        input_tokens=total_input_tokens,
                        output_tokens=total_output_tokens,
                        cost_usd=total_cost,
                        created_at=created_at,
                    )
                yield {
                    "event": "done",
                    "message_id": message_id,
                    "elapsed_ms": int((time.perf_counter() - start) * 1000),
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "cost_usd": total_cost,
                    "llm_cost_id": llm_cost_id,
                    "assistant_text": "".join(accumulated_text_parts),
                    "tool_calls": list(accumulated_tool_uses),
                }
                return

            # Otherwise dispatch every tool_use block, feed results back.
            assistant_blocks: list[dict[str, Any]] = []
            if text:
                assistant_blocks.append({"type": "text", "text": text})
            tool_result_blocks: list[dict[str, Any]] = []
            for tu in tool_uses:
                yield {
                    "event": "tool_call",
                    "id": tu["id"],
                    "name": tu["name"],
                    "args": tu["input"],
                }
                accumulated_tool_uses.append(
                    {"id": tu["id"], "name": tu["name"], "args": tu["input"]}
                )
                result = dispatch_tool(
                    tu["name"], tu["input"], self.conn, tools=self.tools
                )
                yield {
                    "event": "tool_result",
                    "tool_call_id": tu["id"],
                    "result": result,
                }
                assistant_blocks.append(
                    {
                        "type": "tool_use",
                        "id": tu["id"],
                        "name": tu["name"],
                        "input": tu["input"],
                    }
                )
                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

            api_messages = [
                *api_messages,
                {"role": "assistant", "content": assistant_blocks},
                {"role": "user", "content": tool_result_blocks},
            ]

        # Hit the tool-turn cap; surface as an error so the UI doesn't hang.
        yield {
            "event": "error",
            "code": "tool_turn_limit",
            "message": f"exceeded {_MAX_TOOL_TURNS} tool turns",
        }


def _classify_anthropic_error(exc: Exception) -> str:
    """Map common Anthropic SDK errors to short stable codes."""

    name = type(exc).__name__
    lname = name.lower()
    if "ratelimit" in lname:
        return "rate_limit"
    if "overloaded" in lname:
        return "overloaded"
    if "timeout" in lname:
        return "timeout"
    if "auth" in lname or "permission" in lname:
        return "auth_error"
    if "badrequest" in lname or "invalid" in lname:
        return "invalid_request"
    return "agent_failed"


__all__ = [
    "ChatAgent",
    "DEFAULT_SYSTEM_PROMPT",
]
