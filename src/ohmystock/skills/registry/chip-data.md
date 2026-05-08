---
name: chip-data
description: 三大法人（外資 / 投信 / 自營商）每日買賣超與融資融券
category: data
cited_specs:
  - chip-data-skill
---
# Purpose
存取台股「籌碼面」資料：三大法人買賣超、融資融券餘額、借券、處置股清單。資料源 FinMind，cache 入 `chip_three_major_daily` 表。

# Inputs
- `symbol`（必填）
- `period_from` / `period_to`（ISO date）

# Outputs
- 三大法人列陣列：`{date, foreign_net, invest_trust_net, prop_dealer_net}`
- 數值單位「股」（lots = shares / 1000）

# See also
- `openspec/specs/chip-data-skill/spec.md`
- 衍生指標：連續買超、外資 / 投信合計
