"""Tests for ``ohmystock.memory.store.MemoryStore``.

Spec: openspec/changes/web-admin-memory-page-and-store/specs/memory-store/spec.md
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable

import pytest
from pydantic import ValidationError

import ohmystock.memory as memory_pkg
from ohmystock.memory import (
    MemoryRow,
    MemoryStore,
    MemoryStoreError,
    init_schema,
)


def _seed(
    conn: sqlite3.Connection,
    rows: Iterable[tuple[str, str, list[str], str | None, str]],
) -> None:
    """Insert ``(kind, content, tags, source, created_at)`` tuples."""

    for kind, content, tags, source, created_at in rows:
        conn.execute(
            "INSERT INTO memory_rows(kind, content, tags, source, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (kind, content, json.dumps(tags), source, created_at),
        )
    conn.commit()


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    init_schema(c)
    try:
        yield c
    finally:
        c.close()


@pytest.fixture
def store(conn: sqlite3.Connection) -> MemoryStore:
    return MemoryStore(conn)


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------


def test_public_api_exports_exactly_five_names() -> None:
    assert set(memory_pkg.__all__) == {
        "MemoryRow",
        "MemoryKind",
        "MemoryStore",
        "MemoryStoreError",
        "init_schema",
    }
    for name in memory_pkg.__all__:
        assert hasattr(memory_pkg, name)


def test_store_exposes_no_writers(store: MemoryStore) -> None:
    assert not hasattr(store, "add")
    assert not hasattr(store, "update")
    assert not hasattr(store, "delete")


# ---------------------------------------------------------------------------
# MemoryRow model invariants
# ---------------------------------------------------------------------------


def test_memory_row_is_frozen() -> None:
    row = MemoryRow(
        id=1,
        kind="note",
        content="x",
        tags=[],
        source=None,
        created_at="2026-05-09T10:00:00+08:00",
    )
    with pytest.raises(ValidationError):
        row.kind = "lesson"  # type: ignore[misc]


def test_memory_row_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        MemoryRow(
            id=1,
            kind="note",
            content="x",
            tags=[],
            source=None,
            created_at="2026-05-09T10:00:00+08:00",
            extra="boom",  # type: ignore[call-arg]
        )


def test_memory_row_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        MemoryRow(
            id=1,
            kind="random",  # type: ignore[arg-type]
            content="x",
            tags=[],
            source=None,
            created_at="2026-05-09T10:00:00+08:00",
        )


# ---------------------------------------------------------------------------
# list()
# ---------------------------------------------------------------------------


def test_list_empty_db(store: MemoryStore) -> None:
    result = store.list()
    assert result.items == []
    assert result.total == 0
    assert result.limit == 50
    assert result.offset == 0
    assert result.has_more is False


def test_list_orders_by_created_at_desc_then_id_desc(
    conn: sqlite3.Connection, store: MemoryStore
) -> None:
    _seed(
        conn,
        [
            ("note", "a", [], None, "2026-05-09T10:00:00+08:00"),
            ("note", "b", [], None, "2026-05-09T11:00:00+08:00"),
            ("note", "c", [], None, "2026-05-09T11:00:00+08:00"),
        ],
    )
    ids = [r.id for r in store.list().items]
    assert ids == [3, 2, 1]


def test_list_filters_by_kind(
    conn: sqlite3.Connection, store: MemoryStore
) -> None:
    _seed(
        conn,
        [
            ("note", "x", [], None, "2026-05-09T10:00:00+08:00"),
            ("lesson", "y", [], None, "2026-05-09T10:01:00+08:00"),
            ("lesson", "z", [], None, "2026-05-09T10:02:00+08:00"),
        ],
    )
    result = store.list(kind="lesson")
    assert {r.kind for r in result.items} == {"lesson"}
    assert result.total == 2


def test_list_filters_by_tag(
    conn: sqlite3.Connection, store: MemoryStore
) -> None:
    _seed(
        conn,
        [
            ("note", "a", ["vcp", "breakout"], None, "2026-05-09T10:00:00+08:00"),
            ("note", "b", ["vcp"], None, "2026-05-09T10:01:00+08:00"),
            ("note", "c", ["breakout"], None, "2026-05-09T10:02:00+08:00"),
            ("note", "d", [], None, "2026-05-09T10:03:00+08:00"),
        ],
    )
    result = store.list(tag="vcp")
    assert {r.id for r in result.items} == {1, 2}


def test_list_combined_kind_and_tag(
    conn: sqlite3.Connection, store: MemoryStore
) -> None:
    _seed(
        conn,
        [
            ("note", "a", ["vcp"], None, "2026-05-09T10:00:00+08:00"),
            ("lesson", "b", ["vcp"], None, "2026-05-09T10:01:00+08:00"),
            ("lesson", "c", ["breakout"], None, "2026-05-09T10:02:00+08:00"),
        ],
    )
    result = store.list(kind="lesson", tag="vcp")
    assert [r.id for r in result.items] == [2]
    assert result.total == 1


def test_list_clamps_limit_to_200(
    conn: sqlite3.Connection, store: MemoryStore
) -> None:
    _seed(
        conn,
        [
            ("note", f"row{i}", [], None, f"2026-05-09T10:{i // 60:02d}:{i % 60:02d}+08:00")
            for i in range(300)
        ],
    )
    result = store.list(limit=999)
    assert len(result.items) == 200
    assert result.limit == 200
    assert result.total == 300
    assert result.has_more is True


def test_list_paginates_via_offset(
    conn: sqlite3.Connection, store: MemoryStore
) -> None:
    _seed(
        conn,
        [
            ("note", f"r{i}", [], None, f"2026-05-09T10:00:{i:02d}+08:00")
            for i in range(100)
        ],
    )
    page = store.list(limit=20, offset=40)
    assert len(page.items) == 20
    assert page.offset == 40
    assert page.has_more is True

    last = store.list(limit=20, offset=80)
    assert len(last.items) == 20
    assert last.has_more is False


def test_list_zero_limit_raises(store: MemoryStore) -> None:
    with pytest.raises(MemoryStoreError) as excinfo:
        store.list(limit=0)
    assert excinfo.value.code == "invalid_input"


def test_list_negative_offset_raises(store: MemoryStore) -> None:
    with pytest.raises(MemoryStoreError) as excinfo:
        store.list(offset=-1)
    assert excinfo.value.code == "invalid_input"


def test_list_garbage_kind_raises(store: MemoryStore) -> None:
    with pytest.raises(MemoryStoreError) as excinfo:
        store.list(kind="garbage")  # type: ignore[arg-type]
    assert excinfo.value.code == "invalid_input"
    assert "kind" in str(excinfo.value)


def test_list_empty_string_tag_treated_as_absent(
    conn: sqlite3.Connection, store: MemoryStore
) -> None:
    _seed(
        conn,
        [
            ("note", "x", [], None, "2026-05-09T10:00:00+08:00"),
        ],
    )
    result = store.list(tag="")
    assert result.total == 1


# ---------------------------------------------------------------------------
# search()
# ---------------------------------------------------------------------------


def test_search_orders_by_bm25(
    conn: sqlite3.Connection, store: MemoryStore
) -> None:
    _seed(
        conn,
        [
            ("note", "breakout breakout breakout", [], None, "2026-05-09T10:00:00+08:00"),
            ("note", "breakout once", [], None, "2026-05-09T10:00:01+08:00"),
            ("note", "unrelated", [], None, "2026-05-09T10:00:02+08:00"),
        ],
    )
    result = store.search(q="breakout")
    assert [r.id for r in result.items][:2] == [1, 2]
    assert result.total == 2


def test_search_empty_q_raises(store: MemoryStore) -> None:
    with pytest.raises(MemoryStoreError) as excinfo:
        store.search(q="")
    assert excinfo.value.code == "invalid_input"


def test_search_whitespace_only_q_raises(store: MemoryStore) -> None:
    with pytest.raises(MemoryStoreError) as excinfo:
        store.search(q="   \t\n")
    assert excinfo.value.code == "invalid_input"


def test_search_control_chars_only_raises(store: MemoryStore) -> None:
    with pytest.raises(MemoryStoreError) as excinfo:
        store.search(q="\x00\x01")
    assert excinfo.value.code == "invalid_input"


def test_search_strips_control_chars_then_matches(
    conn: sqlite3.Connection, store: MemoryStore
) -> None:
    _seed(
        conn,
        [("note", "hello world", [], None, "2026-05-09T10:00:00+08:00")],
    )
    result = store.search(q="hello\x00 world")
    assert {r.id for r in result.items} == {1}


def test_search_invalid_query_remap(
    conn: sqlite3.Connection, store: MemoryStore
) -> None:
    _seed(
        conn,
        [("note", "x", [], None, "2026-05-09T10:00:00+08:00")],
    )
    with pytest.raises(MemoryStoreError) as excinfo:
        store.search(q="foo OR")
    assert excinfo.value.code == "invalid_query"
    # The exception message must be the safe canned string, not the raw
    # SQLite OperationalError text.
    assert excinfo.value.message == "FTS5 query syntax error"


def test_search_honours_fts5_boolean(
    conn: sqlite3.Connection, store: MemoryStore
) -> None:
    _seed(
        conn,
        [
            ("note", "VCP breakout", [], None, "2026-05-09T10:00:00+08:00"),
            ("note", "VCP only", [], None, "2026-05-09T10:00:01+08:00"),
            ("note", "breakout only", [], None, "2026-05-09T10:00:02+08:00"),
        ],
    )
    result = store.search(q="VCP AND breakout")
    assert [r.id for r in result.items] == [1]
    assert result.total == 1


def test_search_no_hits_returns_empty(store: MemoryStore) -> None:
    result = store.search(q="zzzzzzzz")
    assert result.items == []
    assert result.total == 0
    assert result.has_more is False


def test_search_clamps_limit_to_200(
    conn: sqlite3.Connection, store: MemoryStore
) -> None:
    _seed(
        conn,
        [
            ("note", "common", [], None, f"2026-05-09T10:{i // 60:02d}:{i % 60:02d}+08:00")
            for i in range(250)
        ],
    )
    result = store.search(q="common", limit=999)
    assert len(result.items) == 200
    assert result.limit == 200
    assert result.total == 250
    assert result.has_more is True
