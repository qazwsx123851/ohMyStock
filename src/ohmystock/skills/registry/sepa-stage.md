---
name: sepa-stage
description: Minervini SEPA 階段分類器（Stage 1-4）
category: signal
cited_specs:
  - sepa-stage-classification
---
# Purpose
依 Stan Weinstein / Mark Minervini SEPA 框架，將 symbol 在當下分類到 Stage 1（盤底）/ 2（突破上漲）/ 3（盤頭）/ 4（下跌），用於進場時機判斷。

# Inputs
- `bars: list[BarRow]`（建議 ≥ 252 筆）

# Outputs
- `StageResult{stage: int(1..4), since: str | None}`
- 資料不足拋例外，pipeline 應 fail-soft 為 `None`

# See also
- `openspec/specs/sepa-stage-classification/spec.md`
- 與 `sepa-trend-template` 配對：trend template 過濾後再分類
