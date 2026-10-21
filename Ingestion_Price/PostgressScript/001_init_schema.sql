-- NSE Bhavcopy ingestion schema
-- Run on a PostgreSQL + TimescaleDB-enabled instance.
--
-- Bootstrap requirements:
-- 1. Load DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, DB_ADMIN_DATABASE=postgres,
--    AUTO_CREATE_DATABASE=true, and AUTO_ENABLE_EXTENSIONS=true.
-- 2. Connect to the administrative database and validate whether the target database exists.
-- 3. Create the target database if it does not exist, then reconnect to it.
-- 4. Enable required extensions idempotently.
-- 5. Run schema initialization in load order.
--
-- The database creation block is intended for execution through psql.

-- Create the target database if it does not already exist.
SELECT 'CREATE DATABASE "StockAnalysis_Bhavcopy"'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_database WHERE datname = 'StockAnalysis_Bhavcopy'
)
\gexec

\connect "StockAnalysis_Bhavcopy"

-- Enable TimescaleDB support in the target database.
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Schema initialization order:
-- 1. company_master
-- 2. equity_bhavcopy
-- 3. fo_bhavcopy

-- Company master metadata, keyed by symbol.
CREATE TABLE IF NOT EXISTS company_master (
    symbol TEXT PRIMARY KEY,
    company_name TEXT,
    date_of_listing TIMESTAMPTZ,
    SERIES TEXT,
    isin_number TEXT,
    face_value NUMERIC(18, 6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION set_company_master_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_company_master_updated_at ON company_master;

CREATE TRIGGER trg_company_master_updated_at
BEFORE UPDATE ON company_master
FOR EACH ROW
EXECUTE FUNCTION set_company_master_updated_at();

-- Canonical equity bhavcopy table.
-- The historical time-series data is stored as a hypertable keyed on DATE1.
CREATE TABLE IF NOT EXISTS equity_bhavcopy (
    date1 TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    series TEXT NOT NULL,
    prev_close NUMERIC(18, 6),
    open_price NUMERIC(18, 6),
    high_price NUMERIC(18, 6),
    low_price NUMERIC(18, 6),
    last_price NUMERIC(18, 6),
    close_price NUMERIC(18, 6),
    avg_price NUMERIC(18, 6),
    ttl_trd_qty BIGINT,
    turnover_lacs NUMERIC(18, 6),
    no_of_trades BIGINT,
    deliv_qty BIGINT,
    deliv_per NUMERIC(10, 6),
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (date1, symbol, series)
);

SELECT create_hypertable(
    'equity_bhavcopy',
    'date1',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '30 days'
);

-- F&O bhavcopy table. Append-only with duplicate protection on the composite key.
CREATE TABLE IF NOT EXISTS fo_bhavcopy (
    date1 TIMESTAMPTZ NOT NULL,
    segment TEXT,
    symbol TEXT NOT NULL,
    expiry_date DATE NOT NULL,
    instrument_number TEXT NOT NULL,
    open_price NUMERIC(18, 6),
    high_price NUMERIC(18, 6),
    low_price NUMERIC(18, 6),
    close_price NUMERIC(18, 6),
    last_price NUMERIC(18, 6),
    prev_close NUMERIC(18, 6),
    underlying_price NUMERIC(18, 6),
    settlement_price NUMERIC(18, 6),
    open_interest NUMERIC(18, 6),
    change_in_open_interest NUMERIC(18, 6),
    ttl_trd_qty BIGINT,
    turnover_lacs NUMERIC(18, 6),
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (date1, symbol, expiry_date, instrument_number)
);

-- Performance indexes.
CREATE INDEX IF NOT EXISTS idx_equity_bhavcopy_symbol_date
    ON equity_bhavcopy (symbol, date1 DESC);

CREATE INDEX IF NOT EXISTS idx_fo_bhavcopy_symbol_date
    ON fo_bhavcopy (symbol, date1 DESC);

-- Optional compression setup to stay compatible with TimescaleDB compression workflows.
ALTER TABLE equity_bhavcopy SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol',
    timescaledb.compress_orderby = 'date1 DESC'
);

-- Example ingestion patterns for retry-safe loads.
-- Company metadata upsert that preserves created_at.
-- INSERT INTO company_master (symbol, company_name, isin_number)
-- VALUES ('RELIANCE', 'Reliance Industries Ltd', 'INE002A01018')
-- ON CONFLICT (symbol) DO UPDATE
-- SET company_name = EXCLUDED.company_name,
--     isin_number = EXCLUDED.isin_number,
--     updated_at = now();

-- Historical append-only loads should ignore duplicates.
-- INSERT INTO equity_bhavcopy (
--     date1, symbol, series, prev_close, open_price, high_price, low_price, last_price, close_price, avg_price,
--     ttl_trd_qty, turnover_lacs, no_of_trades, deliv_qty, deliv_per
-- )
-- VALUES (
--     '2026-05-29', 'RELIANCE', 'EQ', 2500.00, 2510.00, 2530.00, 2495.00, 2525.00, 2525.00, 2525.00,
--     100000, 100.00, 25000, 75000, 75.00
-- )
-- ON CONFLICT (date1, symbol, series) DO NOTHING;

-- INSERT INTO fo_bhavcopy (
--     date1, segment, symbol, expiry_date, instrument_number, open_price, high_price, low_price, close_price,
--     last_price, prev_close, underlying_price, settlement_price, open_interest, change_in_open_interest,
--     ttl_trd_qty, turnover_lacs
-- )
-- VALUES (
--     '2026-05-29', 'F&O', 'RELIANCE', '2026-06-25', '123456', 2500.00, 2520.00, 2490.00, 2510.00,
--     2510.00, 2500.00, 2505.00, 2505.00, 150000, 2000, 2500, 12.50
-- )
-- ON CONFLICT (date1, symbol, expiry_date, instrument_number) DO NOTHING;
