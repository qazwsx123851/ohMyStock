"""Technical indicator math (pure functions, stateless).

Conventions:
- Output length always equals input length.
- Warmup positions where the indicator is undefined are ``None`` (never NaN).
- RSI and ATR use Wilder smoothing; SMA / EMA / MACD / Bollinger use textbook definitions.
- Empty inputs return empty outputs (or tuple of empties), never raise.

Spec: openspec/changes/technical-indicators-skill/specs/technical-indicators/spec.md
"""

from __future__ import annotations

from ohmystock.data.sources.base import BarRow


def _validate_period(period: int) -> None:
    if not isinstance(period, int) or period <= 0:
        raise ValueError(f"period must be a positive integer, got {period!r}")


def sma(closes: list[float], period: int) -> list[float | None]:
    _validate_period(period)
    n = len(closes)
    if n == 0:
        return []
    result: list[float | None] = [None] * n
    window_sum = 0.0
    for i in range(n):
        window_sum += closes[i]
        if i >= period:
            window_sum -= closes[i - period]
        if i >= period - 1:
            result[i] = window_sum / period
    return result


def ema(closes: list[float], period: int) -> list[float | None]:
    _validate_period(period)
    n = len(closes)
    if n == 0:
        return []
    result: list[float | None] = [None] * n
    if n < period:
        return result
    alpha = 2.0 / (period + 1)
    seed = sum(closes[:period]) / period
    result[period - 1] = seed
    prev = seed
    for i in range(period, n):
        prev = alpha * closes[i] + (1 - alpha) * prev
        result[i] = prev
    return result


def rsi(closes: list[float], period: int = 14) -> list[float | None]:
    _validate_period(period)
    n = len(closes)
    if n == 0:
        return []
    result: list[float | None] = [None] * n
    if n <= period:
        return result

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, n):
        diff = closes[i] - closes[i - 1]
        gains.append(diff if diff > 0 else 0.0)
        losses.append(-diff if diff < 0 else 0.0)

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    result[period] = _rsi_from_avgs(avg_gain, avg_loss)

    for i in range(period + 1, n):
        avg_gain = ((period - 1) * avg_gain + gains[i - 1]) / period
        avg_loss = ((period - 1) * avg_loss + losses[i - 1]) / period
        result[i] = _rsi_from_avgs(avg_gain, avg_loss)
    return result


def _rsi_from_avgs(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0 and avg_gain == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def macd(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    _validate_period(fast)
    _validate_period(slow)
    _validate_period(signal)
    n = len(closes)
    if n == 0:
        return ([], [], [])

    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line: list[float | None] = [None] * n
    first_macd_idx: int | None = None
    for i in range(n):
        f = ema_fast[i]
        s = ema_slow[i]
        if f is not None and s is not None:
            macd_line[i] = f - s
            if first_macd_idx is None:
                first_macd_idx = i

    signal_line: list[float | None] = [None] * n
    histogram: list[float | None] = [None] * n
    if first_macd_idx is not None:
        defined = [v for v in macd_line[first_macd_idx:] if v is not None]
        if len(defined) >= signal:
            sub_signal = ema(defined, signal)
            for j, v in enumerate(sub_signal):
                signal_line[first_macd_idx + j] = v
        for i in range(n):
            m = macd_line[i]
            s = signal_line[i]
            if m is not None and s is not None:
                histogram[i] = m - s

    return (macd_line, signal_line, histogram)


def atr(bars: list[BarRow], period: int = 14) -> list[float | None]:
    _validate_period(period)
    n = len(bars)
    if n == 0:
        return []
    result: list[float | None] = [None] * n
    if n <= period:
        return result

    trs: list[float] = [bars[0]["h"] - bars[0]["l"]]
    for t in range(1, n):
        h = bars[t]["h"]
        low = bars[t]["l"]
        prev_c = bars[t - 1]["c"]
        trs.append(max(h - low, abs(h - prev_c), abs(low - prev_c)))

    seed = sum(trs[: period + 1]) / (period + 1)
    result[period] = seed
    prev_atr = seed
    for t in range(period + 1, n):
        prev_atr = ((period - 1) * prev_atr + trs[t]) / period
        result[t] = prev_atr
    return result


def bollinger_bands(
    closes: list[float],
    period: int = 20,
    k: float = 2.0,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    _validate_period(period)
    n = len(closes)
    if n == 0:
        return ([], [], [])
    middle = sma(closes, period)
    upper: list[float | None] = [None] * n
    lower: list[float | None] = [None] * n
    for i in range(period - 1, n):
        window = closes[i - period + 1 : i + 1]
        mean = middle[i]
        assert mean is not None
        var = sum((x - mean) ** 2 for x in window) / period
        std = var**0.5
        upper[i] = mean + k * std
        lower[i] = mean - k * std
    return (upper, middle, lower)
