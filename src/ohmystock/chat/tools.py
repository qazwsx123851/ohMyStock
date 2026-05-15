"""Read-only tool wrappers callable by the chat agent.

Spec: openspec/changes/admin-chat-sessions-endpoints-and-pages/specs/chat-agent-runtime/spec.md

v0 invariant: every tool here is **read-only**. The agent cannot place
orders, write to the trade journal, change confirm-gate state, mutate
Settings, or run screeners. The four tools cover the chat use cases
documented in ``docs/user-scenarios.md``:

* ``query_journal``     — fetch past entry / exit / reject rows for a symbol
* ``search_memory``     — FTS5 search over curated lessons / proposals
* ``get_market_symbol`` — current quote + bars + RS / SEPA / institutional
* ``list_skills``       — registry of skill cheatsheets (name + description)

Each tool exposes a frozen pydantic ``args_model`` whose ``extra="forbid"``
keeps the agent from sneaking unknown fields past validation. The
dispatcher catches any handler exception and degrades to a ``{"error":
"..."}`` payload — the agent sees the failure but the outer streaming
loop never propagates it.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

import ohmystock.skills as _skills_pkg
from ohmystock.api.routes.market import aggregate_symbol
from ohmystock.memory import MemoryStore, MemoryStoreError
from ohmystock.skills.loader import load_skills


# ---------------------------------------------------------------------------
# ToolHandler + dispatcher
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolHandler:
    """One read-only tool exposed to the chat agent.

    ``args_model`` MUST be a frozen pydantic model with ``extra="forbid"``
    so the dispatcher rejects unknown args before any DB / FS access.
    """

    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[BaseModel, sqlite3.Connection], dict[str, Any]]


def _err(code: str, detail: str) -> dict[str, Any]:
    """Uniform error payload returned to the agent (never raised)."""

    return {"error": f"{code}: {detail}"}


def dispatch_tool(
    name: str,
    args: dict[str, Any] | None,
    conn: sqlite3.Connection,
    *,
    tools: list[ToolHandler] | None = None,
) -> dict[str, Any]:
    """Dispatch a tool call, catching any handler exception.

    The result is always a JSON-serialisable dict. On error the dict is
    ``{"error": "<code>: <detail>"}`` — never a raised exception.
    """

    registry = tools if tools is not None else BUILTIN_TOOLS
    by_name = {t.name: t for t in registry}
    tool = by_name.get(name)
    if tool is None:
        return _err("unknown_tool", name)

    try:
        validated = tool.args_model.model_validate(args or {})
    except ValidationError as exc:
        return _err("invalid_args", str(exc))

    try:
        return tool.handler(validated, conn)
    except Exception as exc:  # noqa: BLE001 — caught & surfaced as data
        detail = f"{type(exc).__name__}: {exc!s}"
        return _err("tool_failed", detail[:200])


# ---------------------------------------------------------------------------
# Tool: query_journal
# ---------------------------------------------------------------------------


_VALID_JOURNAL_KINDS: frozenset[str] = frozenset(
    {"entry", "exit", "reject", "expire", "auto_execute_audit"}
)


class QueryJournalArgs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str | None = None
    date_from: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    date_to: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    status: str | None = None  # accepts journal "kind" column
    limit: int = Field(default=20, ge=1, le=50)


def _query_journal_handler(
    args: QueryJournalArgs, conn: sqlite3.Connection
) -> dict[str, Any]:
    if args.status is not None and args.status not in _VALID_JOURNAL_KINDS:
        return _err(
            "invalid_status",
            f"expected one of {sorted(_VALID_JOURNAL_KINDS)}, "
            f"got {args.status!r}",
        )
    if (
        args.date_from is not None
        and args.date_to is not None
        and args.date_from > args.date_to
    ):
        return _err("invalid_input", "date_from > date_to")

    clauses: list[str] = []
    params: list[Any] = []
    if args.symbol is not None:
        clauses.append("symbol = ?")
        params.append(args.symbol)
    if args.status is not None:
        clauses.append("kind = ?")
        params.append(args.status)
    if args.date_from is not None:
        clauses.append("substr(created_at, 1, 10) >= ?")
        params.append(args.date_from)
    if args.date_to is not None:
        clauses.append("substr(created_at, 1, 10) <= ?")
        params.append(args.date_to)
    where_sql = " WHERE " + " AND ".join(clauses) if clauses else ""

    total_row = conn.execute(
        f"SELECT COUNT(*) FROM journal_entries{where_sql}", params
    ).fetchone()
    total = int(total_row[0]) if total_row is not None else 0

    rows = conn.execute(
        f"""
        SELECT id, decision_id, kind, symbol, created_at, payload_json
        FROM journal_entries{where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        [*params, args.limit],
    ).fetchall()

    items: list[dict[str, Any]] = []
    for r in rows:
        try:
            payload = json.loads(r[5])
        except (TypeError, ValueError):
            payload = {}
        items.append(
            {
                "id": int(r[0]),
                "decision_id": r[1],
                "kind": r[2],
                "symbol": r[3],
                "created_at": r[4],
                "payload": payload if isinstance(payload, dict) else {},
            }
        )

    return {"rows": items, "total": total}


