"""Coverage for review.nodes.data_loader.

Spec: openspec/changes/phase5-review-mvp/specs/post-trade-review-pipeline/spec.md
Requirement: data_loader 走 deterministic pure-data 路徑
"""

from __future__ import annotations

import json
from datetime import date

from ohmystock.review.nodes.data_loader import run_data_loader

from tests.review.conftest import (
    StaticMarketData,
    insert_entry,
    insert_exit,
    insert_expire,
    insert_reject,
)


def _setup_one_trade(conn) -> None:
    insert_entry(
        conn,
        decision_id="dec-1",
        symbol="2330",
        created_at="2026-04-15T14:36:18+08:00",
        actual_entry_price=845.0,
        cited_skills=["technical/breakout"],
    )
    insert_exit(
        conn,
        decision_id="dec-1",
        symbol="2330",
        created_at="2026-04-22T13:30:00+08:00",
        actual_exit_price=900.0,
        exit_tag="hit_t1",
        pnl_pct=6.5,
        hold_days=5,
    )


def test_post_exit_returns_match_spec_example(journal_conn):
    _setup_one_trade(journal_conn)
    closes_after_exit: list[float] = []
    closes_after_exit.extend([900.0] * 4)
    closes_after_exit.append(916.0)
    closes_after_exit.extend([910.0] * 4)
    closes_after_exit.append(940.0)
    closes_after_exit.extend([910.0] * 9)
    closes_after_exit.append(880.0)
    md = StaticMarketData({("2330", "2026-04-22"): closes_after_exit})

    out = run_data_loader(
        date(2026, 4, 1), date(2026, 4, 30), journal_conn, md
    )

    assert len(out.trades) == 1
    t = out.trades[0]
    assert t.post_exit_return_5d == 0.0178
    assert t.post_exit_return_10d == 0.0444
    assert t.post_exit_return_20d == -0.0222
    assert t.data_missing is False


def test_data_missing_when_fewer_than_twenty_closes(journal_conn):
    _setup_one_trade(journal_conn)
    md = StaticMarketData({("2330", "2026-04-22"): [900.0] * 19})

    out = run_data_loader(
        date(2026, 4, 1), date(2026, 4, 30), journal_conn, md
    )

    assert len(out.trades) == 1
    t = out.trades[0]
    assert t.data_missing is True
    assert t.post_exit_return_5d is None
    assert t.post_exit_return_10d is None
    assert t.post_exit_return_20d is None


def test_byte_identical_rerun(journal_conn):
    _setup_one_trade(journal_conn)
    md = StaticMarketData({("2330", "2026-04-22"): [905.0] * 21})

    out1 = run_data_loader(
        date(2026, 4, 1), date(2026, 4, 30), journal_conn, md
    )
    out2 = run_data_loader(
        date(2026, 4, 1), date(2026, 4, 30), journal_conn, md
    )

    s1 = json.dumps(
        out1.model_dump(mode="json", by_alias=True),
        sort_keys=True,
        ensure_ascii=False,
    )
    s2 = json.dumps(
        out2.model_dump(mode="json", by_alias=True),
        sort_keys=True,
        ensure_ascii=False,
    )
    assert s1 == s2


def test_empty_period(journal_conn):
    md = StaticMarketData()
    out = run_data_loader(
        date(2026, 4, 1), date(2026, 4, 30), journal_conn, md
    )
    assert out.trades == []
    assert out.rejected == []
    assert out.expired == []
    assert out.stats.total_entries == 0
    assert out.stats.total_rejects == 0
    assert out.stats.total_expires == 0
    assert out.stats.expire_rate == 0.0


def test_rejects_and_expires_collected(journal_conn):
    _setup_one_trade(journal_conn)
    insert_reject(
        journal_conn,
        decision_id="dec-r1",
        symbol="2454",
        created_at="2026-04-10T09:30:00+08:00",
        reject_layer="pre_check",
        reject_reason="同產業已有 2 檔",
    )
    insert_expire(
        journal_conn,
        decision_id="dec-e1",
        symbol="3008",
        created_at="2026-04-12T10:00:00+08:00",
    )
    md = StaticMarketData({("2330", "2026-04-22"): [905.0] * 21})

    out = run_data_loader(
        date(2026, 4, 1), date(2026, 4, 30), journal_conn, md
    )
    assert len(out.rejected) == 1
    assert out.rejected[0].reject_layer == "pre_check"
    assert len(out.expired) == 1
    assert out.expired[0].symbol == "3008"
    assert out.stats.total_rejects == 1
    assert out.stats.total_expires == 1


def test_limit_trades_truncates_only_trades(journal_conn):
    for i in range(5):
        decision_id = f"dec-{i}"
        entry_day = 10 + i
        insert_entry(
            journal_conn,
            decision_id=decision_id,
            symbol=f"233{i}",
            created_at=f"2026-04-{entry_day:02d}T14:00:00+08:00",
            actual_entry_price=100.0 + i,
        )
        insert_exit(
            journal_conn,
            decision_id=decision_id,
            symbol=f"233{i}",
            created_at=f"2026-04-{entry_day + 5:02d}T13:30:00+08:00",
            actual_exit_price=106.0 + i,
        )
    insert_reject(
        journal_conn,
        decision_id="dec-rj",
        symbol="9999",
        created_at="2026-04-11T09:00:00+08:00",
    )
    md = StaticMarketData(
        {(f"233{i}", f"2026-04-{10 + i + 5:02d}"): [105.0] * 21 for i in range(5)}
    )

    out = run_data_loader(
        date(2026, 4, 1),
        date(2026, 4, 30),
        journal_conn,
        md,
        limit_trades=3,
    )

    assert len(out.trades) == 3
    assert [t.decision_id for t in out.trades] == ["dec-0", "dec-1", "dec-2"]
    assert len(out.rejected) == 1
