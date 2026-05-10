"""Coverage for review.index.

Spec: openspec/changes/phase5-review-mvp/specs/post-trade-review-pipeline/spec.md
Requirement: reviews/_index.json 以 atomic rename 維護
"""

from __future__ import annotations

import json
from datetime import date

from ohmystock.review.index import upsert_index_entry
from ohmystock.review.models import IndexEntry, Period


def _entry(
    review_id: str = "manual-2026-04-01-to-2026-04-30",
    *,
    win_rate: float = 0.5652,
    proposals_created: int = 3,
) -> IndexEntry:
    return IndexEntry(
        review_id=review_id,
        kind="manual",
        period=Period.model_validate(
            {"from": date(2026, 4, 1), "to": date(2026, 4, 30)}
        ),
        trade_count=23,
        win_rate=win_rate,
        pf=1.84,
        proposals_created=proposals_created,
        completed_at="2026-04-30T19:42:00+08:00",
    )


def test_first_write_creates_index(tmp_path) -> None:
    upsert_index_entry(tmp_path, _entry())
    target = tmp_path / "_index.json"
    assert target.exists()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "v3.0"
    assert "last_updated" in payload
    assert len(payload["reviews"]) == 1
    assert payload["reviews"][0]["review_id"] == "manual-2026-04-01-to-2026-04-30"


def test_same_review_id_updates_in_place(tmp_path) -> None:
    upsert_index_entry(tmp_path, _entry(win_rate=0.5))
    upsert_index_entry(tmp_path, _entry(win_rate=0.6, proposals_created=5))
    payload = json.loads((tmp_path / "_index.json").read_text(encoding="utf-8"))
    assert len(payload["reviews"]) == 1
    assert payload["reviews"][0]["win_rate"] == 0.6
    assert payload["reviews"][0]["proposals_created"] == 5


def test_different_review_id_appends(tmp_path) -> None:
    upsert_index_entry(tmp_path, _entry(review_id="manual-2026-04-01-to-2026-04-30"))
    upsert_index_entry(tmp_path, _entry(review_id="manual-2026-05-01-to-2026-05-31"))
    payload = json.loads((tmp_path / "_index.json").read_text(encoding="utf-8"))
    ids = {row["review_id"] for row in payload["reviews"]}
    assert ids == {
        "manual-2026-04-01-to-2026-04-30",
        "manual-2026-05-01-to-2026-05-31",
    }


def test_orphan_temp_file_does_not_break_parse(tmp_path) -> None:
    upsert_index_entry(tmp_path, _entry())
    (tmp_path / ".index.crashed.tmp").write_text("garbage", encoding="utf-8")
    payload = json.loads((tmp_path / "_index.json").read_text(encoding="utf-8"))
    assert len(payload["reviews"]) == 1
    upsert_index_entry(tmp_path, _entry(win_rate=0.7))
    payload = json.loads((tmp_path / "_index.json").read_text(encoding="utf-8"))
    assert payload["reviews"][0]["win_rate"] == 0.7


def test_period_uses_from_alias(tmp_path) -> None:
    upsert_index_entry(tmp_path, _entry())
    payload = json.loads((tmp_path / "_index.json").read_text(encoding="utf-8"))
    period = payload["reviews"][0]["period"]
    assert period == {"from": "2026-04-01", "to": "2026-04-30"}