# ---------------------------------------------------------------------------
# Tool: search_memory
# ---------------------------------------------------------------------------


_MEMORY_KINDS: frozenset[str] = frozenset(
    {"note", "lesson", "proposal", "review_summary"}
)


class SearchMemoryArgs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    q: str = ""
    kind: str | None = None
    tag: str | None = None
    limit: int = Field(default=20, ge=1, le=50)


def _search_memory_handler(
    args: SearchMemoryArgs, conn: sqlite3.Connection
) -> dict[str, Any]:
    if args.kind is not None and args.kind not in _MEMORY_KINDS:
        return _err(
            "invalid_kind",
            f"expected one of {sorted(_MEMORY_KINDS)}, got {args.kind!r}",
        )

    store = MemoryStore(conn)
    try:
        if args.q.strip():
            result = store.search(q=args.q, limit=args.limit)
        else:
            result = store.list(
                kind=args.kind, tag=args.tag, limit=args.limit
            )
    except MemoryStoreError as exc:
        return _err(exc.code, exc.message or "memory store error")

    return {
        "rows": [row.model_dump() for row in result.items],
        "total": result.total,
    }


# ---------------------------------------------------------------------------
# Tool: get_market_symbol
# ---------------------------------------------------------------------------


class GetMarketSymbolArgs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str = Field(min_length=1)
    days: int = Field(default=60, ge=1, le=252)


def _get_market_symbol_handler(
    args: GetMarketSymbolArgs, conn: sqlite3.Connection
) -> dict[str, Any]:
    data = aggregate_symbol(conn, args.symbol, args.days)
    if data is None:
        return _err("not_found", args.symbol)
    return data.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Tool: list_skills
# ---------------------------------------------------------------------------


_REGISTRY_DIR: Path = (
    Path(_skills_pkg.__file__).resolve().parent / "registry"
)


class ListSkillsArgs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    category: str | None = None


def _list_skills_handler(
    args: ListSkillsArgs, conn: sqlite3.Connection  # noqa: ARG001 — conn unused
) -> dict[str, Any]:
    specs = load_skills(_REGISTRY_DIR)
    filtered = [
        s
        for s in specs
        if args.category is None or s.category == args.category
    ]
    return {
        "rows": [
            {
                "name": s.name,
                "description": s.description,
                "category": s.category,
                "cited_specs": list(s.cited_specs),
            }
            for s in filtered
        ],
        "total": len(filtered),
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


BUILTIN_TOOLS: list[ToolHandler] = [
    ToolHandler(
        name="query_journal",
        description=(
            "Search trade journal entries by symbol / date / kind. "
            "Returns up to 50 rows ordered by created_at DESC."
        ),
        args_model=QueryJournalArgs,
        handler=_query_journal_handler,
    ),
    ToolHandler(
        name="search_memory",
        description=(
            "FTS5 BM25 search over curated lessons / proposals / review "
            "summaries. Empty q falls back to a recency listing."
        ),
        args_model=SearchMemoryArgs,
        handler=_search_memory_handler,
    ),
    ToolHandler(
        name="get_market_symbol",
        description=(
            "Fetch current quote, recent bars, RS rating, SEPA stage, "
            "institutional flows, and pattern history for one symbol."
        ),
        args_model=GetMarketSymbolArgs,
        handler=_get_market_symbol_handler,
    ),
    ToolHandler(
        name="list_skills",
        description=(
            "List skill cheatsheets in the registry. Each row carries "
            "name / description / category / cited_specs (no body)."
        ),
        args_model=ListSkillsArgs,
        handler=_list_skills_handler,
    ),
]


__all__ = [
    "BUILTIN_TOOLS",
    "GetMarketSymbolArgs",
    "ListSkillsArgs",
    "QueryJournalArgs",
    "SearchMemoryArgs",
    "ToolHandler",
    "dispatch_tool",
]
