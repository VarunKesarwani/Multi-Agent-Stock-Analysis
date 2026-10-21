-- ============================================================================
-- 002_migrate_schema_merged.sql
-- Merged from: 002_migrate_schema_to_compatible.sql + 003_init_validation_COMPATIBLE.sql
--
-- Purpose: In-place migration of an existing database from legacy lowercase
--          columns to quoted uppercase NSE-style column names.
--
-- Bug fixes applied (see VALIDATION_REPORT.md):
--   BUG-2  : equity_bhavcopy symbol correctly renamed to "SYMBOL".
--   DISC-1 : Aligned PK reference to company_master("SYMBOL").
--   DISC-5 : Compression settings aligned with fresh setup (two-column segmentby).
--   DISC-10: Validation query includes company_market.
--   DISC-11: set_updated_at() defined unconditionally.
--
-- Usage:
--   psql -U postgres -d StockAnalysis_Bhavcopy -f PostgressScript/002_migrate_schema_merged.sql
-- ============================================================================

BEGIN;

-- ============================================================================
-- 0. Generic updated_at trigger function
--    FIX: DISC-11 — Guarantees function exists before trigger definitions.
-- ============================================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 1. COMPANY MASTER — Rename legacy lowercase columns
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'company_master' AND column_name = 'symbol') THEN
        EXECUTE 'ALTER TABLE company_master RENAME COLUMN symbol TO "SYMBOL"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'company_master' AND column_name = 'company_name') THEN
        EXECUTE 'ALTER TABLE company_master RENAME COLUMN company_name TO "NAME_OF_COMPANY"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'company_master' AND column_name = 'series') THEN
        EXECUTE 'ALTER TABLE company_master RENAME COLUMN series TO "SERIES"';
    ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'company_master' AND column_name = 'SERIES') THEN
        EXECUTE 'ALTER TABLE company_master ADD COLUMN "SERIES" TEXT';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'company_master' AND column_name = 'date_of_listing') THEN
        EXECUTE 'ALTER TABLE company_master RENAME COLUMN date_of_listing TO "DATE_OF_LISTING"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'company_master' AND column_name = 'isin_number') THEN
        EXECUTE 'ALTER TABLE company_master RENAME COLUMN isin_number TO "ISIN_NUMBER"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'company_master' AND column_name = 'face_value') THEN
        EXECUTE 'ALTER TABLE company_master RENAME COLUMN face_value TO "FACE_VALUE"';
    END IF;
END $$;

-- ============================================================================
-- 2. EQUITY BHAVCOPY — Rename legacy lowercase columns
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'equity_bhavcopy' AND column_name = 'date1') THEN
        EXECUTE 'ALTER TABLE equity_bhavcopy RENAME COLUMN date1 TO "DATE1"';
    END IF;

    -- FIX: BUG-2 — Corrected rename target to "SYMBOL"
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'equity_bhavcopy' AND column_name = 'symbol') THEN
        EXECUTE 'ALTER TABLE equity_bhavcopy RENAME COLUMN symbol TO "SYMBOL"';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'equity_bhavcopy' AND column_name = 'series') THEN
        EXECUTE 'ALTER TABLE equity_bhavcopy RENAME COLUMN series TO "SERIES"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'equity_bhavcopy' AND column_name = 'prev_close') THEN
        EXECUTE 'ALTER TABLE equity_bhavcopy RENAME COLUMN prev_close TO "PREV_CLOSE"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'equity_bhavcopy' AND column_name = 'open_price') THEN
        EXECUTE 'ALTER TABLE equity_bhavcopy RENAME COLUMN open_price TO "OPEN_PRICE"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'equity_bhavcopy' AND column_name = 'high_price') THEN
        EXECUTE 'ALTER TABLE equity_bhavcopy RENAME COLUMN high_price TO "HIGH_PRICE"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'equity_bhavcopy' AND column_name = 'low_price') THEN
        EXECUTE 'ALTER TABLE equity_bhavcopy RENAME COLUMN low_price TO "LOW_PRICE"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'equity_bhavcopy' AND column_name = 'last_price') THEN
        EXECUTE 'ALTER TABLE equity_bhavcopy RENAME COLUMN last_price TO "LAST_PRICE"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'equity_bhavcopy' AND column_name = 'close_price') THEN
        EXECUTE 'ALTER TABLE equity_bhavcopy RENAME COLUMN close_price TO "CLOSE_PRICE"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'equity_bhavcopy' AND column_name = 'avg_price') THEN
        EXECUTE 'ALTER TABLE equity_bhavcopy RENAME COLUMN avg_price TO "AVG_PRICE"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'equity_bhavcopy' AND column_name = 'ttl_trd_qty') THEN
        EXECUTE 'ALTER TABLE equity_bhavcopy RENAME COLUMN ttl_trd_qty TO "TTL_TRD_QNTY"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'equity_bhavcopy' AND column_name = 'turnover_lacs') THEN
        EXECUTE 'ALTER TABLE equity_bhavcopy RENAME COLUMN turnover_lacs TO "TURNOVER_LACS"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'equity_bhavcopy' AND column_name = 'no_of_trades') THEN
        EXECUTE 'ALTER TABLE equity_bhavcopy RENAME COLUMN no_of_trades TO "NO_OF_TRADES"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'equity_bhavcopy' AND column_name = 'deliv_qty') THEN
        EXECUTE 'ALTER TABLE equity_bhavcopy RENAME COLUMN deliv_qty TO "DELIV_QTY"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'equity_bhavcopy' AND column_name = 'deliv_per') THEN
        EXECUTE 'ALTER TABLE equity_bhavcopy RENAME COLUMN deliv_per TO "DELIV_PER"';
    END IF;
