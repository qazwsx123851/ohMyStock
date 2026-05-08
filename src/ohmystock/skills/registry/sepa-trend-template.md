---
name: sepa-trend-template
description: Minervini Trend Template 8 條過濾器（must-have 進場前置）
category: signal
cited_specs:
  - sepa-trend-template
---
# Purpose
8 條 must-have 規則作為 Stage 2 進場的前置過濾：價 > 50/150/200 SMA、200 SMA 上行、50 SMA > 150 SMA > 200 SMA、距 52w 高 ≤ 25%、距 52w 低 ≥ 30%、RS ≥ 70 等。任一條不過 → 不予進場。

# Inputs
- `bars: list[BarRow]`（≥ 252 筆）
- `rs_value: int | None`

# Outputs
- `TemplateResult{passed: bool, failures: list[str]}`
- `failures` 為人類可讀字串如 `"price below 200SMA"`，方便 LLM 解釋

# See also
- `openspec/specs/sepa-trend-template/spec.md`
- 在 LLM Decider 進場時為 must-have 1/3
