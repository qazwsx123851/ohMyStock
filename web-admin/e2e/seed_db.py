"""E2E-only SQLite schema + fixture seeder.

Playwright's globalSetup runs this against a throwaway DB pointed to by
``OHMYSTOCK_DB_PATH`` (a temp file) and a throwaway proposals root pointed to
by ``PROPOSALS_DIR``. Seeds deterministic fixtures for the GWT scenario specs
(docs/web-admin-user-testing-spec.md): pending_confirm decisions (Tier 0),
proposal markdown files in every status (Tier 1), bars_daily for WFA/backtest
(Tier 1/2), open positions + audit rows (Tier 3), memory rows (Tier 4).

NEVER point OHMYSTOCK_DB_PATH at the real journal.db or PROPOSALS_DIR at the
repo's real proposals/: global-setup wipes both each run.

Run: ``uv run python web-admin/e2e/seed_db.py``
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ohmystock.backtest.storage import init_schema as init_backtest
from ohmystock.chat.schema import ChatMessage, ChatSession
from ohmystock.chat.storage import init_schema as init_chat
from ohmystock.chat.storage import insert_message, insert_session
from ohmystock.chip.cache import init_chip_schema, insert_three_major_rows
from ohmystock.data.cache import init_market_data_schema, insert_bars
from ohmystock.data.disposition import init_schema as init_disposition
from ohmystock.data.sources.base import BarRow
from ohmystock.journal.schema import init_schema as init_journal
from ohmystock.memory.schema import init_schema as init_memory
from ohmystock.proposal import ProposalDraft, transition_proposal, write_proposal
from ohmystock.review.index import upsert_index_entry
from ohmystock.review.models import IndexEntry, Period
from ohmystock.sepa.rs import init_schema as init_rs
from ohmystock.swarm_runs.storage import init_schema as init_swarm_runs

_INITS = (
    init_journal,
    init_swarm_runs,
    init_memory,
    init_chat,
    init_backtest,
    init_disposition,
    init_rs,
    init_market_data_schema,
    init_chip_schema,
)

_TPE = timezone(timedelta(hours=8))


# ---------------------------------------------------------------------------
# journal_entries fixtures
# ---------------------------------------------------------------------------


def _insert_journal(
    conn: sqlite3.Connection,
    decision_id: str,
    kind: str,
    symbol: str,
    created_at: str,
    payload: dict,
) -> None:
    conn.execute(
        "INSERT INTO journal_entries "
        "(decision_id, kind, symbol, created_at, payload_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (decision_id, kind, symbol, created_at, json.dumps(payload)),
    )


def _pending_payload(sizing_pct: float, price: float, atr_pct: float) -> dict:
    return {
        "decision_status": "pending_confirm",
        "final_sizing_pct": sizing_pct,
        "current_price": price,
        "atr_14_pct": atr_pct,
        "entry_thesis": "e2e fixture entry thesis",
    }


def seed_journal(conn: sqlite3.Connection, now: datetime) -> None:
    now_iso = now.isoformat()

    # --- Tier 0: pending_confirm queue (distinct id per CG test) ---
    # price 100 / sizing 10% / capital 1M -> system qty 1000 shares (CG-B1 math).
    # All prices kept <= 250 so 1 lot stays under the 25% notional cap (the UI
    # confirm dialog always sends override_qty, which enforces the cap).
    for did, symbol, price in (
        # NOTE: symbols must stay unique among entries that end up as OPEN
        # positions (PaperPositionsPage rowKey = symbol). 2330/0050 belong to
        # the e2e-pp-* fixtures.
        ("e2e-cg-01", "3034", 200.0),
        ("e2e-cg-02", "2317", 105.0),
        ("e2e-cg-04a", "2603", 120.0),
        ("e2e-cg-04b", "2609", 38.5),
        ("e2e-cg-b1", "1216", 100.0),
        ("e2e-cg-b2", "2882", 25.0),
    ):
        _insert_journal(
            conn, did, "entry", symbol, now_iso, _pending_payload(10.0, price, 2.0)
        )

    # Expired pending entry (created 2h ago, TTL 30min) — CG-03 sweep target.
    expired_iso = (now - timedelta(hours=2)).isoformat()
    _insert_journal(
        conn,
        "e2e-cg-03",
        "entry",
        "2454",
        expired_iso,
        _pending_payload(10.0, 1000.0, 2.5),
    )

    # --- Tier 3: open positions (confirmed entries, no exit) ---
    pp1_ts = (now - timedelta(days=5)).isoformat()
    _insert_journal(
        conn,
        "e2e-pp-01",
        "entry",
        "2330",
        pp1_ts,
        {
            "decision_status": "confirmed",
            "sector": "半導體",
            "actual_entry_price": 600.0,
            "actual_qty": 2,
            "stop_loss": 570.0,
            "t1_target": 660.0,
            "time_stop_date": (now + timedelta(days=25)).date().isoformat(),
        },
    )
    # Second position with missing t1_target / time_stop_date (PP-03 缺值).
    pp2_ts = (now - timedelta(days=2)).isoformat()
    _insert_journal(
        conn,
        "e2e-pp-02",
        "entry",
        "0050",
        pp2_ts,
        {
            "decision_status": "confirmed",
            "sector": "ETF",
            "actual_entry_price": 180.0,
            "actual_qty": 1,
            "stop_loss": 171.0,
        },
    )

    # --- Tier 3: audit rows, one per remaining kind + a closed trade pair ---
    t = now - timedelta(days=10)
    _insert_journal(
        conn,
        "e2e-au-trade",
        "entry",
        "2603",
        t.isoformat(),
        {
            "decision_status": "confirmed",
            "actual_entry_price": 100.0,
            "actual_qty": 1,
            "entry_thesis": "e2e closed trade",
        },
    )
    _insert_journal(
        conn,
        "e2e-au-trade",
        "exit",
        "2603",
        (t + timedelta(days=3)).isoformat(),
        {"exit_reason": "t1_hit", "pnl_pct": 5.0, "price": 105.0, "qty": 1},
    )
    _insert_journal(
        conn,
        "e2e-au-rej",
        "reject",
        "3008",
        (t + timedelta(days=1)).isoformat(),
        {"reason": "risk gate red", "reject_layer": "human"},
    )
    _insert_journal(
        conn,
        "e2e-au-exp",
        "expire",
        "2308",
        (t + timedelta(days=2)).isoformat(),
        {"reason": "confirm timeout", "decision_status": "expired"},
    )
    _insert_journal(
        conn,
        "e2e-au-auto",
        "auto_execute_audit",
        "2412",
        (t + timedelta(days=4)).isoformat(),
        {"confidence": 0.91, "executed_qty": 1000, "clamped": False},
    )


# ---------------------------------------------------------------------------
# memory_rows fixtures
# ---------------------------------------------------------------------------


def seed_memory(conn: sqlite3.Connection, now: datetime) -> None:
    rows = [
        ("note", "台積電 法說會 重點觀察：先進製程稼動率", ["2330", "earnings"], "e2e"),
        ("lesson", "停損紀律：跌破 ATR 停損價不凹單", ["discipline"], "e2e"),
        ("proposal", "建議調整 sizing 公式上限", ["sizing"], "e2e"),
        ("review_summary", "五月復盤摘要：勝率 55%", ["review"], "e2e"),
    ]
    for i, (kind, content, tags, source) in enumerate(rows):
        conn.execute(
            "INSERT INTO memory_rows (kind, content, tags, source, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                kind,
                content,
                json.dumps(tags),
                source,
                (now - timedelta(minutes=i)).isoformat(),
            ),
        )


# ---------------------------------------------------------------------------
# bars_daily fixtures (Tier 1 WFA validate + Tier 2 backtest)
# ---------------------------------------------------------------------------


def _trading_days(start: date, n: int) -> list[date]:
    days: list[date] = []
    current = start
    while len(days) < n:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _uptrend_bars(n: int, base: float) -> list[BarRow]:
    """Monotonic up-trend, Mon-Fri from 2025-01-02 (pytest-proven pass recipe)."""
    rows: list[BarRow] = []
    for i, d in enumerate(_trading_days(date(2025, 1, 2), n)):
        price = base + i * 0.5
        rows.append(
            BarRow(
                ts=d.isoformat(),
                o=price,
                h=price,
                l=price,
                c=price,
                v=1_000_000,
                amount=int(price * 1_000_000),
            )
        )
    return rows


def _choppy_bars(n: int, base: float) -> list[BarRow]:
    """Trendless sine-wave chop — whipsaws SMA crossovers (fail recipe)."""
    rows: list[BarRow] = []
    for i, d in enumerate(_trading_days(date(2025, 1, 2), n)):
        price = base * (1.0 + 0.15 * math.sin(i / 3.0))
        rows.append(
            BarRow(
                ts=d.isoformat(),
                o=price,
                h=price * 1.005,
                l=price * 0.995,
                c=price,
                v=500_000,
                amount=int(price * 500_000),
            )
        )
    return rows


def seed_bars(conn: sqlite3.Connection) -> None:
    fetched = datetime.now(_TPE).isoformat()
    insert_bars(conn, "2330", _uptrend_bars(253, 100.0), "e2e", fetched)
    insert_bars(conn, "0050", _uptrend_bars(253, 50.0), "e2e", fetched)
    insert_bars(conn, "2317", _uptrend_bars(253, 80.0), "e2e", fetched)
    insert_bars(conn, "1101", _choppy_bars(253, 40.0), "e2e", fetched)


# ---------------------------------------------------------------------------
# chat fixtures (tier5: sessions CRUD + FTS5 search; zero-LLM)
# ---------------------------------------------------------------------------


def seed_chat(conn: sqlite3.Connection) -> None:
    """3 sessions with fixed timestamps. ASCII FTS token `e2etokenalpha`
    because FTS5 unicode61 does not tokenise CJK-only content reliably.
    The 05-01 vs 05-02 date spread drives the search date-range filter."""

    def session(sid: str, title: str, status: str, created: str, updated: str):
        insert_session(
            conn,
            ChatSession(
                id=sid,
                title=title,
                model="claude-sonnet-4-6",
                status=status,  # type: ignore[arg-type]
                created_at=created,
                updated_at=updated,
            ),
        )

    def message(mid: str, sid: str, role: str, content: str, created: str):
        insert_message(
            conn,
            ChatMessage(
                id=mid,
                session_id=sid,
                role=role,  # type: ignore[arg-type]
                content=content,
                created_at=created,
            ),
        )

    # A: detail page + missing_api_key send target (2 messages).
    session(
        "chat_e2e00001",
        "e2e 固定對話 A",
        "active",
        "2026-05-01T10:00:00+08:00",
        "2026-05-01T10:01:00+08:00",
    )
    message(
        "msg_aaaaaaaaaa01",
        "chat_e2e00001",
        "user",
        "請幫我看台積電走勢 e2etokenalpha",
        "2026-05-01T10:00:30+08:00",
    )
    message(
        "msg_aaaaaaaaaa02",
        "chat_e2e00001",
        "assistant",
        "e2e fixture 回覆：已收到。",
        "2026-05-01T10:01:00+08:00",
    )

    # B: UI delete target (0 messages).
    session(
        "chat_e2e00002",
        "e2e 固定對話 B",
        "active",
        "2026-05-01T11:00:00+08:00",
        "2026-05-01T11:00:00+08:00",
    )

    # Deleted: drives (已刪除) search badge + session_deleted detail page.
    session(
        "chat_e2e00003",
        "e2e 已刪除對話",
        "deleted",
        "2026-05-02T09:00:00+08:00",
        "2026-05-02T09:05:00+08:00",
    )
    message(
        "msg_aaaaaaaaaa03",
        "chat_e2e00003",
        "user",
        "已刪除對話的內容 e2etokenalpha",
        "2026-05-02T09:00:30+08:00",
    )


# ---------------------------------------------------------------------------
# reviews fixtures (tier6: _index.json + <review_id>/ files)
# ---------------------------------------------------------------------------


def seed_reviews(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)

    # Full monthly review: all 6 standard files -> partial=false.
    monthly = root / "2026-05-e2e-monthly"
    monthly.mkdir(parents=True, exist_ok=True)
    (monthly / "data.json").write_text("{}\n", encoding="utf-8")
    (monthly / "attribution.json").write_text("{}\n", encoding="utf-8")
    (monthly / "metrics.json").write_text(
        json.dumps(
            {
                "overall": {
                    "win_rate": 0.583,
                    "profit_factor": 1.42,
                    "expectancy_pct": 0.012,
                    "max_drawdown_pct": -0.08,
                    "max_consecutive_loss": 2,
                    "avg_hold_days": 6.5,
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (monthly / "critique.md").write_text("# e2e critique\n", encoding="utf-8")
    (monthly / "report.md").write_text(
        "# e2e 五月復盤報告\n\n勝率 58.3%，PF 1.42。\n", encoding="utf-8"
    )
    # Row format must satisfy routes/reviews._PROPOSAL_LINK_RE + >=4 cells.
    (monthly / "proposals_created.md").write_text(
        "| Proposal | Status | Priority | Target |\n"
        "|---|---|---|---|\n"
        "| [e2e-pr05m](../../proposals/2026-01-06-e2e-pr05m.md) "
        "| merged | medium | cheatsheet §6.6 |\n",
        encoding="utf-8",
    )
    upsert_index_entry(
        root,
        IndexEntry(
            review_id="2026-05-e2e-monthly",
            kind="monthly",
            period=Period.model_validate(
                {"from": "2026-05-01", "to": "2026-05-31"}
            ),
            trade_count=12,
            win_rate=0.583,
            pf=1.42,
            proposals_created=1,
            completed_at="2026-05-31T18:00:00+08:00",
        ),
    )

    # Partial quarterly review: only report.md -> partial banner + 缺漏.
    quarterly = root / "2026-04-e2e-quarterly"
    quarterly.mkdir(parents=True, exist_ok=True)
    (quarterly / "report.md").write_text(
        "# e2e 季度復盤（部分產出）\n", encoding="utf-8"
    )
    upsert_index_entry(
        root,
        IndexEntry(
            review_id="2026-04-e2e-quarterly",
            kind="quarterly",
            period=Period.model_validate(
                {"from": "2026-02-01", "to": "2026-04-30"}
            ),
            trade_count=5,
            win_rate=0.4,
            pf=0.85,
            proposals_created=0,
            completed_at="2026-04-30T18:00:00+08:00",
        ),
    )


# ---------------------------------------------------------------------------
# market symbol fixtures (tier8: /market/3017, now-relative)
# ---------------------------------------------------------------------------


def seed_market_symbol(conn: sqlite3.Connection, now: datetime) -> None:
    """Symbol 3017, untouched by every other fixture. Bars must end near
    `now` because routes/market._fetch_bars windows back from today —
    the fixed-2025 bars used by WFA/backtest would 404 here."""

    # 70 weekdays ending at the last weekday <= today.
    end = now.date()
    while end.weekday() >= 5:
        end -= timedelta(days=1)
    days: list[date] = []
    cur = end
    while len(days) < 70:
        if cur.weekday() < 5:
            days.append(cur)
        cur -= timedelta(days=1)
    days.reverse()

    fetched = now.isoformat()
    rows = []
    for i, d in enumerate(days):
        price = 100.0 + i * 0.5
        rows.append(
            BarRow(
                ts=d.isoformat(),
                o=price,
                h=price,
                l=price,
                c=price,
                v=2_000_000,
                amount=int(price * 2_000_000),
            )
        )
    insert_bars(conn, "3017", rows, "e2e", fetched)

    # RS rating: latest row wins (no date window in routes/market._fetch_rs).
    conn.execute(
        "INSERT OR REPLACE INTO rs_rating_cache "
        "(asof_date, symbol, rs_rating, universe_size, computed_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (days[-1].isoformat(), "3017", 87, 200, fetched),
    )

    # Institutional: last 5 bar dates; shares -> lots /1000 in the route.
    # Per-day total = 3000 - 1000 + 500 = +2500 lots; KPI sums 5 days = +12500.
    insert_three_major_rows(
        conn,
        [
            {
                "symbol": "3017",
                "date": d.isoformat(),
                "foreign_net": 3_000_000,
                "invest_trust_net": -1_000_000,
                "prop_dealer_net": 500_000,
            }
            for d in days[-5:]
        ],
        "e2e",
        fetched,
    )

    # Pattern row (kind=reject is safe: AU/PP/Dashboard assert specific
    # decision_ids only). No later 3017 entry exists -> outcome 未進場.
    _insert_journal(
        conn,
        "e2e-mk-pattern",
        "reject",
        "3017",
        (now - timedelta(days=3)).isoformat(),
        {"pattern": "VCP breakout", "score": 0.86, "reason": "e2e pattern fixture"},
    )


# ---------------------------------------------------------------------------
# proposals fixtures (Tier 1 state machine)
# ---------------------------------------------------------------------------


def _draft(topic: str, created: datetime) -> ProposalDraft:
    return ProposalDraft(
        topic=topic,
        target_section="cheatsheet §6.6",
        # NOT "mark": tier1 asserts changelog "by mark" lines added via UI,
        # which must not collide with the created-by line.
        created_by="seeder",
        created_at=created,
        review_id=None,
        priority="medium",
        description="e2e fixture 改動描述。",
        motivation="e2e fixture 動機 — metrics.json#/sharpe baseline.",
        diff_draft="```diff\n+ e2e\n```",
        expected_impact="影響。",
        risk_assessment="風險。",
        validation_plan="WFA 5+1。",
        expected_improvement="0.55 → 0.60。",
    )


def seed_proposals(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)

    def make(topic: str, day: int) -> Path:
        return write_proposal(
            _draft(topic, datetime(2026, 1, day, 10, 0, tzinfo=_TPE)), root
        )

    # pending: e2e-pr01 (UI pending→validating), e2e-pr06 (illegal-transition API)
    make("e2e-pr01", 1)
    make("e2e-pr06", 8)

    # validating: pr02 (validate pass + approve prefill), pr02f (validate fail),
    # pr04 (reject UI)
    for topic, day in (("e2e-pr02", 2), ("e2e-pr02f", 3), ("e2e-pr04", 5)):
        transition_proposal(make(topic, day), "validating", actor="e2e-seed")

    # approved: pr03 (merge UI)
    p = transition_proposal(make("e2e-pr03", 4), "validating", actor="e2e-seed")
    transition_proposal(
        p,
        "approved",
        actor="e2e-seed",
        validation_report_path=Path("2026-01-04-e2e-pr03.validation.json"),
    )

    # terminal: pr05m (merged), pr05r (rejected)
    p = transition_proposal(make("e2e-pr05m", 6), "validating", actor="e2e-seed")
    p = transition_proposal(
        p,
        "approved",
        actor="e2e-seed",
        validation_report_path=Path("2026-01-06-e2e-pr05m.validation.json"),
    )
    transition_proposal(p, "merged", actor="e2e-seed", merged_to_version="v9.9")

    p = transition_proposal(make("e2e-pr05r", 7), "validating", actor="e2e-seed")
    transition_proposal(p, "rejected", actor="e2e-seed", reason="e2e 終態 fixture")


def main() -> int:
    db_path = os.environ.get("OHMYSTOCK_DB_PATH")
    if not db_path:
        print("OHMYSTOCK_DB_PATH not set; refusing to seed", file=sys.stderr)
        return 1
    proposals_dir = os.environ.get("PROPOSALS_DIR")
    if not proposals_dir:
        print("PROPOSALS_DIR not set; refusing to seed", file=sys.stderr)
        return 1
    reviews_dir = os.environ.get("REVIEWS_DIR")
    if not reviews_dir:
        print("REVIEWS_DIR not set; refusing to seed", file=sys.stderr)
        return 1

    resolved = Path(db_path).expanduser()
    resolved.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(_TPE)

    conn = sqlite3.connect(str(resolved))
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        for init in _INITS:
            init(conn)
        seed_journal(conn, now)
        seed_memory(conn, now)
        seed_bars(conn)
        seed_chat(conn)
        seed_market_symbol(conn, now)
        conn.commit()
    finally:
        conn.close()

    seed_proposals(Path(proposals_dir).expanduser())
    seed_reviews(Path(reviews_dir).expanduser())

    print(
        f"seeded schema + fixtures into {resolved}, {proposals_dir} "
        f"and {reviews_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
