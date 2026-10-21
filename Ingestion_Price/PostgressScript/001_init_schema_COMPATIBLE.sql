-- NSE Bhavcopy ingestion schema - CORRECTED FOR PYTHON COMPATIBILITY
-- Run on a PostgreSQL + TimescaleDB-enabled instance.
--
-- CHANGES FROM ORIGINAL:
-- 1. All column names converted to UPPERCASE to match Python DataFrame columns
-- 2. Company master table now includes SERIES column
-- 3. Company master columns renamed to match NSE source data format
-- 4. Index names updated to match new column naming
--
-- Bootstrap requirements:
-- 1. Load DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, DB_ADMIN_DATABASE=postgres,
--    AUTO_CREATE_DATABASE=true, and AUTO_ENABLE_EXTENSIONS=true.
-- 2. Connect to the administrative database and validate whether the target database exists.
-- 3. Create the target database if it does not exist, then reconnect to it.
-- 4. Enable required extensions idempotently.
-- 5. Run schema initialization in load order.

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

-- ============================================================================
-- Company Master Table - CORRECTED VERSION
-- ============================================================================
-- CHANGES:
-- - Added SERIES column (missing in original)
-- - Renamed columns to match NSE source data format with spaces:
--   company_name → "NAME OF COMPANY"
--   isin_number → "ISIN NUMBER"
-- - All column names properly quoted for case sensitivity
-- ============================================================================
CREATE TABLE IF NOT EXISTS company_master (
    "SYMBOL" TEXT PRIMARY KEY,
    "NAME OF COMPANY" TEXT,
    "SERIES" TEXT,
    "DATE OF LISTING" TIMESTAMPTZ ,
    "ISIN NUMBER" TEXT,
    "FACE VALUE" NUMERIC(18, 6),
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

-- ============================================================================
-- Equity Bhavcopy Table - CORRECTED VERSION
-- ============================================================================
-- CHANGES:
-- - All column names converted to UPPERCASE with quotes for case sensitivity
-- - Updated primary key constraint to use quoted UPPERCASE names
-- The historical time-series data is stored as a hypertable keyed on DATE1.
-- ============================================================================
CREATE TABLE IF NOT EXISTS equity_bhavcopy (
    "DATE1" TIMESTAMPTZ NOT NULL,
    "SYMBOL" TEXT NOT NULL,
    "SERIES" TEXT NOT NULL,
    "PREV_CLOSE" NUMERIC(18, 6),
    "OPEN_PRICE" NUMERIC(18, 6),
    "HIGH_PRICE" NUMERIC(18, 6),
    "LOW_PRICE" NUMERIC(18, 6),
    "LAST_PRICE" NUMERIC(18, 6),
    "CLOSE_PRICE" NUMERIC(18, 6),
    "AVG_PRICE" NUMERIC(18, 6),
    "TTL_TRD_QNTY" BIGINT,
    "TURNOVER_LACS" NUMERIC(18, 6),
    "NO_OF_TRADES" BIGINT,
    "DELIV_QTY" BIGINT,
    "DELIV_PER" NUMERIC(10, 6),
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY ("DATE1", "SYMBOL", "SERIES")
);

SELECT create_hypertable(
    'equity_bhavcopy',
    'DATE1',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '30 days'
);

-- ============================================================================
-- F&O Bhavcopy Table - CORRECTED VERSION
-- ============================================================================
-- CHANGES:
-- - All column names converted to UPPERCASE with quotes for case sensitivity
-- - Updated primary key constraint to use quoted UPPERCASE names
-- Append-only with duplicate protection on the composite key.
-- ============================================================================
CREATE TABLE IF NOT EXISTS fo_bhavcopy (
    "DATE1" TIMESTAMPTZ NOT NULL,
    "SEGMENT" TEXT,
    "SYMBOL" TEXT NOT NULL,
    "EXPIRY_DATE" DATE NOT NULL,
    "INSTRUMENT_NUMBER" TEXT NOT NULL,
    "OPEN_PRICE" NUMERIC(18, 6),
    "HIGH_PRICE" NUMERIC(18, 6),
    "LOW_PRICE" NUMERIC(18, 6),
    "CLOSE_PRICE" NUMERIC(18, 6),
    "LAST_PRICE" NUMERIC(18, 6),
    "PREV_CLOSE" NUMERIC(18, 6),
    "UNDERLYING_PRICE" NUMERIC(18, 6),
    "SETTLEMENT_PRICE" NUMERIC(18, 6),
    "OPEN_INTEREST" NUMERIC(18, 6),
    "CHANGE_IN_OPEN_INTEREST" NUMERIC(18, 6),
    "TTL_TRD_QNTY" BIGINT,
    "TURNOVER_LACS" NUMERIC(18, 6),
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY ("DATE1", "SYMBOL", "EXPIRY_DATE", "INSTRUMENT_NUMBER")
);

-- ============================================================================
-- Performance Indexes - UPDATED FOR UPPERCASE COLUMNS
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_equity_bhavcopy_symbol_date
    ON equity_bhavcopy ("SYMBOL", "DATE1" DESC);

CREATE INDEX IF NOT EXISTS idx_fo_bhavcopy_symbol_date
    ON fo_bhavcopy ("SYMBOL", "DATE1" DESC);

-- ============================================================================
-- TimescaleDB Compression Configuration
-- ============================================================================
-- Optional compression setup to stay compatible with TimescaleDB compression workflows.
ALTER TABLE equity_bhavcopy SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'SYMBOL',
    timescaledb.compress_orderby = 'DATE1 DESC'
);

