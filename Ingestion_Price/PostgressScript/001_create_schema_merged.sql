-- ============================================================================
-- 001_create_schema_merged.sql
-- Merged from: 001_init_schema.sql + 003_init_validation_COMPATIBLE.sql
--
-- Purpose: Fresh schema creation for NSE Bhavcopy + Screener market data.
-- Run on: PostgreSQL 15+ with TimescaleDB extension installed.
--
-- Bug fixes applied (see VALIDATION_REPORT.md):
--   BUG-1  : set_updated_at() function is defined before any trigger uses it.
--   BUG-3/4: Column names strictly standardized to uppercase quoted with underscores ("ISIN_NUMBER", "FACE_VALUE").
--   BUG-5  : Commented example INSERT uses consistent "ISIN_NUMBER" throughout.
--   DISC-1 : Standardized company_master primary key on "SYMBOL" (TEXT).
--   DISC-3 : Standardized company_market timestamp on updated_at.
--   DISC-10: Validation query now includes company_market.
--
-- Usage:
--   psql -U postgres -f PostgressScript/001_create_schema_merged.sql
-- ============================================================================

-- ============================================================================
-- 1. Database Creation
-- ============================================================================
SELECT 'CREATE DATABASE "StockAnalysis_Bhavcopy"'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_database WHERE datname = 'StockAnalysis_Bhavcopy'
)
\gexec

\connect "StockAnalysis_Bhavcopy"

