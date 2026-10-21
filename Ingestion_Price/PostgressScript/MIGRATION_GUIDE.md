# SQL Schema Migration Guide - From 001_init_schema.sql to Compatible Version

**Purpose**: Migrate existing PostgreSQL database schema to be compatible with Python NSE ingestion project

**When to Use**: If you have already run `001_init_schema.sql` and need to upgrade to compatible version

---

## Overview

The original SQL schema uses lowercase column names (PostgreSQL convention), but the Python ingestion project uses UPPERCASE column names (following NSE source data format). This guide provides a safe migration path with data preservation.

---

## Pre-Migration Checklist

```bash
# 1. Backup your database
pg_dump StockAnalysis_Bhavcopy > backup_$(date +%Y%m%d_%H%M%S).sql

# 2. Verify current schema
psql -U postgres -d StockAnalysis_Bhavcopy -c "\dt"

# 3. Check data exists
psql -U postgres -d StockAnalysis_Bhavcopy -c "SELECT COUNT(*) FROM company_master; SELECT COUNT(*) FROM equity_bhavcopy; SELECT COUNT(*) FROM fo_bhavcopy;"

# 4. Document any custom indexes or constraints
psql -U postgres -d StockAnalysis_Bhavcopy -c "\d+ company_master"
psql -U postgres -d StockAnalysis_Bhavcopy -c "\d+ equity_bhavcopy"
psql -U postgres -d StockAnalysis_Bhavcopy -c "\d+ fo_bhavcopy"
```

---

## Migration Strategy

### Option 1: RECOMMENDED - Rename Columns In-Place (Fastest)

**Time**: 5-10 minutes  
**Risk**: Low (uses ALTER TABLE)  
**Downtime**: 1-2 seconds during each rename

```bash
# Connect to database
psql -U postgres -d StockAnalysis_Bhavcopy

# Run the migration script below
```

#### Migration SQL Script

