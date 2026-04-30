## 1. 套件骨架與 `__init__` re-exports

- [x] 1.1 建立 `src/ohmystock/indicators/__init__.py`，內容為 `from ohmystock.indicators.core import sma, ema, rsi, macd, atr, bollinger_bands` 與對應 `__all__`
- [x] 1.2 建立 `src/ohmystock/indicators/core.py`（先放 module docstring + `from __future__ import annotations` + 必要 import：`from typing import Sequence`、`from ohmystock.data.sources.base import BarRow`，視需要 `import numpy as np`）
- [x] 1.3 在 `core.py` 加共用 helper `_validate_period(period: int) -> None` raise `ValueError`，被全部 6 個 indicator 共用

## 2. SMA

- [x] 2.1 實作 `sma(closes: list[float], period: int) -> list[float | None]`：參數驗證 → 空輸入回 `[]` → 前 `period - 1` 個位置回 `None` → 其餘回 trailing window 算術平均
- [x] 2.2 在 `tests/test_indicators.py` 加 3 個測試：`sma([1.5, 2.5, 3.5], 1) == [1.5, 2.5, 3.5]`、`sma([1..6], 4)` 線性 ramp golden、`sma([], 5) == []`
- [x] 2.3 加 1 個測試：`sma(closes, 0)` raise `ValueError`、`sma(closes, -1)` raise `ValueError`

## 3. EMA

- [x] 3.1 實作 `ema(closes: list[float], period: int) -> list[float | None]`：α = 2/(period+1)；index `period - 1` 用前 `period` 筆 SMA 當 seed；之後 `ema_t = α*close_t + (1-α)*ema_{t-1}`
- [x] 3.2 加 1 個 golden test：`ema([2.0, 4.0, 6.0, 8.0, 10.0], 3) == [None, None, 4.0, 6.0, 8.0]`（α = 0.5）
- [x] 3.3 加 1 個 length-invariant 測試：`len(ema(closes, period)) == len(closes)` 對 period=1, 5, 50

## 4. RSI（Wilder）

- [x] 4.1 實作 `rsi(closes: list[float], period: int = 14) -> list[float | None]`：算逐筆 gain/loss → 前 `period` 筆 gain/loss 簡單平均做 seed → 之後用 Wilder smoothing → `rs = avg_gain/avg_loss`、`rsi = 100 - 100/(1+rs)`
- [x] 4.2 處理特例：`avg_loss == 0` → 回 `100.0`；`avg_gain == 0 and avg_loss == 0`（常數輸入）→ 回 `50.0`
- [x] 4.3 加 golden tests：常數輸入 `[10.0]*30, 14` → 全 50.0；嚴格遞增 `[1..30], 14` → 全 100.0
- [x] 4.4 加 1 個 warmup 測試：前 14 個位置（index 0..13）皆為 `None`

## 5. MACD

- [x] 5.1 實作 `macd(closes, fast=12, slow=26, signal=9) -> tuple[list, list, list]`：(a) 算 `ema(closes, fast)` / `ema(closes, slow)`；(b) `macd_line[i] = ema_fast[i] - ema_slow[i]`（兩端任一為 None → None）；(c) 把 macd_line 中 `defined` 部分丟給 `ema(..., signal)` 算 signal_line，再回填 None 對齊原長度；(d) `histogram[i] = macd_line[i] - signal_line[i]`（任一 None → None）
- [x] 5.2 加 length 測試：3 個輸出長度都等於 `len(closes)`
- [x] 5.3 加 alignment 測試：`macd([1..50])` 預期 `macd_line` 第一個非 None index = 25、`signal_line` 第一個非 None index = 33

## 6. ATR（Wilder）

- [x] 6.1 實作 `atr(bars: list[BarRow], period: int = 14) -> list[float | None]`：(a) 逐筆算 true-range：`tr_0 = h_0 - l_0`，`tr_t = max(h_t-l_t, |h_t - c_{t-1}|, |l_t - c_{t-1}|)`；(b) 採 Wilder 慣例：第一個 ATR 落在 index `period`（用 first `period+1` 個 TR 起跳），實作時參照 spec scenario 確認對齊
- [x] 6.2 之後 Wilder smoothing：`atr_t = ((period - 1) * atr_{t-1} + tr_t) / period`
- [x] 6.3 加 golden test：20 根 flat bars（h=110, l=90, c=100）→ 所有 defined 位置 = 20.0
- [x] 6.4 加 warmup 測試：bars=20、period=14 → index 0..13 為 None、index 14..19 為 20.0

## 7. Bollinger Bands

- [x] 7.1 實作 `bollinger_bands(closes, period=20, k=2.0) -> tuple[list, list, list]`：(a) `middle = sma(closes, period)`；(b) rolling population std（denominator = `period`，不是 `period - 1`）；(c) `upper[i] = middle[i] + k * std[i]`；(d) `lower[i] = middle[i] - k * std[i]`；warmup index 為 None
- [x] 7.2 加 golden test：常數輸入 `[5.0]*25, period=20, k=2.0` → 所有 defined 位置 `upper == middle == lower == 5.0`
- [x] 7.3 加 length 測試：3 個輸出長度都 = `len(closes)`

## 8. 跨函式共通行為

- [x] 8.1 加 1 個 import 測試：`from ohmystock.indicators import sma, ema, rsi, macd, atr, bollinger_bands` 全部成功；且 `from ohmystock.indicators.core import sma` 與 package-level import 是同一物件 (`sma is sma_from_core`)
- [x] 8.2 加 1 個 empty-input 測試：6 個 indicator 對空輸入分別回 `[]` / `([], [], [])`，皆不 raise

## 9. 反向 import 防護

- [x] 9.1 在 `tests/test_reverse_import_guard.py` 的 `GUARDED_MODULES` 加入 `"ohmystock.indicators.core"` → `Path("src/ohmystock/indicators/core.py")`，並在 subprocess script 加 `import ohmystock.indicators.core` — 確認不拉 `fastapi` / `uvicorn` / `starlette`

## 10. 全套驗收

- [x] 10.1 跑 `uv run pytest tests/test_indicators.py -v` 全綠
- [x] 10.2 跑 `uv run pytest -v` 全綠（既有 63 + 新增 ~15 個 ≈ 78 個全 pass）
- [x] 10.3 在 REPL 串接 `get_kline` + 任一 indicator 跑一次：`uv run python -c "from ohmystock.data.market_data import get_kline; from ohmystock.indicators import rsi; r = get_kline('2330', bars=30, end_date='2026-04-28'); print(rsi([b['c'] for b in r['data']['bars']], 14))"` → 末尾應有真實 RSI 值
- [x] 10.4 跑 `openspec validate technical-indicators-skill --strict` 通過
- [x] 10.5 commit 並 push（commit message 引用本 change name + 列關鍵子模組）