-- ============================================================================
-- Example Ingestion Patterns for Retry-Safe Loads
-- ============================================================================
-- Company metadata upsert that preserves created_at.
-- INSERT INTO company_master ("SYMBOL", "NAME OF COMPANY", "SERIES", "ISIN NUMBER")
-- VALUES ('RELIANCE', 'Reliance Industries Ltd', 'EQ', 'INE002A01018')
-- ON CONFLICT ("SYMBOL") DO UPDATE
-- SET "NAME OF COMPANY" = EXCLUDED."NAME OF COMPANY",
--     "SERIES" = EXCLUDED."SERIES",
--     "ISIN NUMBER" = EXCLUDED."ISIN NUMBER",
--     updated_at = now();

-- Historical append-only loads should ignore duplicates.
-- INSERT INTO equity_bhavcopy (
--     "DATE1", "SYMBOL", "SERIES", "PREV_CLOSE", "OPEN_PRICE", "HIGH_PRICE", 
--     "LOW_PRICE", "LAST_PRICE", "CLOSE_PRICE", "AVG_PRICE",
--     "TTL_TRD_QNTY", "TURNOVER_LACS", "NO_OF_TRADES", "DELIV_QTY", "DELIV_PER"
-- )
-- VALUES (
--     '2026-05-29', 'RELIANCE', 'EQ', 2500.00, 2510.00, 2530.00, 2495.00, 
--     2525.00, 2525.00, 2525.00,
--     100000, 100.00, 25000, 75000, 75.00
-- )
-- ON CONFLICT ("DATE1", "SYMBOL", "SERIES") DO NOTHING;

-- INSERT INTO fo_bhavcopy (
--     "DATE1", "SEGMENT", "SYMBOL", "EXPIRY_DATE", "INSTRUMENT_NUMBER", 
--     "OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE",
--     "LAST_PRICE", "PREV_CLOSE", "UNDERLYING_PRICE", "SETTLEMENT_PRICE", 
--     "OPEN_INTEREST", "CHANGE_IN_OPEN_INTEREST",
--     "TTL_TRD_QNTY", "TURNOVER_LACS"
-- )
-- VALUES (
--     '2026-05-29', 'F&O', 'RELIANCE', '2026-06-25', '123456', 
--     2500.00, 2520.00, 2490.00, 2510.00,
--     2510.00, 2500.00, 2505.00, 2505.00, 150000, 2000, 2500, 12.50
-- )
-- ON CONFLICT ("DATE1", "SYMBOL", "EXPIRY_DATE", "INSTRUMENT_NUMBER") DO NOTHING;
