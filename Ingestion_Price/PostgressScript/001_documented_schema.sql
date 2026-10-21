-- For a NEW database only. Existing legacy schemas need an explicit migration.
BEGIN;
-- 1. Create Schema and Extensions
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- 2. Company Master Table
CREATE TABLE IF NOT EXISTS company_master (
    "SYMBOL"          TEXT PRIMARY KEY,
    "NAME_OF_COMPANY"    TEXT NOT NULL,
    "SERIES"          TEXT,
    "DATE_OF_LISTING" DATE,
    "PAID_UP_VALUE"   NUMERIC(18, 2),
    "MARKET_LOT"      INT,
    "ISIN_NUMBER"     TEXT,
    "FACE_VALUE"      NUMERIC(18, 2),
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Company Market Valuation Table (Screener.in Ingestion Target)
CREATE TABLE IF NOT EXISTS company_market (
    "SYMBOL"               TEXT PRIMARY KEY REFERENCES company_master("SYMBOL") ON DELETE CASCADE,
    "CURRENT_MARKET_PRICE" NUMERIC(18, 2),
    "PE_RATIO"             NUMERIC(18, 2),
    "MARKET_CAP_CR"        NUMERIC(18, 2),
    "DIVIDEND_YIELD"       NUMERIC(10, 2),
    "ROCE"                 NUMERIC(18, 2),
    created_at             TIMESTAMPTZ DEFAULT NOW(),
    updated_at             TIMESTAMPTZ DEFAULT NOW()
);

-- Trigger for company_market updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE OR REPLACE TRIGGER trg_company_market_updated_at
BEFORE UPDATE ON company_market
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- 4. Equity Bhavcopy Table
CREATE TABLE IF NOT EXISTS equity_bhavcopy (
    "SYMBOL"           TEXT NOT NULL,
    "SERIES"           TEXT NOT NULL,
    "TRADE_DATE"       DATE NOT NULL,
    "OPEN_PRICE"       NUMERIC(18, 2),
    "HIGH_PRICE"       NUMERIC(18, 2),
    "LOW_PRICE"        NUMERIC(18, 2),
    "CLOSE_PRICE"      NUMERIC(18, 2),
    "LAST_PRICE"       NUMERIC(18, 2),
    "PREV_CLOSE"       NUMERIC(18, 2),
    "TOTAL_TRADED_QTY" BIGINT,
    "TURNOVER_LACS"    NUMERIC(18, 2),
    "NO_OF_TRADES"     BIGINT,
    "DELIVERY_QTY"     BIGINT,
    "DELIVERY_PERCENT" NUMERIC(10, 2),
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY ("SYMBOL", "SERIES", "TRADE_DATE")
);

-- Convert equity_bhavcopy to Hypertable
SELECT create_hypertable('equity_bhavcopy', 'TRADE_DATE', if_not_exists => TRUE);

-- 5. F&O Bhavcopy Table
CREATE TABLE IF NOT EXISTS fo_bhavcopy (
    "INSTRUMENT"       TEXT NOT NULL,
    "SYMBOL"           TEXT NOT NULL,
    "EXPIRY_DATE"      DATE NOT NULL,
    "STRIKE_PRICE"     NUMERIC(18, 2) NOT NULL DEFAULT 0.00,
    "OPTION_TYPE"      TEXT NOT NULL DEFAULT 'XX',
    "TRADE_DATE"       DATE NOT NULL,
    "OPEN_PRICE"       NUMERIC(18, 2),
    "HIGH_PRICE"       NUMERIC(18, 2),
    "LOW_PRICE"        NUMERIC(18, 2),
    "CLOSE_PRICE"      NUMERIC(18, 2),
    "SETTLE_PRICE"     NUMERIC(18, 2),
    "CONTRACTS_TRADED" BIGINT,
    "VAL_IN_LAKHS"     NUMERIC(18, 2),
    "OPEN_INTEREST"    BIGINT,
    "CHANGE_IN_OI"     BIGINT,
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY ("INSTRUMENT", "SYMBOL", "EXPIRY_DATE", "STRIKE_PRICE", "OPTION_TYPE", "TRADE_DATE")
);

-- Convert fo_bhavcopy to Hypertable
SELECT create_hypertable('fo_bhavcopy', 'TRADE_DATE', if_not_exists => TRUE);

-- 6. Indexes for Performance
CREATE INDEX IF NOT EXISTS idx_company_market_mcap ON company_market ("MARKET_CAP_CR" DESC);
CREATE INDEX IF NOT EXISTS idx_equity_symbol_date ON equity_bhavcopy ("SYMBOL", "TRADE_DATE" DESC);
CREATE INDEX IF NOT EXISTS idx_fo_symbol_date ON fo_bhavcopy ("SYMBOL", "TRADE_DATE" DESC);

COMMIT;
