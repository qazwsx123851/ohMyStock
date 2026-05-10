"""``reviews/_index.json`` upsert + atomic write.

Spec: openspec/changes/phase5-review-mvp/specs/post-trade-review-pipeline/spec.md
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ohmystock.review.models import IndexEntry


_TPE = timezone(timedelta(hours=8))
_SCHEMA_VERSION = "v3.0"
_INDEX_FILENAME = "_index.json"


def upsert_index_entry(out_dir: Path, entry: IndexEntry) -> None:
    """Insert/update ``entry`` in ``<out_dir>/_index.json`` atomically."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / _INDEX_FILENAME

    payload = _read_existing(target)

    rows: list[dict] = list(payload.get("reviews", []))
    encoded = entry.model_dump(mode="json", by_alias=True)
    replaced = False
    for idx, existing in enumerate(rows):
        if existing.get("review_id") == entry.review_id:
            rows[idx] = encoded
            replaced = True
            break
    if not replaced:
        rows.append(encoded)

    payload = {
        "schema_version": _SCHEMA_VERSION,
        "last_updated": datetime.now(_TPE).isoformat(timespec="seconds"),
        "reviews": rows,
    }

    tmp_fd, tmp_path = tempfile.mkstemp(prefix=".index.", suffix=".tmp", dir=out_dir)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp_path, target)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _read_existing(target: Path) -> dict:
    if not target.exists():
        return {"schema_version": _SCHEMA_VERSION, "reviews": []}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"schema_version": _SCHEMA_VERSION, "reviews": []}
