"""Bounded parameterized read-only queries against the existing C# column contract."""
import os
import psycopg
from psycopg.rows import dict_row

COLUMNS = '"DATE1", "SYMBOL", "SERIES", "OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE", "TTL_TRD_QNTY"'
QUERY = f"""
SELECT {COLUMNS} FROM equity_bhavcopy
WHERE "SYMBOL" = %s AND "SERIES" = %s
  AND "OPEN_PRICE" IS NOT NULL AND "HIGH_PRICE" IS NOT NULL
  AND "LOW_PRICE" IS NOT NULL AND "CLOSE_PRICE" IS NOT NULL
ORDER BY "DATE1" DESC LIMIT %s
"""


def connect():
    # libpq PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD; no credentials logged.
    return psycopg.connect(
        connect_timeout=10, row_factory=dict_row,
        options="-c default_transaction_read_only=on -c statement_timeout=10000",
    )


def candles(symbol, limit):
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(QUERY, (symbol, os.getenv("MARKET_SERIES", "EQ"), limit))
            records = cursor.fetchall()
    dates = [str(row["DATE1"]) for row in records]
    if len(set(dates)) != len(dates):
        raise ValueError("Duplicate daily candles in the selected symbol/series")
    return [{
        "date": row["DATE1"].isoformat(),
        "open": float(row["OPEN_PRICE"]), "high": float(row["HIGH_PRICE"]),
        "low": float(row["LOW_PRICE"]), "close": float(row["CLOSE_PRICE"]),
        "volume": int(row["TTL_TRD_QNTY"]) if row["TTL_TRD_QNTY"] is not None else None,
        "companyId": row["SYMBOL"],
    } for row in reversed(records)]
