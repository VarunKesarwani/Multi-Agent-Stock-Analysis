"""Explicit opt-in PostgreSQL validation; never writes data or prints credentials."""
import argparse
import json
from .repository import candles
from .server import symbol_value
from .indicators import calculate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--limit", type=int, default=250)
    args = parser.parse_args()
    if not 1 <= args.limit <= 5000:
        parser.error("--limit must be between 1 and 5000")
    try:
        rows = candles(symbol_value(args.symbol), args.limit)
        if not rows:
            raise ValueError("No complete candles for this symbol/series")
        requests = [{"name": "ema", "period": p} for p in (5, 13, 21, 55)]
        requests += [{"name": "rsi", "period": 14}, {"name": "macd", "period": 14}]
        results = calculate(rows, requests)
        json.dumps(results, allow_nan=False)
        print(json.dumps({"symbol": args.symbol, "candles": len(rows),
                          "firstDate": rows[0]["date"], "lastDate": rows[-1]["date"],
                          "indicators": [{"name": r["indicator"], "period": r["period"],
                                          "status": r["status"], "latest": r["data"][-1]}
                                         for r in results]}, allow_nan=False))
        if any(r["status"] != "ok" for r in results):
            raise ValueError("Insufficient history for requested indicators")
    except Exception as error:
        # Full driver errors can contain connection information; expose type and SQLSTATE only.
        print(json.dumps({"status": "failed", "errorType": type(error).__name__,
                          "sqlstate": getattr(error, "sqlstate", None)}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
