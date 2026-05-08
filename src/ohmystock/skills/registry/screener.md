---
name: screener
description: 全 TWSE+OTC universe 多重 filter 篩選器
category: signal
cited_specs:
  - screener-tw-universe
---
# Purpose
單一進入點對全市場（~1700 檔）跑多 filter pipeline：SEPA template、RS ≥ N、三大法人連買、技術 pattern、處置股排除等。配合 `phase-2b-scoring-engine` 做加權打分輸出 watchlist。

# Inputs
- `universe: "tw50" | "all" | "custom"`
- `custom_symbols: list[str] | None`
- `filters: list[dict]`（每個 filter 為一條規則）
- `asof_date: str | None`

# Outputs
- envelope `{ok: bool, data?: {run_id, asof_date_used, candidates, elapsed_ms}, error?: {code, message}}`
- `candidates` 為通過所有 filter 的 symbol 列表

# See also
- `openspec/specs/screener-tw-universe/spec.md`
- `openspec/specs/phase-2b-scoring-engine/spec.md`
