# SQL-Python Compatibility - Quick Implementation Guide

**TL;DR**: Your SQL schema is INCOMPATIBLE with Python ingestion. Choose a fix below and implement (5-10 minutes).

---

## 🚨 The Problem (30 seconds)

```
❌ Python expects: ['DATE1', 'SYMBOL', 'SERIES', 'PREV_CLOSE', ...]
❌ SQL has:      (date1, symbol, series, prev_close, ...)
❌ Result:        INSERT fails → "column not found" error
```

---

## 🔧 Quick Fix - Choose ONE

### Fix Option 1: Use Compatible SQL Schema (RECOMMENDED)
**⏱️ Time**: 2 minutes  
**📍 For**: New databases

```bash
# 1. Copy-paste into psql:
psql -U postgres -d StockAnalysis_Bhavcopy

# 2. Then paste entire contents of:
# PostgressScript/001_init_schema_COMPATIBLE.sql

# 3. Done! Schema is now UPPERCASE-compatible
```

**If you have existing data**, see Migration Guide instead.

---

### Fix Option 2: Migrate Existing Database (2 strategies)
**⏱️ Time**: 5-10 minutes  
**📍 For**: Existing databases with data

#### Strategy A: In-Place Column Rename (Safest)
```bash
# 1. Backup first:
pg_dump StockAnalysis_Bhavcopy > backup_$(date +%Y%m%d).sql

# 2. Open migration guide:
cat PostgressScript/MIGRATION_GUIDE.md

# 3. Run "Option 1: RECOMMENDED - Rename Columns In-Place"

# 4. That's it - data preserved, columns renamed
```

#### Strategy B: Drop & Recreate (Cleanest)
```bash
# 1. Backup first:
pg_dump StockAnalysis_Bhavcopy > backup_$(date +%Y%m%d).sql

# 2. Drop tables (if safe):
psql -U postgres -d StockAnalysis_Bhavcopy
  DROP TABLE IF EXISTS fo_bhavcopy, equity_bhavcopy, company_master CASCADE;

# 3. Run compatible schema:
# (Paste from 001_init_schema_COMPATIBLE.sql)
```

---

### Fix Option 3: Update Python Instead
**⏱️ Time**: 10 minutes  
**📍 For**: Keep existing SQL, modify Python

Edit `ingestion/db_loader.py` line 75:

```python
def load_dataframe(self, table_name, dataframe, if_exists="append") -> int:
    if dataframe.empty:
        logger.warning(f"Empty DataFrame provided for {table_name}, skipping load")
        return 0
    
    try:
        # ✅ ADD THIS LINE (convert to lowercase):
        dataframe.columns = dataframe.columns.str.lower()
        
        # Convert DATE columns to datetime
        for date_col in ["date1", "expiry_date"]:  # ← use lowercase now
            if date_col in dataframe.columns:
                dataframe[date_col] = pd.to_datetime(dataframe[date_col])
        
        rows_loaded = len(dataframe)
        dataframe.to_sql(
            table_name,
            self.engine,
            if_exists=if_exists,
            index=False,
            chunksize=1000
        )
        
        logger.info(f"Successfully loaded {rows_loaded} rows into {table_name}")
        return rows_loaded
```

**BUT**: You still need to add SERIES column to company_master:

```sql
ALTER TABLE company_master ADD COLUMN IF NOT EXISTS series TEXT;
```

---

## ✅ After Fixing - Test It

```bash
cd ingestion/

# Test 1: Company master only (fastest)
python main.py --skip-equity --skip-fo

# Test 2: Check logs
tail -f logs/ingestion.log

# Test 3: Verify in database
psql -U postgres -d StockAnalysis_Bhavcopy -c "SELECT COUNT(*) FROM company_master;"

# Test 4: If test 1 passed, run full ingestion
python main.py --start-date 2026-06-01 --end-date 2026-06-10
```

---

## 📊 Comparison: Which Option?

| Factor | Option 1 (SQL) | Option 2 (Migrate) | Option 3 (Python) |
|--------|---|---|---|
| **Time** | 2 min | 5-10 min | 10 min |
| **Risk** | None | Low | Low |
| **For New DB** | ✅ Yes | N/A | ✅ Yes |
| **With Existing Data** | Need migration | ✅ Best | ✅ Works |
| **Recommendation** | ✅ BEST | Good | Alternative |
| **Effort** | Copy-paste | Follow guide | Edit 1 line + SQL ALTER |

---

## 🎯 Decision Flowchart

```
Do you have existing data in database?
│
├─ NO (New database)
│  └─ Use Option 1: 001_init_schema_COMPATIBLE.sql
│     (Just copy-paste into psql)
│
└─ YES (Existing data)
   ├─ Do you want to keep current SQL schema?
   │  ├─ NO (Change SQL to UPPERCASE)
   │  │  └─ Use Option 2: MIGRATION_GUIDE.md
   │  │     (Run 5-minute migration)
   │  │
   │  └─ YES (Keep SQL as-is)
   │     └─ Use Option 3: Update Python
   │        (Edit db_loader.py + 1 ALTER TABLE)
```

---

## 📋 Detailed Issues Fixed

| Issue | Option 1 | Option 2 | Option 3 |
|-------|----------|----------|----------|
| **Column case mismatch** | ✅ SQL → UPPERCASE | ✅ Rename to UPPERCASE | ✅ Python converts to lowercase |
| **Missing SERIES column** | ✅ Included | ✅ Added during migration | ⚠️ Manual ALTER needed |
| **Company Master naming** | ✅ "NAME OF COMPANY" format | ✅ Renamed correctly | ⚠️ Only if Option 3 works |
| **Primary keys** | ✅ Correct | ✅ Recreated | ✅ Works as-is |
| **Data types** | ✅ Compatible | ✅ Preserved | ✅ Compatible |

