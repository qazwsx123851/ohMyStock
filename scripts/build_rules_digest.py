"""One-shot rules-digest regenerator (developer use only).

The swarm input assembler reads ``docs/_rules_digest.json`` for the LLM-visible
must-have / bonus rules. This file is the curated SSOT — when
``docs/workflow-cheatsheet.md`` §6.3 / §6.4 changes, edit this script's
embedded constants, run ``python scripts/build_rules_digest.py``, and review
the diff alongside the cheatsheet edit in the same PR.

Why a curated script and not a markdown parser:
- Cheatsheet section headings drift; regex parsing rots silently.
- A reviewable JSON diff catches semantic drift the way a code review should.
- Keeps parsing logic out of production code paths.
"""

from __future__ import annotations

import json
from pathlib import Path


# Cheatsheet §6.3 — Must-have (SEPA three pillars)
MUST_HAVE: list[str] = [
    "Trend Template 8/8 全過（依 §2 第一層）",
    "Stage 2 確認（依 §0.4 / §2 第三層）",
    "VCP/杯柄/平台 + Pivot Breakout 量能（≥ 1.4× 20DMA、Pivot~Pivot+5%）",
]

# Cheatsheet §6.4 — Bonus items (must remain length 8)
BONUS_ITEMS: list[str] = [
    "季 EPS YoY ≥ 25%（且本季 > 前季加速）",
    "月營收 YoY ≥ 20% 且創歷史新高",
    "RS Percentile ≥ 80",
    "距 52 週高 ≤ 15%",
    "VCP 收縮 ≥ 4 次（每次振幅 ≤ 前次 50%）",
    "機構持股遞增（外資/投信 30 日 + 主力分點 ≥ 25%）",
    "產業 RS 領先（產業 RS Percentile ≥ 80）",
    "新高 + 量爆（突破 52 週新高 + 量 ≥ 1.5× 20DMA）",
]


def main() -> None:
    if len(MUST_HAVE) != 3:
        raise SystemExit(f"MUST_HAVE must have 3 entries, got {len(MUST_HAVE)}")
    if len(BONUS_ITEMS) != 8:
        raise SystemExit(f"BONUS_ITEMS must have 8 entries, got {len(BONUS_ITEMS)}")

    out = {"must_have": MUST_HAVE, "bonus_items": BONUS_ITEMS}
    path = Path(__file__).resolve().parents[1] / "docs" / "_rules_digest.json"
    path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
