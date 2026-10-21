> Validation update: read [VALIDATION_REVIEW.md](../Doc/PriceDataIngestion/VALIDATION_REVIEW.md) before running. Existing SQL variants conflict with the documented schema; the review explains compatibility, setup, fixes, and validation limits. Both market skip flags now address one Screener stage. Database credentials must come from the environment or `--db-url`.

# NSE Bhavcopy Ingestion System

A comprehensive Python-based system for downloading, transforming, and ingesting NSE Bhavcopy (market data) into PostgreSQL.

## Features

- **Company Master Ingestion**: Downloads and maintains NSE company master data
- **Equity Bhavcopy**: Downloads and ingests equity market data with multiple fallback sources
- **F&O Bhavcopy**: Downloads and ingests futures & options data
- **Schema Normalization**: Transforms multiple source formats to canonical schema
- **Error Handling**: Robust error handling with graceful fallback and logging
- **Historical Backfill**: Supports full historical data ingestion from 2006

## Project Structure

```
ingestion/
├── config.py                      # Configuration and constants
├── utils.py                       # Utility functions (URL handling, date generation, parsing)
├── transformers.py                # Data transformation logic
├── db_loader.py                   # Database operations and management
├── company_master_ingestion.py    # Company master workflow
├── equity_ingestion.py            # Equity data workflow
├── fo_ingestion.py                # F&O data workflow
├── main.py                        # Main entry point
├── requirements.txt               # Python dependencies
├── logs/                          # Ingestion logs (auto-created)
├── temp/                          # Temporary files (auto-created)
└── README.md                      # This file
```

## Installation

### Prerequisites

- Python 3.9+
- PostgreSQL database
- Pandas, SQLAlchemy, requests

### Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set `POSTGRES_CONNECTION_STRING` to your PostgreSQL instance. For the
   local Compose database, follow the commands in the next section.

3. Apply the appropriate table and hypertable schema SQL before ingestion.

## Local TimescaleDB with Docker Compose

From `Ingestion_Price` in PowerShell:

```powershell
Copy-Item .env.example .env
# Edit .env and replace POSTGRES_PASSWORD with a private password.
docker compose up -d timescaledb
docker compose ps
docker compose exec timescaledb psql -U postgres -d StockAnalysis_Bhavcopy -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
```

The database runs PostgreSQL 16 with TimescaleDB 2.23.1 and is reachable from
Windows at `127.0.0.1:6543`. Override `POSTGRES_PORT` in `.env` if that port
is already in use. The Compose volume retains database data when the container
is restarted or recreated. An existing database outside this Compose project
is **not** imported into this new volume.

Run the ingestion application on Windows with `POSTGRES_CONNECTION_STRING`
pointing to that host port:

```powershell
$env:POSTGRES_CONNECTION_STRING = "postgresql+psycopg2://postgres:<URL-encoded-password>@127.0.0.1:6543/StockAnalysis_Bhavcopy"
python .\main.py
```

Replace the placeholder with the password from `.env`, URL-encoding reserved
characters (for example, `#` becomes `%23`). Quote a password containing `#`
in `.env`, such as `POSTGRES_PASSWORD='example#value'`. The Compose `.env` configures
the database container; it does not automatically set the Python process's
`POSTGRES_CONNECTION_STRING`.

This starts an empty database with the TimescaleDB extension. It does not run
the repository's table or hypertable scripts. Apply the appropriate SQL under
`../PostgressScript/` separately before ingestion.

## Usage

### Basic Usage

Run the complete ingestion pipeline:

```bash
python main.py
```

### With Custom Date Range

```bash
python main.py --start-date 2023-01-01 --end-date 2023-12-31
```

### Skip Steps

Skip specific ingestion steps:

```bash
# Skip company master ingestion
python main.py --skip-company-master

# Skip equity ingestion
python main.py --skip-equity

# Skip F&O ingestion
python main.py --skip-fo
```

### Custom F&O Date Range

F&O uses current year by default. Override with:

```bash
python main.py --fo-start-date 2023-01-01 --fo-end-date 2023-12-31
```

### Custom Database URL

```bash
python main.py --db-url "postgresql+psycopg2://user:pass@host:5432/db"
```

### Combined Example

```bash
python main.py \
  --start-date 2023-01-01 \
  --end-date 2023-12-31 \
  --skip-company-master \
  --fo-start-date 2023-06-01 \
  --fo-end-date 2023-06-30
```

## Module Descriptions

### config.py
- Database connection strings
- NSE source URLs (equity and F&O)
- Canonical schema definitions
- Column mapping configurations
- Request headers and timeouts

### utils.py
- `normalize_url()`: Clean URL strings
- `resolve_url()`: Replace date placeholders
- `generate_trading_dates()`: Create date list skipping weekends
- `download_payload()`: HTTP GET with error handling
- `parse_payload_to_dataframe()`: Handle CSV and ZIP+CSV
- `setup_session()`: Initialize NSE-compatible session
- `calculate_avg_price()`: Safe division with null handling

### transformers.py
- `transform_equity()`: Normalize equity data to canonical schema
- `transform_fo()`: Normalize F&O data to canonical schema
- `transform_company_master()`: Process company master data
- Handles Source 1, 2, and 3 with different column mappings

### db_loader.py
- `DatabaseManager`: Main database class
  - Connection management
  - DataFrame loading
  - Upsert operations for company master
  - Last ingestion date tracking
- `create_database_manager()`: Factory function

### company_master_ingestion.py
- `download_company_master()`: Download EQUITY_L.csv from NSE
- `ingest_company_master()`: Complete workflow
- Must run before equity/F&O to ensure symbols exist

### equity_ingestion.py
- `ingest_equity()`: Main equity workflow
- Tries 3 sources in priority order
- Skips weekends automatically
- Returns list of failed dates

### fo_ingestion.py
- `ingest_fo()`: Main F&O workflow
- Uses current year by default (Jan 1 to today)
- Can override with custom date range
- Returns total rows ingested

### main.py
- Entry point for complete pipeline
- Orchestrates all three ingestion workflows
- Command-line argument parsing
- Logging configuration
- Error handling and reporting

## Data Schemas

### Canonical Equity Schema
```
SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE,
LAST_PRICE, CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS,
NO_OF_TRADES, DELIV_QTY, DELIV_PER
```

### Canonical F&O Schema
```
DATE1, SEGMENT, SYMBOL, EXPIRY_DATE, INSTRUMENT_NUMBER, OPEN_PRICE,
HIGH_PRICE, LOW_PRICE, CLOSE_PRICE, LAST_PRICE, PREV_CLOSE,
UNDERLYING_PRICE, SETTLEMENT_PRICE, OPEN_INTEREST,
CHANGE_IN_OPEN_INTEREST, TTL_TRD_QNTY, TURNOVER_LACS
```

### Company Master Schema
```
SYMBOL, NAME_OF_COMPANY, SERIES, ISIN NUMBER
```

## Execution Flow

1. **Setup**: Initialize logging, create database connection, setup requests session
2. **Company Master**: Download and upsert company master data
3. **Equity**: For each trading date:
   - Try Source 1 (Full Bhavcopy)
   - If fails, try Source 2 (CM - Bhavcopy)
   - If fails, try Source 3 (CM-UDiFF)
   - If all fail, mark as holiday and continue
4. **F&O**: For each trading date (current year):
   - Download and parse F&O data
   - Transform and load to database
5. **Cleanup**: Close database connection, finalize logs

## Logging

Logs are written to `logs/ingestion.log` with rotating file handler (10 MB max, 5 backups).

Log levels:
- `INFO`: Major workflow steps, row counts
- `WARNING`: Failed sources, missing data
- `ERROR`: Exceptions and fatal failures
- `DEBUG`: Detailed parsing and transformation info

## Error Handling