```sql
-- =============================================================================
-- COMPANY MASTER TABLE MIGRATION
-- =============================================================================
-- Step 1: Add missing SERIES column
ALTER TABLE company_master ADD COLUMN IF NOT EXISTS "SERIES" TEXT;

-- Step 2: Drop existing indexes/constraints that reference the old columns
DROP TRIGGER IF EXISTS trg_company_master_updated_at ON company_master;

-- Step 3: Rename columns to match Python format
ALTER TABLE company_master RENAME COLUMN symbol TO "SYMBOL";
ALTER TABLE company_master RENAME COLUMN company_name TO "NAME OF COMPANY";
ALTER TABLE company_master RENAME COLUMN company_name TO "DATE OF LISTING";
ALTER TABLE company_master RENAME COLUMN isin_number TO "ISIN NUMBER";
ALTER TABLE company_master RENAME COLUMN isin_number TO "FACE VALUE";  

-- Step 4: Re-create trigger
CREATE TRIGGER trg_company_master_updated_at
BEFORE UPDATE ON company_master
FOR EACH ROW
EXECUTE FUNCTION set_company_master_updated_at();

-- Step 5: Verify migration
-- SELECT column_name, data_type FROM information_schema.columns 
-- WHERE table_name = 'company_master' ORDER BY ordinal_position;

-- =============================================================================
-- EQUITY BHAVCOPY TABLE MIGRATION
-- =============================================================================
-- Step 1: Get existing hypertable configuration
-- SELECT * FROM timescaledb_information.hypertables WHERE table_name = 'equity_bhavcopy';

-- Step 2: Drop foreign key constraints that may reference equity_bhavcopy
-- (if any exist - check your actual constraints)
-- ALTER TABLE <table_name> DROP CONSTRAINT <constraint_name>;

-- Step 3: Drop existing primary key and indexes
ALTER TABLE equity_bhavcopy DROP CONSTRAINT IF EXISTS equity_bhavcopy_pkey;
DROP INDEX IF EXISTS idx_equity_bhavcopy_symbol_date;

-- Step 4: Rename all columns to UPPERCASE
ALTER TABLE equity_bhavcopy RENAME COLUMN date1 TO "DATE1";
ALTER TABLE equity_bhavcopy RENAME COLUMN symbol TO "SYMBOL";
ALTER TABLE equity_bhavcopy RENAME COLUMN series TO "SERIES";
ALTER TABLE equity_bhavcopy RENAME COLUMN prev_close TO "PREV_CLOSE";
ALTER TABLE equity_bhavcopy RENAME COLUMN open_price TO "OPEN_PRICE";
ALTER TABLE equity_bhavcopy RENAME COLUMN high_price TO "HIGH_PRICE";
ALTER TABLE equity_bhavcopy RENAME COLUMN low_price TO "LOW_PRICE";
ALTER TABLE equity_bhavcopy RENAME COLUMN last_price TO "LAST_PRICE";
ALTER TABLE equity_bhavcopy RENAME COLUMN close_price TO "CLOSE_PRICE";
ALTER TABLE equity_bhavcopy RENAME COLUMN avg_price TO "AVG_PRICE";
ALTER TABLE equity_bhavcopy RENAME COLUMN ttl_trd_qty TO "TTL_TRD_QTY";
ALTER TABLE equity_bhavcopy RENAME COLUMN turnover_lacs TO "TURNOVER_LACS";
ALTER TABLE equity_bhavcopy RENAME COLUMN no_of_trades TO "NO_OF_TRADES";
ALTER TABLE equity_bhavcopy RENAME COLUMN deliv_qty TO "DELIV_QTY";
ALTER TABLE equity_bhavcopy RENAME COLUMN deliv_per TO "DELIV_PER";

-- Step 5: Re-create primary key with UPPERCASE column names
ALTER TABLE equity_bhavcopy ADD PRIMARY KEY ("DATE1", "SYMBOL", "SERIES");

-- Step 6: Re-create index
CREATE INDEX idx_equity_bhavcopy_symbol_date
    ON equity_bhavcopy ("SYMBOL", "DATE1" DESC);

-- Step 7: Verify migration
-- SELECT column_name, data_type FROM information_schema.columns 
-- WHERE table_name = 'equity_bhavcopy' ORDER BY ordinal_position;

-- =============================================================================
-- F&O BHAVCOPY TABLE MIGRATION
-- =============================================================================
-- Step 1: Drop existing primary key and indexes
ALTER TABLE fo_bhavcopy DROP CONSTRAINT IF EXISTS fo_bhavcopy_pkey;
DROP INDEX IF EXISTS idx_fo_bhavcopy_symbol_date;

-- Step 2: Rename all columns to UPPERCASE
ALTER TABLE fo_bhavcopy RENAME COLUMN date1 TO "DATE1";
ALTER TABLE fo_bhavcopy RENAME COLUMN segment TO "SEGMENT";
ALTER TABLE fo_bhavcopy RENAME COLUMN symbol TO "SYMBOL";
ALTER TABLE fo_bhavcopy RENAME COLUMN expiry_date TO "EXPIRY_DATE";
ALTER TABLE fo_bhavcopy RENAME COLUMN instrument_number TO "INSTRUMENT_NUMBER";
ALTER TABLE fo_bhavcopy RENAME COLUMN open_price TO "OPEN_PRICE";
ALTER TABLE fo_bhavcopy RENAME COLUMN high_price TO "HIGH_PRICE";
ALTER TABLE fo_bhavcopy RENAME COLUMN low_price TO "LOW_PRICE";
ALTER TABLE fo_bhavcopy RENAME COLUMN close_price TO "CLOSE_PRICE";
ALTER TABLE fo_bhavcopy RENAME COLUMN last_price TO "LAST_PRICE";
ALTER TABLE fo_bhavcopy RENAME COLUMN prev_close TO "PREV_CLOSE";
ALTER TABLE fo_bhavcopy RENAME COLUMN underlying_price TO "UNDERLYING_PRICE";
ALTER TABLE fo_bhavcopy RENAME COLUMN settlement_price TO "SETTLEMENT_PRICE";
ALTER TABLE fo_bhavcopy RENAME COLUMN open_interest TO "OPEN_INTEREST";
ALTER TABLE fo_bhavcopy RENAME COLUMN change_in_open_interest TO "CHANGE_IN_OPEN_INTEREST";
ALTER TABLE fo_bhavcopy RENAME COLUMN ttl_trd_qty TO "TTL_TRD_QTY";
ALTER TABLE fo_bhavcopy RENAME COLUMN turnover_lacs TO "TURNOVER_LACS";

-- Step 3: Re-create primary key with UPPERCASE column names
ALTER TABLE fo_bhavcopy ADD PRIMARY KEY ("DATE1", "SYMBOL", "EXPIRY_DATE", "INSTRUMENT_NUMBER");

-- Step 4: Re-create index
CREATE INDEX idx_fo_bhavcopy_symbol_date
    ON fo_bhavcopy ("SYMBOL", "DATE1" DESC);

-- Step 5: Verify migration
-- SELECT column_name, data_type FROM information_schema.columns 
-- WHERE table_name = 'fo_bhavcopy' ORDER BY ordinal_position;

-- =============================================================================
-- POST-MIGRATION VERIFICATION
-- =============================================================================

-- Verify all tables have correct columns
\d+ company_master
\d+ equity_bhavcopy
\d+ fo_bhavcopy

-- Verify data integrity
SELECT COUNT(*) as company_count FROM company_master;
SELECT COUNT(*) as equity_count FROM equity_bhavcopy;
SELECT COUNT(*) as fo_count FROM fo_bhavcopy;

-- Verify primary keys work
SELECT COUNT(DISTINCT ("SYMBOL")) FROM company_master;
SELECT COUNT(DISTINCT ("DATE1", "SYMBOL", "SERIES")) FROM equity_bhavcopy;
SELECT COUNT(DISTINCT ("DATE1", "SYMBOL", "EXPIRY_DATE", "INSTRUMENT_NUMBER")) FROM fo_bhavcopy;

-- Check for any NULL primary key values
SELECT * FROM company_master WHERE "SYMBOL" IS NULL;
SELECT * FROM equity_bhavcopy WHERE "DATE1" IS NULL OR "SYMBOL" IS NULL OR "SERIES" IS NULL;
SELECT * FROM fo_bhavcopy WHERE "DATE1" IS NULL OR "SYMBOL" IS NULL OR "EXPIRY_DATE" IS NULL OR "INSTRUMENT_NUMBER" IS NULL;
```

