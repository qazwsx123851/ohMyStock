"""Tests for ohmystock.swarm.load_rules_digest.

Spec: openspec/changes/phase-2b-swarm-input-assembler/specs/swarm-input-assembler/spec.md
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ohmystock.swarm import RulesDigest, RulesDigestError, load_rules_digest


_VALID = {
    "must_have": [
        "Trend Template 8/8 全過（依 §2 第一層）",
        "Stage 2 確認（依 §0.4 / §2 第三層）",
        "VCP/杯柄/平台 + Pivot Breakout 量能（≥ 1.4× 20DMA、Pivot~Pivot+5%）",
    ],
    "bonus_items": [
        "季 EPS YoY ≥ 25%（且本季 > 前季加速）",
        "月營收 YoY ≥ 20% 且創歷史新高",
        "RS Percentile ≥ 80",
        "距 52 週高 ≤ 15%",
        "VCP 收縮 ≥ 4 次（每次振幅 ≤ 前次 50%）",
        "機構持股遞增（外資/投信 30 日 + 主力分點 ≥ 25%）",
        "產業 RS 領先（產業 RS Percentile ≥ 80）",
        "新高 + 量爆（突破 52 週新高 + 量 ≥ 1.5× 20DMA）",
    ],
}


def _write(tmp_path: Path, data: object) -> Path:
    target = tmp_path / "digest.json"
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return target


def test_default_path_loads() -> None:
    digest = load_rules_digest()
    assert isinstance(digest, RulesDigest)
    assert len(digest.must_have) == 3
    assert len(digest.bonus_items) == 8


def test_explicit_path_valid_load(tmp_path: Path) -> None:
    target = _write(tmp_path, _VALID)
    digest = load_rules_digest(target)
    assert digest.must_have == _VALID["must_have"]
    assert digest.bonus_items == _VALID["bonus_items"]


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(RulesDigestError, match="not found"):
        load_rules_digest(tmp_path / "missing.json")


def test_malformed_json_raises(tmp_path: Path) -> None:
    target = tmp_path / "bad.json"
    target.write_text("{not json", encoding="utf-8")
    with pytest.raises(RulesDigestError, match="not valid JSON"):
        load_rules_digest(target)


def test_top_level_must_be_object(tmp_path: Path) -> None:
    target = _write(tmp_path, [1, 2, 3])
    with pytest.raises(RulesDigestError, match="must be a JSON object"):
        load_rules_digest(target)


def test_wrong_must_have_count_raises(tmp_path: Path) -> None:
    bad = dict(_VALID)
    bad["must_have"] = ["only", "two"]
    target = _write(tmp_path, bad)
    with pytest.raises(RulesDigestError, match="failed validation"):
        load_rules_digest(target)


def test_wrong_bonus_count_raises(tmp_path: Path) -> None:
    bad = dict(_VALID)
    bad["bonus_items"] = ["only-one"]
    target = _write(tmp_path, bad)
    with pytest.raises(RulesDigestError, match="failed validation"):
        load_rules_digest(target)