END $$;

-- ============================================================================
-- 3. F&O BHAVCOPY — Rename legacy lowercase columns
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'fo_bhavcopy' AND column_name = 'date1') THEN
        EXECUTE 'ALTER TABLE fo_bhavcopy RENAME COLUMN date1 TO "DATE1"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'fo_bhavcopy' AND column_name = 'segment') THEN
        EXECUTE 'ALTER TABLE fo_bhavcopy RENAME COLUMN segment TO "SEGMENT"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'fo_bhavcopy' AND column_name = 'symbol') THEN
        EXECUTE 'ALTER TABLE fo_bhavcopy RENAME COLUMN symbol TO "SYMBOL"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'fo_bhavcopy' AND column_name = 'expiry_date') THEN
        EXECUTE 'ALTER TABLE fo_bhavcopy RENAME COLUMN expiry_date TO "EXPIRY_DATE"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'fo_bhavcopy' AND column_name = 'instrument_number') THEN
        EXECUTE 'ALTER TABLE fo_bhavcopy RENAME COLUMN instrument_number TO "INSTRUMENT_NUMBER"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'fo_bhavcopy' AND column_name = 'open_price') THEN
        EXECUTE 'ALTER TABLE fo_bhavcopy RENAME COLUMN open_price TO "OPEN_PRICE"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'fo_bhavcopy' AND column_name = 'high_price') THEN
        EXECUTE 'ALTER TABLE fo_bhavcopy RENAME COLUMN high_price TO "HIGH_PRICE"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'fo_bhavcopy' AND column_name = 'low_price') THEN
        EXECUTE 'ALTER TABLE fo_bhavcopy RENAME COLUMN low_price TO "LOW_PRICE"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'fo_bhavcopy' AND column_name = 'close_price') THEN
        EXECUTE 'ALTER TABLE fo_bhavcopy RENAME COLUMN close_price TO "CLOSE_PRICE"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'fo_bhavcopy' AND column_name = 'last_price') THEN
        EXECUTE 'ALTER TABLE fo_bhavcopy RENAME COLUMN last_price TO "LAST_PRICE"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'fo_bhavcopy' AND column_name = 'prev_close') THEN
        EXECUTE 'ALTER TABLE fo_bhavcopy RENAME COLUMN prev_close TO "PREV_CLOSE"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'fo_bhavcopy' AND column_name = 'underlying_price') THEN
        EXECUTE 'ALTER TABLE fo_bhavcopy RENAME COLUMN underlying_price TO "UNDERLYING_PRICE"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'fo_bhavcopy' AND column_name = 'settlement_price') THEN
        EXECUTE 'ALTER TABLE fo_bhavcopy RENAME COLUMN settlement_price TO "SETTLEMENT_PRICE"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'fo_bhavcopy' AND column_name = 'open_interest') THEN
        EXECUTE 'ALTER TABLE fo_bhavcopy RENAME COLUMN open_interest TO "OPEN_INTEREST"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'fo_bhavcopy' AND column_name = 'change_in_open_interest') THEN
        EXECUTE 'ALTER TABLE fo_bhavcopy RENAME COLUMN change_in_open_interest TO "CHANGE_IN_OPEN_INTEREST"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'fo_bhavcopy' AND column_name = 'ttl_trd_qty') THEN
        EXECUTE 'ALTER TABLE fo_bhavcopy RENAME COLUMN ttl_trd_qty TO "TTL_TRD_QNTY"';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'fo_bhavcopy' AND column_name = 'turnover_lacs') THEN
        EXECUTE 'ALTER TABLE fo_bhavcopy RENAME COLUMN turnover_lacs TO "TURNOVER_LACS"';
    END IF;
