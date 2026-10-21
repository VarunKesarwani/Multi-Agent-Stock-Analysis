import asyncio
import json
from unittest.mock import MagicMock, patch
import pytest
from marketdata_mcp.indicators import calculate, ema, rsi
from marketdata_mcp.server import IndicatorRequest, normalize_requests, mcp, calculate_indicators
from marketdata_mcp import repository


def candles(values):
    return [{"date": f"2026-01-{i+1:02}", "close": value} for i, value in enumerate(values)]


def test_ema_reference_seed_and_recurrence():
    assert ema([1, 2, 3, 4, 5], 3) == [None, None, 2, 3, 4]


def test_wilder_rsi_published_reference_sequence():
    prices = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
              45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00]
    result = rsi(prices, 14)
    assert result[:14] == [None] * 14
    assert result[14] == pytest.approx(70.464135, abs=0.00001)
    assert result[15] == pytest.approx(66.249619, abs=0.00001)


@pytest.mark.parametrize("prices,expected", [
    (list(range(20)), 100), (list(range(20, 0, -1)), 0), ([5] * 20, 50),
])
def test_rsi_edge_cases(prices, expected):
    assert rsi(prices, 14)[-1] == expected


def test_macd_linear_reference_and_signal_warmup():
    result = calculate(candles(list(range(1, 51))), [{"name": "macd", "period": 14}])[0]
    rows = result["data"]
    assert rows[24]["MACD"] is None
    assert rows[25]["MACD"] == pytest.approx(7)
    assert rows[32]["Signal"] is None
    assert rows[33]["Signal"] == pytest.approx(7)
    assert rows[-1]["Histogram"] == pytest.approx(0, abs=1e-10)


def test_macd_non_linear_reference():
    # Independently tabulated SMA-seeded EMA recurrence for a final price jump.
    result = calculate(candles([100] * 40 + [110]), [{"name": "macd", "period": 14}])[0]["data"][-1]
    assert result["MACD"] == pytest.approx(10 * (2/13 - 2/27))
    assert result["Signal"] == pytest.approx(result["MACD"] * 0.2)
    assert result["Histogram"] == pytest.approx(result["MACD"] * 0.8)


def test_requested_ema_periods_and_json_nulls():
    requests = [{"name": "ema", "period": p} for p in (5, 13, 21, 55)]
    results = calculate(candles(list(range(1, 61))), requests)
    assert [r["period"] for r in results] == [5, 13, 21, 55]
    assert results[-1]["data"][53]["EMA55"] is None
    assert results[-1]["data"][54]["EMA55"] == 28
    json.dumps(results, allow_nan=False)


def test_insufficient_history_and_nonfinite_prices():
    result = calculate(candles([1, 2]), [{"name": "rsi", "period": 14}])[0]
    assert result["status"] == "insufficient_history"
    assert all(row["RSI"] is None for row in result["data"])
    with pytest.raises(ValueError):
        calculate(candles([float("nan")]), [{"name": "ema", "period": 1}])


def test_unsupported_indicators_and_macd_period_rejected():
    with pytest.raises(ValueError):
        normalize_requests([IndicatorRequest(name="adx")])
    with pytest.raises(ValueError):
        normalize_requests([IndicatorRequest(name="macd", period=55)])


def test_mcp_discovery_preserves_names_and_object_schema():
    tools = asyncio.run(mcp.list_tools())
    assert {t.name for t in tools} == {
        "list_available_indicators", "get_latest_price",
        "get_historical_prices", "calculate_indicators",
    }
    tool = next(t for t in tools if t.name == "calculate_indicators")
    assert tool.input_schema["properties"]["indicators"]["type"] == "array"


def test_query_parameterization_readonly_and_ascending_dates():
    connection = MagicMock()
    cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
    from datetime import date
    cursor.fetchall.return_value = [
        {"DATE1": date(2026, 1, day), "SYMBOL": "TCS", "SERIES": "EQ",
         "OPEN_PRICE": 1, "HIGH_PRICE": 2, "LOW_PRICE": 1,
         "CLOSE_PRICE": 2, "TTL_TRD_QNTY": 10}
        for day in (2, 1)
    ]
    with patch.object(repository, "connect", return_value=connection):
        rows = repository.candles("TCS", 250)
    assert rows[0]["date"] == "2026-01-01"
    assert cursor.execute.call_args.args[1] == ("TCS", "EQ", 250)
    assert "%s" in cursor.execute.call_args.args[0]
    with patch.object(repository.psycopg, "connect") as connect:
        repository.connect()
    assert "default_transaction_read_only=on" in connect.call_args.kwargs["options"]


def test_duplicate_dates_fail():
    from datetime import date
    connection = MagicMock()
    cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = [{"DATE1": date(2026, 1, 1)}] * 2
    with patch.object(repository, "connect", return_value=connection), pytest.raises(ValueError):
        repository.candles("TCS", 2)


def test_unsupported_request_does_not_query_postgres():
    with patch.object(repository, "candles") as fetch, pytest.raises(ValueError):
        asyncio.run(calculate_indicators("TCS", [IndicatorRequest(name="adx")]))
    fetch.assert_not_called()