---

### Option 2: Drop and Recreate (Safest for Clean Database)

**Time**: 10-15 minutes  
**Risk**: Very Low (preserves data if done carefully)  
**Downtime**: ~5-10 seconds total

Use this if you want to start fresh or if you don't have critical data yet.

```sql
-- Step 1: Backup
-- (Already done above)

-- Step 2: Drop all tables
DROP TABLE IF EXISTS fo_bhavcopy CASCADE;
DROP TABLE IF EXISTS equity_bhavcopy CASCADE;
DROP TABLE IF EXISTS company_master CASCADE;

-- Step 3: Drop functions
DROP FUNCTION IF EXISTS set_company_master_updated_at() CASCADE;

-- Step 4: Run new schema from 001_init_schema_COMPATIBLE.sql
-- (See below for full script)
```

---

### Option 3: Migrate to Temporary Tables (Most Conservative)

**Time**: 20-30 minutes  
**Risk**: Very Low (preserves old data)  
**Complexity**: High

This keeps both old and new schemas, allowing rollback.

```sql
-- Step 1: Rename old tables to _old suffix
ALTER TABLE company_master RENAME TO company_master_old;
ALTER TABLE equity_bhavcopy RENAME TO equity_bhavcopy_old;
ALTER TABLE fo_bhavcopy RENAME TO fo_bhavcopy_old;

-- Step 2: Create new schema from 001_init_schema_COMPATIBLE.sql

-- Step 3: Migrate data from old tables to new
INSERT INTO company_master ("SYMBOL", "NAME OF COMPANY", "SERIES", "ISIN NUMBER")
SELECT "SYMBOL", "NAME OF COMPANY", "SERIES", "ISIN NUMBER" FROM company_master_old;

INSERT INTO equity_bhavcopy ("DATE1", "SYMBOL", "SERIES", "PREV_CLOSE", "OPEN_PRICE", 
    "HIGH_PRICE", "LOW_PRICE", "LAST_PRICE", "CLOSE_PRICE", "AVG_PRICE",
    "TTL_TRD_QTY", "TURNOVER_LACS", "NO_OF_TRADES", "DELIV_QTY", "DELIV_PER")
SELECT "DATE1", "SYMBOL", "SERIES", "PREV_CLOSE", "OPEN_PRICE",
    "HIGH_PRICE", "LOW_PRICE", "LAST_PRICE", "CLOSE_PRICE", "AVG_PRICE",
    "TTL_TRD_QTY", "TURNOVER_LACS", "NO_OF_TRADES", "DELIV_QTY", "DELIV_PER"
FROM equity_bhavcopy_old;

INSERT INTO fo_bhavcopy ("DATE1", "SEGMENT", "SYMBOL", "EXPIRY_DATE", "INSTRUMENT_NUMBER",
    "OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE", "LAST_PRICE", "PREV_CLOSE",
    "UNDERLYING_PRICE", "SETTLEMENT_PRICE", "OPEN_INTEREST", "CHANGE_IN_OPEN_INTEREST",
    "TTL_TRD_QTY", "TURNOVER_LACS")
SELECT "DATE1", "SEGMENT", "SYMBOL", "EXPIRY_DATE", "INSTRUMENT_NUMBER",
    "OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE", "LAST_PRICE", "PREV_CLOSE",
    "UNDERLYING_PRICE", "SETTLEMENT_PRICE", "OPEN_INTEREST", "CHANGE_IN_OPEN_INTEREST",
    "TTL_TRD_QTY", "TURNOVER_LACS"
FROM fo_bhavcopy_old;

-- Step 4: Verify data
SELECT COUNT(*) FROM company_master;
SELECT COUNT(*) FROM equity_bhavcopy;
SELECT COUNT(*) FROM fo_bhavcopy;

-- Step 5: Drop old tables (only after verification)
DROP TABLE company_master_old CASCADE;
DROP TABLE equity_bhavcopy_old CASCADE;
DROP TABLE fo_bhavcopy_old CASCADE;
```