-- Enable TimescaleDB support in the target database.
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- ============================================================================
-- 2. Generic updated_at trigger function
--    FIX: BUG-1 — set_updated_at() defined globally prior to trigger assignments.
-- ============================================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 3. Company Master Table
--    Primary key: "SYMBOL" (TEXT)
-- ============================================================================
CREATE TABLE IF NOT EXISTS company_master (
    "SYMBOL"            TEXT PRIMARY KEY,
    "NAME_OF_COMPANY"   TEXT,
    "SERIES"            TEXT,
    "DATE_OF_LISTING"   TIMESTAMPTZ,
    "ISIN_NUMBER"       TEXT,
    "FACE_VALUE"        NUMERIC(18, 6),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Trigger: auto-update updated_at on every row change.
DROP TRIGGER IF EXISTS trg_company_master_updated_at ON company_master;

CREATE TRIGGER trg_company_master_updated_at
BEFORE UPDATE ON company_master
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- 4. Company Market Table
--    Screener.in scraped market data. FK to company_master("SYMBOL").
--    FIX: DISC-1/DISC-3 — Foreign key directly references "SYMBOL", uses updated_at.
-- ============================================================================
CREATE TABLE IF NOT EXISTS company_market (
    "SYMBOL"                  TEXT PRIMARY KEY,
    "CURRENT_MARKET_PRICE"    NUMERIC(18, 2),
    "PE_RATIO"                NUMERIC(18, 2),
    "MARKET_CAP_CR"           NUMERIC(18, 2),
    "DIVIDEND_YIELD"          NUMERIC(10, 2),
    "QUARTERLY_PROFIT_CR"     NUMERIC(18, 2),
    "QUARTERLY_PROFIT_GROWTH" NUMERIC(18, 2),
    "QUARTERLY_SALES_CR"      NUMERIC(18, 2),
    "QUARTERLY_SALES_GROWTH"  NUMERIC(18, 2),
    "ROCE"                    NUMERIC(18, 2),
    screener_rank             INTEGER,
    scraped_at                TIMESTAMPTZ,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT fk_company_market_company
        FOREIGN KEY ("SYMBOL")
        REFERENCES company_master("SYMBOL")
        ON UPDATE CASCADE
        ON DELETE CASCADE
);

-- Trigger: auto-update updated_at on company_market changes.
DROP TRIGGER IF EXISTS trg_company_market_updated_at ON company_market;

CREATE TRIGGER trg_company_market_updated_at
BEFORE UPDATE ON company_market
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- 5. Equity Bhavcopy Table
--    TimescaleDB hypertable keyed on "DATE1".
-- ============================================================================
CREATE TABLE IF NOT EXISTS equity_bhavcopy (
    "DATE1"             TIMESTAMPTZ NOT NULL,
    "SYMBOL"            TEXT NOT NULL,
    "SERIES"            TEXT NOT NULL,
    "PREV_CLOSE"        NUMERIC(18, 6),
    "OPEN_PRICE"        NUMERIC(18, 6),
    "HIGH_PRICE"        NUMERIC(18, 6),
    "LOW_PRICE"         NUMERIC(18, 6),
    "LAST_PRICE"        NUMERIC(18, 6),
    "CLOSE_PRICE"       NUMERIC(18, 6),
    "AVG_PRICE"         NUMERIC(18, 6),
    "TTL_TRD_QNTY"      BIGINT,
    "TURNOVER_LACS"     NUMERIC(18, 6),
    "NO_OF_TRADES"      BIGINT,
    "DELIV_QTY"         BIGINT,
    "DELIV_PER"         NUMERIC(10, 6),
    inserted_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY ("DATE1", "SYMBOL", "SERIES")
);

SELECT create_hypertable(
    'equity_bhavcopy',
    'DATE1',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '30 days'
);

-- ============================================================================
-- 6. F&O Bhavcopy Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS fo_bhavcopy (
    "DATE1"                     TIMESTAMPTZ NOT NULL,
    "SEGMENT"                   TEXT,
    "SYMBOL"                    TEXT NOT NULL,
    "EXPIRY_DATE"               DATE NOT NULL,
    "INSTRUMENT_NUMBER"         TEXT NOT NULL,
    "OPEN_PRICE"                NUMERIC(18, 6),
    "HIGH_PRICE"                NUMERIC(18, 6),
    "LOW_PRICE"                 NUMERIC(18, 6),
    "CLOSE_PRICE"               NUMERIC(18, 6),
    "LAST_PRICE"                NUMERIC(18, 6),
    "PREV_CLOSE"                NUMERIC(18, 6),
    "UNDERLYING_PRICE"          NUMERIC(18, 6),
    "SETTLEMENT_PRICE"          NUMERIC(18, 6),
    "OPEN_INTEREST"             NUMERIC(18, 6),
    "CHANGE_IN_OPEN_INTEREST"   NUMERIC(18, 6),
    "TTL_TRD_QNTY"              BIGINT,
    "TURNOVER_LACS"             NUMERIC(18, 6),
    inserted_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY ("DATE1", "SYMBOL", "EXPIRY_DATE", "INSTRUMENT_NUMBER")
);

SELECT create_hypertable(
    'fo_bhavcopy',
    'DATE1',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '30 days'
);

-- ============================================================================
-- 7. Performance Indexes
-- ============================================================================

-- Company market indexes (FIX: DISC-4 — Standardized index naming)
CREATE INDEX IF NOT EXISTS idx_company_market_symbol
ON company_market("SYMBOL");

CREATE INDEX IF NOT EXISTS idx_company_market_market_cap
ON company_market("MARKET_CAP_CR" DESC);

CREATE INDEX IF NOT EXISTS idx_company_market_scraped_at
ON company_market(scraped_at DESC);

-- Company master lookup
CREATE INDEX IF NOT EXISTS idx_company_master_company_name
ON company_master(UPPER("NAME_OF_COMPANY"));

-- Equity bhavcopy lookup
CREATE INDEX IF NOT EXISTS idx_equity_bhavcopy_symbol_date
ON equity_bhavcopy ("SYMBOL", "DATE1" DESC);

-- F&O bhavcopy lookup
CREATE INDEX IF NOT EXISTS idx_fo_bhavcopy_symbol_date
ON fo_bhavcopy ("SYMBOL", "DATE1" DESC);

-- ============================================================================
-- 8. TimescaleDB Compression Configuration
-- ============================================================================
ALTER TABLE equity_bhavcopy
SET (
    timescaledb.compress = true,
    timescaledb.compress_segmentby = '"SYMBOL","SERIES"',
    timescaledb.compress_orderby = '"DATE1" DESC'
);

ALTER TABLE fo_bhavcopy
SET (
    timescaledb.compress = true,
    timescaledb.compress_segmentby = '"SYMBOL"',
    timescaledb.compress_orderby = '"DATE1" DESC'
);

SELECT add_compression_policy('equity_bhavcopy', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_compression_policy('fo_bhavcopy', INTERVAL '7 days', if_not_exists => TRUE);

-- ============================================================================
-- 9. Example Ingestion Patterns (Reference only)
-- ============================================================================

-- FIX: BUG-5 — SET clause correctly references "ISIN_NUMBER".
-- INSERT INTO company_master ("SYMBOL", "NAME_OF_COMPANY", "SERIES", "ISIN_NUMBER", "FACE_VALUE")
-- VALUES ('RELIANCE', 'Reliance Industries Ltd', 'EQ', 'INE002A01018', 10.000000)
-- ON CONFLICT ("SYMBOL") DO UPDATE
-- SET "NAME_OF_COMPANY" = EXCLUDED."NAME_OF_COMPANY",
--     "SERIES"          = EXCLUDED."SERIES",
--     "ISIN_NUMBER"     = EXCLUDED."ISIN_NUMBER",
--     "FACE_VALUE"      = EXCLUDED."FACE_VALUE",
--     updated_at        = now();

-- ============================================================================
-- 10. Validation Queries
--     FIX: DISC-10 — Validation query updated to verify company_market.
-- ============================================================================
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_name IN ('company_master', 'company_market', 'equity_bhavcopy', 'fo_bhavcopy')
ORDER BY table_name, ordinal_position;

SELECT table_name, COUNT(*) AS total_columns
FROM information_schema.columns
WHERE table_name IN ('company_master', 'company_market', 'equity_bhavcopy', 'fo_bhavcopy')
GROUP BY table_name
ORDER BY table_name;