END $$;

-- ============================================================================
-- 4. COMPANY MARKET — Migrate/Create table structure
-- ============================================================================
CREATE TABLE IF NOT EXISTS company_market (
    "SYMBOL" TEXT PRIMARY KEY
);

-- Rename company_id if legacy column exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'company_market' AND column_name = 'company_id') THEN
        EXECUTE 'ALTER TABLE company_market RENAME COLUMN company_id TO "SYMBOL"';
    END IF;
END $$;

ALTER TABLE company_market ADD COLUMN IF NOT EXISTS "CURRENT_MARKET_PRICE" NUMERIC(18,2);
ALTER TABLE company_market ADD COLUMN IF NOT EXISTS "PE_RATIO" NUMERIC(18,2);
ALTER TABLE company_market ADD COLUMN IF NOT EXISTS "MARKET_CAP_CR" NUMERIC(18,2);
ALTER TABLE company_market ADD COLUMN IF NOT EXISTS "DIVIDEND_YIELD" NUMERIC(10,2);
ALTER TABLE company_market ADD COLUMN IF NOT EXISTS "QUARTERLY_PROFIT_CR" NUMERIC(18,2);
ALTER TABLE company_market ADD COLUMN IF NOT EXISTS "QUARTERLY_PROFIT_GROWTH" NUMERIC(18,2);
ALTER TABLE company_market ADD COLUMN IF NOT EXISTS "QUARTERLY_SALES_CR" NUMERIC(18,2);
ALTER TABLE company_market ADD COLUMN IF NOT EXISTS "QUARTERLY_SALES_GROWTH" NUMERIC(18,2);
ALTER TABLE company_market ADD COLUMN IF NOT EXISTS "ROCE" NUMERIC(18,2);
ALTER TABLE company_market ADD COLUMN IF NOT EXISTS screener_rank INTEGER;
ALTER TABLE company_market ADD COLUMN IF NOT EXISTS scraped_at TIMESTAMPTZ;
ALTER TABLE company_market ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE company_market ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- FK alignment
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_company_market_company') THEN
        ALTER TABLE company_market
        ADD CONSTRAINT fk_company_market_company
        FOREIGN KEY ("SYMBOL")
        REFERENCES company_master("SYMBOL")
        ON UPDATE CASCADE
        ON DELETE CASCADE;
    END IF;
END $$;

-- ============================================================================
-- 5. INDEXES & TRIGGERS
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_company_market_symbol ON company_market("SYMBOL");
CREATE INDEX IF NOT EXISTS idx_company_market_market_cap ON company_market("MARKET_CAP_CR" DESC);
CREATE INDEX IF NOT EXISTS idx_company_market_scraped_at ON company_market(scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_company_master_company_name ON company_master(UPPER("NAME_OF_COMPANY"));
CREATE INDEX IF NOT EXISTS idx_equity_bhavcopy_symbol_date ON equity_bhavcopy ("SYMBOL", "DATE1" DESC);
CREATE INDEX IF NOT EXISTS idx_fo_bhavcopy_symbol_date ON fo_bhavcopy ("SYMBOL", "DATE1" DESC);

DROP TRIGGER IF EXISTS trg_company_market_updated_at ON company_market;
CREATE TRIGGER trg_company_market_updated_at
BEFORE UPDATE ON company_market
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_company_master_updated_at ON company_master;
CREATE TRIGGER trg_company_master_updated_at
BEFORE UPDATE ON company_master
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- 6. TimescaleDB Compression
--    FIX: DISC-5 — Standardized compression properties across both scripts.
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

COMMIT;

-- ============================================================================
-- 7. Validation Queries
-- ============================================================================
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_name IN ('company_master', 'company_market', 'equity_bhavcopy', 'fo_bhavcopy')
ORDER BY table_name, ordinal_position;