---

## Execute Migration

### Using psql (Recommended)

```bash
# Option 1: Pipe SQL directly
psql -U postgres -d StockAnalysis_Bhavcopy << 'EOF'
-- Paste the migration SQL script from Option 1 above
EOF

# Option 2: Save to file and run
cat > migration.sql << 'EOF'
-- Paste the migration SQL script from Option 1 above
EOF

psql -U postgres -d StockAnalysis_Bhavcopy -f migration.sql

# Option 3: Interactive
psql -U postgres -d StockAnalysis_Bhavcopy
# Then paste commands one by one
```

### Using Python sqlalchemy

```python
import sqlalchemy as sa

# Create engine
engine = sa.create_engine(
    "postgresql+psycopg2://postgres:password@localhost/StockAnalysis_Bhavcopy"
)

# Execute migration
with engine.begin() as conn:
    # Paste SQL commands here using conn.execute(text("SQL_HERE"))
    pass
```

---

## Verification Steps

After migration, verify everything worked:

```sql
-- 1. Check company_master has SERIES column
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'company_master'
ORDER BY ordinal_position;

-- Expected output:
-- SYMBOL              | TEXT
-- NAME OF COMPANY     | TEXT
-- SERIES              | TEXT
-- ISIN NUMBER         | TEXT
-- created_at          | TIMESTAMPTZ
-- updated_at          | TIMESTAMPTZ

-- 2. Check equity_bhavcopy has all UPPERCASE columns
SELECT COUNT(*) FROM information_schema.columns
WHERE table_name = 'equity_bhavcopy'
AND column_name ~ '^[A-Z_]+$';  -- Should return 15

-- 3. Check fo_bhavcopy has all UPPERCASE columns
SELECT COUNT(*) FROM information_schema.columns
WHERE table_name = 'fo_bhavcopy'
AND column_name ~ '^[A-Z_]+$';  -- Should return 17

-- 4. Verify primary keys
SELECT constraint_name, column_name FROM information_schema.constraint_column_usage
WHERE table_name IN ('company_master', 'equity_bhavcopy', 'fo_bhavcopy')
ORDER BY table_name, ordinal_position;

-- 5. Test data insertion with new columns
INSERT INTO company_master ("SYMBOL", "NAME OF COMPANY", "SERIES", "ISIN NUMBER")
VALUES ('TEST', 'Test Company', 'EQ', 'TEST123')
ON CONFLICT ("SYMBOL") DO UPDATE SET
    "NAME OF COMPANY" = EXCLUDED."NAME OF COMPANY",
    "SERIES" = EXCLUDED."SERIES",
    "ISIN NUMBER" = EXCLUDED."ISIN NUMBER";

-- 6. Verify insert worked
SELECT * FROM company_master WHERE "SYMBOL" = 'TEST';

-- 7. Cleanup test data
DELETE FROM company_master WHERE "SYMBOL" = 'TEST';
```