- **Download failures**: Logged with HTTP status, attempts next source
- **Parsing failures**: Caught, logged, continues with next date
- **Database errors**: Caught, logged, does not stop execution
- **Holidays**: Dates with all sources failing are logged separately
- **Connection issues**: Graceful reconnection with logging

## Performance Considerations

- Bulk inserts: Uses `chunksize=1000` for large datasets
- Session persistence: Reuses HTTP session for multiple requests
- Database pooling: SQLAlchemy manages connection pool
- Weekend skipping: Reduces API calls by ~30%

## Source Priority (Equity)

1. **Full Bhavcopy and Security Deliverable data**: Most comprehensive
2. **CM - Bhavcopy**: Common fallback
3. **CM-UDiFF Common Bhavcopy**: Last resort

## Testing

Run individual modules:

```bash
# Test company master
python company_master_ingestion.py

# Test equity ingestion
python equity_ingestion.py

# Test F&O ingestion
python fo_ingestion.py
```

## Troubleshooting

### Database Connection Error
- Check `POSTGRES_CONNECTION_STRING` environment variable
- Verify PostgreSQL is running
- Check credentials and network access

### NSE API Errors
- Check internet connectivity
- Verify NSE URLs are accessible
- Check for IP-based rate limiting
- Add delays between requests if needed

### Memory Issues
- Reduce date range (e.g., month by month)
- Use `--skip-company-master` if already ingested
- Monitor system resources

### Missing Data
- Check `logs/ingestion.log` for details
- Verify date range includes trading days
- Check if dates are holidays

## Database Schema Creation

Ensure tables exist before running (example SQL):

```sql
CREATE TABLE IF NOT EXISTS company_master (
    SYMBOL VARCHAR(20) PRIMARY KEY,
    "NAME_OF_COMPANY" VARCHAR(255),
    SERIES VARCHAR(10),
    "ISIN NUMBER" VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS equity_bhavcopy (
    id SERIAL PRIMARY KEY,
    SYMBOL VARCHAR(20),
    SERIES VARCHAR(10),
    DATE1 DATE,
    PREV_CLOSE DECIMAL(10,2),
    OPEN_PRICE DECIMAL(10,2),
    HIGH_PRICE DECIMAL(10,2),
    LOW_PRICE DECIMAL(10,2),
    LAST_PRICE DECIMAL(10,2),
    CLOSE_PRICE DECIMAL(10,2),
    AVG_PRICE DECIMAL(10,2),
    TTL_TRD_QNTY BIGINT,
    TURNOVER_LACS DECIMAL(15,2),
    NO_OF_TRADES INTEGER,
    DELIV_QTY BIGINT,
    DELIV_PER DECIMAL(5,2)
);

CREATE TABLE IF NOT EXISTS fo_bhavcopy (
    id SERIAL PRIMARY KEY,
    DATE1 DATE,
    SEGMENT VARCHAR(10),
    SYMBOL VARCHAR(20),
    EXPIRY_DATE DATE,
    INSTRUMENT_NUMBER VARCHAR(50),
    OPEN_PRICE DECIMAL(10,2),
    HIGH_PRICE DECIMAL(10,2),
    LOW_PRICE DECIMAL(10,2),
    CLOSE_PRICE DECIMAL(10,2),
    LAST_PRICE DECIMAL(10,2),
    PREV_CLOSE DECIMAL(10,2),
    UNDERLYING_PRICE DECIMAL(10,2),
    SETTLEMENT_PRICE DECIMAL(10,2),
    OPEN_INTEREST BIGINT,
    CHANGE_IN_OPEN_INTEREST BIGINT,
    TTL_TRD_QNTY BIGINT,
    TURNOVER_LACS DECIMAL(15,2)
);
```

## References

- [NSE Bhavcopy Documentation](https://www.nseindia.com)
- [INGESTION_FLOW.md](../Doc/INGESTION_FLOW_UPDATED.md)
- [Database Schema](../Doc/PriceDataIngestion/DB_SCHEMA_UPDATED.md)

## License

Internal use only for StockAnalysis_AI project

