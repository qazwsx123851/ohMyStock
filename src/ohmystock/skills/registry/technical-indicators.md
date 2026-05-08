---
name: technical-indicators
description: 技術指標庫（SMA / EMA / RSI / MACD / Bollinger / ATR / VWAP / KD）
category: indicator
cited_specs:
  - technical-indicators
---
# Purpose
純函數技術指標庫，輸入 `BarRow` 序列輸出對應指標序列。所有指標使用 zero-lookahead bias 計算（窗口右閉），可直接餵入 backtest 與 screener。

# Inputs
- `bars: list[BarRow]`（升序）
- 各指標自帶參數：例如 `sma(period=20)`、`atr(period=14)`

# Outputs
- 指標序列（與輸入長度相同；前 N-1 筆為 `NaN` / `None` 直到 warm-up）

# See also
- `openspec/specs/technical-indicators/spec.md`
- ATR 用於 sizing；公式於 `docs/workflow-cheatsheet.md` §6.6
