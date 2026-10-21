-- Read-only validation for StockAnalysis_Bhavcopy.
-- Run using psql -d StockAnalysis_Bhavcopy -f validation/postgresql.sql
-- Or run individual statements in pgAdmin/DBeaver.
-- Edit the date range below for your ingestion window.
BEGIN READ ONLY;
SET LOCAL TIME ZONE 'Asia/Kolkata';

-- 1. Counts, trade-date coverage and ingestion freshness.
SELECT 'equity_bhavcopy' AS table_name, COUNT(*) AS total_rows,
       COUNT(DISTINCT "SYMBOL") AS symbols,
       COUNT(DISTINCT "DATE1"::date) AS trading_days,
       MIN("DATE1") AS earliest_trade_date, MAX("DATE1") AS latest_trade_date,
       MAX(inserted_at) AS latest_ingestion
FROM equity_bhavcopy
UNION ALL
SELECT 'fo_bhavcopy', COUNT(*), COUNT(DISTINCT "SYMBOL"),
       COUNT(DISTINCT "DATE1"::date), MIN("DATE1"), MAX("DATE1"), MAX(inserted_at)
FROM fo_bhavcopy;

SELECT 'company_master' AS table_name, COUNT(*) AS total_rows,
       MAX(updated_at) AS latest_update FROM company_master
UNION ALL
SELECT 'company_market', COUNT(*), MAX(updated_at) FROM company_market;

-- 2. Daily volumes: review unexpectedly low counts or missing sides.
WITH equity AS (
    SELECT "DATE1"::date AS trade_date, COUNT(*) AS equity_rows,
           COUNT(DISTINCT "SYMBOL") AS equity_symbols
    FROM equity_bhavcopy GROUP BY 1
), fo AS (
    SELECT "DATE1"::date AS trade_date, COUNT(*) AS fo_rows,
           COUNT(DISTINCT "SYMBOL") AS fo_symbols
    FROM fo_bhavcopy GROUP BY 1
)
SELECT COALESCE(e.trade_date, f.trade_date) AS trade_date,
       COALESCE(e.equity_rows, 0) AS equity_rows,
       COALESCE(e.equity_symbols, 0) AS equity_symbols,
       COALESCE(f.fo_rows, 0) AS fo_rows,
       COALESCE(f.fo_symbols, 0) AS fo_symbols
FROM equity e FULL JOIN fo f USING (trade_date)
ORDER BY trade_date DESC;

-- 3. Potential missing weekdays, NOT confirmed missing exchange sessions.
-- Excludes weekends but not exchange holidays; misses special weekend sessions.
WITH dates AS (
    SELECT d::date AS trade_date
    FROM generate_series(DATE '2026-03-30', DATE '2026-09-30',
                         INTERVAL '1 day') AS d
    WHERE EXTRACT(ISODOW FROM d) BETWEEN 1 AND 5
), equity AS (
    SELECT DISTINCT "DATE1"::date AS trade_date FROM equity_bhavcopy
), fo AS (
    SELECT DISTINCT "DATE1"::date AS trade_date FROM fo_bhavcopy
)
SELECT d.trade_date, e.trade_date IS NULL AS equity_missing,
       f.trade_date IS NULL AS fo_missing
FROM dates d
LEFT JOIN equity e USING (trade_date)
LEFT JOIN fo f USING (trade_date)
WHERE e.trade_date IS NULL OR f.trade_date IS NULL
ORDER BY d.trade_date;

-- 4. Duplicate business keys: expect zero rows.
-- Calendar-day grouping also detects different timestamps for the same day.
SELECT "DATE1"::date AS trade_date, "SYMBOL", "SERIES", COUNT(*) AS copies
FROM equity_bhavcopy GROUP BY 1, 2, 3 HAVING COUNT(*) > 1;

SELECT "DATE1"::date AS trade_date, "SYMBOL", "EXPIRY_DATE",
       "INSTRUMENT_NUMBER", COUNT(*) AS copies
FROM fo_bhavcopy GROUP BY 1, 2, 3, 4 HAVING COUNT(*) > 1;

-- 5. Price/volume/date anomalies: investigation candidates.
-- Zero prices may occur for inactive F&O contracts.
WITH prices AS (
    SELECT 'equity' AS source, "DATE1", "SYMBOL", "OPEN_PRICE",
           "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE", "TTL_TRD_QNTY"
    FROM equity_bhavcopy
    UNION ALL
    SELECT 'fo', "DATE1", "SYMBOL", "OPEN_PRICE", "HIGH_PRICE",
           "LOW_PRICE", "CLOSE_PRICE", "TTL_TRD_QNTY"
    FROM fo_bhavcopy
)
SELECT * FROM prices
WHERE "DATE1"::date > CURRENT_DATE
   OR NULLIF(BTRIM("SYMBOL"), '') IS NULL
   OR "OPEN_PRICE" IS NULL OR "HIGH_PRICE" IS NULL
   OR "LOW_PRICE" IS NULL OR "CLOSE_PRICE" IS NULL
   OR "TTL_TRD_QNTY" IS NULL
   OR "CLOSE_PRICE" <= 0 OR "TTL_TRD_QNTY" < 0
   OR "HIGH_PRICE" < "LOW_PRICE"
   OR "HIGH_PRICE" < GREATEST("OPEN_PRICE", "CLOSE_PRICE")
   OR "LOW_PRICE" > LEAST("OPEN_PRICE", "CLOSE_PRICE")
ORDER BY "DATE1" DESC LIMIT 100;

-- 6. Company-market completeness/freshness (seven-day review threshold).
-- Missing rows may be expected for companies outside the ingestion universe.
SELECT m."SYMBOL", m."NAME_OF_COMPANY", c."MARKET_CAP_CR",
       c."CURRENT_MARKET_PRICE", c.scraped_at
FROM company_master m
LEFT JOIN company_market c ON c."SYMBOL" = m."SYMBOL"
WHERE c."SYMBOL" IS NULL OR c."MARKET_CAP_CR" IS NULL
   OR c."CURRENT_MARKET_PRICE" IS NULL OR c.scraped_at IS NULL
   OR c.scraped_at < now() - INTERVAL '7 days'
ORDER BY c.scraped_at NULLS FIRST;
COMMIT;
