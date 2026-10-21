import json
import sys
from pathlib import Path

import pandas as pd


def _find_repo_root(start_path: Path):
    current = start_path.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "BhavanCopyIngestion").exists():
            return candidate
    return None


repo_root = _find_repo_root(Path(__file__).resolve())
if repo_root is None:
    raise RuntimeError(f"BhavanCopyIngestion folder not found. Checked from: {Path(__file__).resolve()}")

bhavan_copy_root = repo_root / "BhavanCopyIngestion"
sys.path.insert(0, str(bhavan_copy_root))

import TechIndicator as tech_indicator


def _load_history(rows, symbol):
    if not rows:
        return pd.DataFrame(columns=["CompanyId", "Date", "Open", "High", "Low", "Close", "Volume"])

    df = pd.DataFrame(rows)
    rename_map = {
        "date": "Date",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
        "companyId": "CompanyId",
    }
    df.rename(columns={column: rename_map[column] for column in df.columns if column in rename_map}, inplace=True)

    if "CompanyId" not in df.columns:
        df["CompanyId"] = symbol
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

    for column in ["Open", "High", "Low", "Close", "Volume"]:
        if column not in df.columns:
            df[column] = None
        df[column] = pd.to_numeric(df[column], errors="coerce")

    return df.sort_values("Date").reset_index(drop=True)


def _records(df, columns=None):
    if isinstance(df, pd.Series):
        return df.reset_index(drop=True).to_frame("value").to_dict(orient="records")
    if columns and set(columns).issubset(df.columns):
        return df[columns].to_dict(orient="records")
    return df.to_dict(orient="records")


