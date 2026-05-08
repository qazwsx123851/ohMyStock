---
name: rs-percentile
description: 252 日 RS rating（IBD-style 1-99 percentile，universe 全市場）
category: indicator
cited_specs:
  - rs-percentile
---
# Purpose
計算 IBD-style Relative Strength rating：以 252 個交易日表現對全 universe 排序，輸出 1-99 percentile。每日於 `rs_rating_cache` 增量重算；日盤後 backfill 由 `scripts/backfill_rs_rating.py` 處理。

# Inputs
- `symbol`（必填）
- `asof_date`（預設今日）

# Outputs
- `RsResult{value: int(1..99), asof: str, universe_size: int}`
- 缺資料 / 不足 ≥253 列回 `None`（fail-soft）

# See also
- `openspec/specs/rs-percentile/spec.md`
- 處置股移除規則於 `src/ohmystock/data/disposition.py`
