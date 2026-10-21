"""Explicit SMA-seeded EMA, Wilder RSI, and MACD conventions."""
import math


def ema(values, period):
    output = [None] * len(values)
    # Accept leading warm-up nulls (for the MACD signal).
    start = next((i for i, value in enumerate(values) if value is not None), len(values))
    if len(values) - start < period:
        return output
    seed_index = start + period - 1
    previous = sum(values[start:seed_index + 1]) / period
    output[seed_index] = previous
    alpha = 2 / (period + 1)
    for i in range(seed_index + 1, len(values)):
        previous += alpha * (values[i] - previous)
        output[i] = previous
    return output


def rsi(values, period):
    output = [None] * len(values)
    if len(values) <= period:
        return output
    deltas = [values[i] - values[i - 1] for i in range(1, len(values))]
    gain = sum(max(d, 0) for d in deltas[:period]) / period
    loss = sum(max(-d, 0) for d in deltas[:period]) / period

    def score():
        if loss == 0:
            return 100.0 if gain > 0 else 50.0
        return 100 - 100 / (1 + gain / loss)

    output[period] = score()
    for i in range(period + 1, len(values)):
        delta = deltas[i - 1]
        gain = (gain * (period - 1) + max(delta, 0)) / period
        loss = (loss * (period - 1) + max(-delta, 0)) / period
        output[i] = score()
    return output


def calculate(candles, requests):
    closes = [float(c["close"]) for c in candles]
    if any(not math.isfinite(v) for v in closes):
        raise ValueError("Non-finite close prices cannot be calculated")
    results = []
    for request in requests:
        name, period = request["name"], request["period"]
        rows = [{"Date": c["date"], "Close": c["close"]} for c in candles]
        required = period if name == "ema" else period + 1
        if name == "ema":
            values = ema(closes, period)
            for row, value in zip(rows, values):
                row[f"EMA{period}"] = value
        elif name == "rsi":
            values = rsi(closes, period)
            for row, value in zip(rows, values):
                row["RSI"] = value
        elif name == "macd":
            fast, slow = ema(closes, 12), ema(closes, 26)
            line = [a - b if a is not None and b is not None else None for a, b in zip(fast, slow)]
            signal = ema(line, 9)
            required = 34
            for row, value, sig in zip(rows, line, signal):
                row.update(MACD=value, Signal=sig,
                           Histogram=value - sig if value is not None and sig is not None else None)
        else:
            raise ValueError(f"Unsupported indicator: {name}")
        results.append({
            "indicator": name, "period": period, "data": rows,
            "status": "ok" if len(candles) >= required else "insufficient_history",
            "requiredCandles": required,
            "parameters": {"fast": 12, "slow": 26, "signal": 9} if name == "macd" else {"period": period},
        })
    return results