---

## Rollback Procedure

If migration fails or causes issues:

```bash
# Restore from backup
psql -U postgres < backup_*.sql

# Or if using Option 3 (conservative migration)
# The old tables (_old suffix) are still available
```

---

## Post-Migration Steps

1. **Update Python Configuration**:
   - Verify `config.py` table names match
   - Ensure database URL is correct

2. **Test Ingestion**:
   ```bash
   cd ingestion/
   python main.py --skip-equity --skip-fo  # Test company master only
   ```

3. **Verify Data**:
   ```sql
   SELECT COUNT(*) FROM company_master;
   SELECT * FROM company_master LIMIT 5;
   ```

4. **Update Documentation**:
   - Update DB_SCHEMA.md with new column names
   - Document this migration in project README

5. **Schedule Full Ingestion**:
   ```bash
   python main.py --start-date 2026-01-01 --end-date 2026-06-12
   ```

---

## Common Issues and Solutions

### Issue: "Column does not exist" error

**Cause**: Column names still lowercase after migration

**Solution**: 
```sql
-- Check actual column names
SELECT column_name FROM information_schema.columns WHERE table_name = 'equity_bhavcopy';
-- If lowercase, run migration again
```

### Issue: "Constraint not found" when dropping

**Cause**: Constraint doesn't exist yet

**Solution**: The migration uses `IF EXISTS` clauses, so just continue

### Issue: Data seems missing after migration

**Cause**: Column references in application code need updates

**Solution**: 
```python
# Check data is there
psql -c "SELECT COUNT(*) FROM company_master;"
# Data should exist
```

### Issue: TimescaleDB hypertable issues

**Cause**: Renaming columns on hypertable might cause issues

**Solution**:
```sql
-- Check hypertable status
SELECT * FROM timescaledb_information.hypertables;
-- If issues, see TimescaleDB migration documentation
```

---

## Verification Checklist

After migration, verify:

- [ ] Backup created successfully
- [ ] All tables have UPPERCASE column names
- [ ] company_master has SERIES column
- [ ] Primary keys are intact
- [ ] Indexes are rebuilt
- [ ] Data count matches pre-migration
- [ ] No NULL values in primary key columns
- [ ] Python ingestion script connects successfully
- [ ] Test ingestion loads data without errors
- [ ] Data in tables matches expected format

---

## Next Steps

Once migration is complete:

1. Run Python ingestion project:
   ```bash
   python ingestion/main.py
   ```

2. Monitor logs:
   ```bash
   tail -f ingestion/logs/ingestion.log
   ```

3. Query results:
   ```sql
   SELECT COUNT(*) FROM equity_bhavcopy;
   SELECT * FROM equity_bhavcopy LIMIT 10;
   ```

---

## Support

If you encounter issues:

1. Check SQL_COMPATIBILITY_REPORT.md for detailed compatibility info
2. Review migration SQL for syntax errors
3. Ensure PostgreSQL and TimescaleDB versions are correct
4. Check database logs: `tail -f /var/log/postgresql/postgresql.log`