---

## 🚀 Full Implementation Steps

### If Using Option 1 (SQL - RECOMMENDED)

```bash
# Step 1: Backup (if database exists)
pg_dump StockAnalysis_Bhavcopy > backup_$(date +%Y%m%d).sql

# Step 2: Get the schema file
cat PostgressScript/001_init_schema_COMPATIBLE.sql

# Step 3: Connect to PostgreSQL
psql -U postgres

# Step 4: Create/select database and paste schema
CREATE DATABASE StockAnalysis_Bhavcopy;  -- or \connect if exists
-- Then copy-paste entire schema file

# Step 5: Verify
\d company_master
\d equity_bhavcopy
\d fo_bhavcopy
SELECT COUNT(*) FROM company_master;

# Step 6: Run Python ingestion
cd /path/to/ingestion
python main.py --skip-equity --skip-fo

# Step 7: Monitor
tail -f logs/ingestion.log
```

### If Using Option 2 (Migrate)

```bash
# Follow PostgressScript/MIGRATION_GUIDE.md
# Step-by-step instructions with multiple safety options

# Quick version:
pg_dump StockAnalysis_Bhavcopy > backup_$(date +%Y%m%d).sql
psql -U postgres -d StockAnalysis_Bhavcopy < migration.sql
# (See MIGRATION_GUIDE.md for full migration.sql)
```

### If Using Option 3 (Python)

```bash
# Edit ingestion/db_loader.py
# Add: dataframe.columns = dataframe.columns.str.lower()

# Add missing column:
psql -U postgres -d StockAnalysis_Bhavcopy -c \
  "ALTER TABLE company_master ADD COLUMN IF NOT EXISTS series TEXT;"

# Test:
cd ingestion
python main.py --skip-equity --skip-fo
```

---

## 🔍 Verification Commands

After implementing your chosen option:

```sql
-- Check company_master structure
\d company_master
-- Should show: SYMBOL, NAME OF COMPANY, SERIES, ISIN NUMBER (or all lowercase)

-- Check equity_bhavcopy structure
\d equity_bhavcopy
-- Should show: DATE1, SYMBOL, SERIES, PREV_CLOSE, etc.

-- Check data can be inserted
INSERT INTO company_master (SYMBOL, "NAME OF COMPANY", SERIES, "ISIN NUMBER")
VALUES ('TEST', 'Test', 'EQ', 'TEST')
ON CONFLICT (SYMBOL) DO NOTHING;

-- Verify insert
SELECT * FROM company_master WHERE SYMBOL = 'TEST';

-- Cleanup
DELETE FROM company_master WHERE SYMBOL = 'TEST';

-- Test Python connection
SELECT COUNT(*) FROM company_master;
```

---

## 📚 Documentation Files Created

You now have:

1. **SQL_COMPATIBILITY_REPORT.md** (200+ lines)
   - Detailed analysis of all incompatibilities
   - Examples of failures
   - Column mapping tables
   - Recommendations with code

2. **001_init_schema_COMPATIBLE.sql**
   - Complete, ready-to-use SQL schema
   - All UPPERCASE column names
   - Includes SERIES column
   - Includes examples of correct INSERT statements

3. **MIGRATION_GUIDE.md** (400+ lines)
   - 3 migration strategies
   - Pre-migration checklist
   - Detailed SQL commands
   - Verification steps
   - Rollback procedures
   - Troubleshooting

4. **SQL_PYTHON_VALIDATION_SUMMARY.md**
   - Executive summary
   - Decision tree
   - Testing procedures
   - Timelines

5. **This File**: QUICK_IMPLEMENTATION_GUIDE.md
   - TL;DR version
   - Fast reference
   - Step-by-step procedures

---

## ⚡ I Just Want It Done

**Fastest path (3 minutes)**:

1. **For new database**:
   ```bash
   psql -U postgres -f PostgressScript/001_init_schema_COMPATIBLE.sql
   cd ingestion
   python main.py --skip-equity --skip-fo
   ```

2. **For existing database**:
   ```bash
   # Backup
   pg_dump StockAnalysis_Bhavcopy > backup.sql
   
   # Get Option 1 migration from MIGRATION_GUIDE.md and run it
   
   # Test
   cd ingestion
   python main.py --skip-equity --skip-fo
   ```

---

## 🆘 Troubleshooting

**Error: "column ... does not exist"**
→ Run the appropriate fix option above

**Error: "SERIES column does not exist"**
→ Must use Option 1 (SQL) or add column manually

**Test ingestion fails**
→ Check logs: `tail -f ingestion/logs/ingestion.log`

**Data seems missing after migration**
→ Column names changed but data is there - verify with queries in VERIFICATION COMMANDS section above

---

## ✨ Summary

| What | Status | Action |
|------|--------|--------|
| **SQL vs Python compatibility** | ❌ Incompatible | Choose Option 1, 2, or 3 above |
| **Documentation provided** | ✅ Complete | Read SQL_COMPATIBILITY_REPORT.md |
| **Fix scripts ready** | ✅ Available | See 001_init_schema_COMPATIBLE.sql |
| **Migration guide** | ✅ Available | See MIGRATION_GUIDE.md |
| **Time to fix** | ⏱️ 5-10 min | Choose and implement above |

🎯 **Next Step**: Pick an option and execute it. You'll have working database in 5 minutes!

