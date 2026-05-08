---
name: exit-engine
description: 出場規則引擎（停損 / T1 達標 / time stop，daily evaluation）
category: gate
cited_specs:
  - exit-engine
---
# Purpose
每日盤後評估所有 open positions，依停損 / T1 達標 / time-stop（持有 N 日無進展）三條規則決定是否平倉。v0 為 daily, full-position close；尚未支援分批 / trailing stop。

# Inputs
- 從 `journal_entries` 讀 open positions
- 當日 close price（從 `bars_daily`）

# Outputs
- list of exit actions：`{decision_id, symbol, exit_reason, exit_price, exit_pnl_pct}`
- 寫回 journal `kind="exit"` 列；觸發 broker 平倉（sim 模式）

# See also
- `openspec/specs/exit-engine/spec.md`
- 公式於 `docs/workflow-cheatsheet.md` §6.6（ATR 停損）
