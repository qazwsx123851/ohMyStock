"""Best-effort chat session title autogeneration.

Spec: openspec/changes/admin-chat-sessions-endpoints-and-pages/specs/chat-agent-runtime/spec.md

The HTTP route fires this as ``asyncio.create_task(autogen_title(...))``
after the first successful assistant turn and updates the session row
when it returns a non-fallback string. ``autogen_title`` MUST be
fail-safe — any exception (timeout, API error, empty response, parse
error) collapses to the literal ``"新對話"`` so the background task
never crashes the request loop or the ASGI lifespan.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ohmystock.chat.schema import ChatMessage


FALLBACK_TITLE = "新對話"
_TITLE_MAX_CODEPOINTS = 16
_SYSTEM_PROMPT = (
    "以 16 個 TW Mandarin 字以內摘要這段對話的主題。"
    "只回標題本文，不加引號、不加說明。"
)


def _format_user_payload(messages: list[ChatMessage]) -> str:
    """Format the last 4 messages as a single string for Haiku to summarise."""

    recent = messages[-4:]
    lines: list[str] = []
    for m in recent:
        role_label = {
            "user": "使用者",
            "assistant": "助手",
            "tool_result": "工具結果",
        }.get(m.role, m.role)
        # Trim long content so we stay well under the title model's context.
        snippet = (m.content or "")[:400]
        lines.append(f"{role_label}：{snippet}")
    return "\n".join(lines)


def _extract_title_text(response: Any) -> str:
    content = getattr(response, "content", None) or []
    parts: list[str] = []
    for block in content:
        block_type = getattr(block, "type", None) or (
            block.get("type") if isinstance(block, dict) else None
        )
        if block_type != "text":
            continue
        text = (
            getattr(block, "text", None)
            if not isinstance(block, dict)
            else block.get("text")
        )
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts).strip().strip('"\'「」').strip()


async def autogen_title(
    messages: list[ChatMessage],
    *,
    model: str,
    anthropic_client: Any,
    timeout_seconds: float = 5.0,
) -> str:
    """Return a short title for the session; ``"新對話"`` on any failure."""

    if not messages:
        return FALLBACK_TITLE

    payload = _format_user_payload(messages)

    async def _call() -> str:
        try:
            response = await asyncio.to_thread(
                anthropic_client.messages.create,
                model=model,
                system=_SYSTEM_PROMPT,
                max_tokens=64,
                messages=[{"role": "user", "content": payload}],
            )
        except Exception:  # noqa: BLE001 — caller wants fail-safe
            return FALLBACK_TITLE

        text = _extract_title_text(response)
        if not text:
            return FALLBACK_TITLE
        return text[:_TITLE_MAX_CODEPOINTS]

    try:
        return await asyncio.wait_for(_call(), timeout=timeout_seconds)
    except (asyncio.TimeoutError, Exception):  # noqa: BLE001
        return FALLBACK_TITLE


__all__ = ["FALLBACK_TITLE", "autogen_title"]
