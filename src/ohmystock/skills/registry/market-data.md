---
name: market-data
description: 取得台股 daily bars 與 quote（FinMind / Shioaji / yfinance fallback）
category: data
cited_specs:
  - market-data-cache
  - external-connectors
---
# Purpose
封裝多家資料源（FinMind 贊助會員、Shioaji sim、twstock、yfinance）為單一 API，以 SQLite cache 為一級存取層；對 Agent 隱藏 connector 切換、quota、stale 判斷。

# Inputs
- `symbol` (str, 4-digit TWSE / OTC code)
- `period_from` / `period_to` (ISO date)
- 可選 `prefer_source` 提示

# Outputs
- `BarRow` 序列：`{ts, o, h, l, c, v}`，按日期升序
- 失敗回 envelope `{ok: false, error: {code, message}}`

# See also
- `openspec/specs/market-data-cache/spec.md`
- `openspec/specs/external-connectors/spec.md`
- `openspec/specs/live-providers/spec.md`