def calculate_indicator(indicator_name, rows, period=14, symbol="UNKNOWN"):
    df = _load_history(rows, symbol)
    if df.empty:
        return {"indicator": indicator_name, "symbol": symbol, "period": period, "data": []}

    name = indicator_name.lower()
    if name == "sma":
        result = tech_indicator.SMA(df.copy(), period)
        return {"indicator": "sma", "symbol": symbol, "period": period, "data": _records(result, ["Date", "Close", f"MA_{period}"])}
    if name == "ema":
        result = tech_indicator.EMA(df.copy(), period)
        return {"indicator": "ema", "symbol": symbol, "period": period, "data": _records(result, ["Date", "Close", f"EMA{period}"])}
    if name == "macd":
        result = tech_indicator.MACD(df.copy(), 12, 26, 9)
        return {"indicator": "macd", "symbol": symbol, "period": period, "data": _records(result, ["Date", "Close", "MACD", "Signal", "Histogram"])}
    if name == "rsi":
        result = tech_indicator.RSI(df.copy(), period)
        return {"indicator": "rsi", "symbol": symbol, "period": period, "data": _records(result, ["CompanyId", "Date", "Close", "Volume", "RS", "RSI"])}
    if name == "atr":
        result = tech_indicator.ATR(df.copy(), period)
        return {"indicator": "atr", "symbol": symbol, "period": period, "data": _records(result, ["Date", "Close", "ATR"])}
    if name == "bollinger":
        result = tech_indicator.BollBnd(df.copy(), period)
        return {"indicator": "bollinger", "symbol": symbol, "period": period, "data": _records(result, ["Date", "Close", "MA", "BB_up", "BB_dn"])}
    if name == "supertrend":
        result = tech_indicator.SuperTrend(df.copy(), period, 3)
        return {"indicator": "supertrend", "symbol": symbol, "period": period, "data": _records(result, ["Date", "Strend"])}
    if name == "adx":
        result = tech_indicator.ADX(df.copy(), period)
        return {"indicator": "adx", "symbol": symbol, "period": period, "data": _records(result)}
    if name == "aroon":
        result = tech_indicator.Aroon(df.copy(), period)
        return {"indicator": "aroon", "symbol": symbol, "period": period, "data": _records(result)}
    if name == "psar":
        result = tech_indicator.psar(df.copy(), symbol)
        return {"indicator": "psar", "symbol": symbol, "period": period, "data": _records(result)}
    if name == "heiken_ashi":
        result = tech_indicator.HeikenAshi(df.copy())
        return {"indicator": "heiken_ashi", "symbol": symbol, "period": period, "data": _records(result)}
    if name == "stoch_rsi":
        result = tech_indicator.StochRSI(df.copy(), period)
        return {"indicator": "stoch_rsi", "symbol": symbol, "period": period, "data": _records(result)}
    if name == "stochastic":
        result = tech_indicator.StochasticOscillator(df.copy(), period)
        return {"indicator": "stochastic", "symbol": symbol, "period": period, "data": _records(result)}
    if name == "awesome":
        result = tech_indicator.AwesomeOscillator(df.copy(), 5, 34)
        return {"indicator": "awesome", "symbol": symbol, "period": period, "data": _records(result)}
    if name == "williams_r":
        result = tech_indicator.WR(df.copy(), period)
        return {"indicator": "williams_r", "symbol": symbol, "period": period, "data": _records(result)}
    if name == "cci":
        result = tech_indicator.CCI(df.copy(), period)
        return {"indicator": "cci", "symbol": symbol, "period": period, "data": _records(result)}
    if name == "force":
        result = tech_indicator.FORCE(df.copy(), period)
        return {"indicator": "force", "symbol": symbol, "period": period, "data": _records(result)}
    if name == "mfi":
        result = tech_indicator.mfi(df.copy(), period)
        return {"indicator": "mfi", "symbol": symbol, "period": period, "data": _records(result)}
    if name == "elder_impulse":
        result = tech_indicator.ElderImpluseSystem(df.copy())
        return {"indicator": "elder_impulse", "symbol": symbol, "period": period, "data": [{"signal": result}]}
    if name == "volatility":
        result = tech_indicator.volatility(df.copy())
        return {"indicator": "volatility", "symbol": symbol, "period": period, "data": [{"value": result}]}
    if name == "renko":
        result = tech_indicator.RenkoChart(df.copy(), period)
        return {"indicator": "renko", "symbol": symbol, "period": period, "data": _records(result)}
    if name == "obv":
        result = tech_indicator.OBV(df.copy())
        return {"indicator": "obv", "symbol": symbol, "period": period, "data": _records(result, ["Date", "OBV"])}
    if name == "accdist":
        result = tech_indicator.ACCDIST(df.copy(), period)
        return {"indicator": "accdist", "symbol": symbol, "period": period, "data": _records(result)}
    if name == "vwap":
        result = tech_indicator.VWAP(df.copy(), symbol)
        return {"indicator": "vwap", "symbol": symbol, "period": period, "data": _records(result)}
    if name == "pivot":
        result = tech_indicator.levels(df.copy())
        return {"indicator": "pivot", "symbol": symbol, "period": period, "data": [result]}
    if name == "fibonacci":
        result = tech_indicator.Fibonaci(df.copy(), symbol)
        return {"indicator": "fibonacci", "symbol": symbol, "period": period, "data": _records(result)}
    if name == "support_resistance":
        result = tech_indicator.SupportAndResistance(df.copy())
        return {"indicator": "support_resistance", "symbol": symbol, "period": period, "data": _records(result)}
    if name == "doji":
        result = tech_indicator.doji(df.copy())
        return {"indicator": "doji", "symbol": symbol, "period": period, "data": _records(result, ["Date", "doji"])}
    if name == "shooting_star":
        result = tech_indicator.shooting_star(df.copy())
        return {"indicator": "shooting_star", "symbol": symbol, "period": period, "data": _records(result, ["Date", "sstar"])}
    if name == "maru_bozu":
        result = tech_indicator.maru_bozu(df.copy())
        return {"indicator": "maru_bozu", "symbol": symbol, "period": period, "data": _records(result, ["Date", "maru_bozu"])}
    if name == "cagr":
        result = tech_indicator.CAGR(df.copy())
        return {"indicator": "cagr", "symbol": symbol, "period": period, "data": [{"value": result}]}
    if name == "sharpe":
        result = tech_indicator.sharpe(df.copy(), 0.05)
        return {"indicator": "sharpe", "symbol": symbol, "period": period, "data": [{"value": result}]}
    if name == "max_drawdown":
        result = tech_indicator.max_dd(df.copy())
        return {"indicator": "max_drawdown", "symbol": symbol, "period": period, "data": [{"value": result}]}
    if name == "daily_pct_change":
        result = tech_indicator.Daily_PctChanges(df.copy())
        return {"indicator": "daily_pct_change", "symbol": symbol, "period": period, "data": _records(result)}
    if name == "slope":
        result = tech_indicator.slope(df["Close"], period)
        return {"indicator": "slope", "symbol": symbol, "period": period, "data": [{"value": float(result[-1]) if len(result) else None}]}

    return {"indicator": indicator_name, "symbol": symbol, "period": period, "data": []}


if __name__ == "__main__":
    payload_file = sys.argv[1]
    with open(payload_file, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    output = calculate_indicator(
        payload["indicator"],
        payload.get("rows", []),
        payload.get("period", 14),
        payload.get("symbol", "UNKNOWN"),
    )
    print(json.dumps(output, default=str, allow_nan=False))