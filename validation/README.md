# Ingestion validation

Read-only checks for PostgreSQL/TimescaleDB, MongoDB and Elasticsearch.
These scripts report findings; they do not repair data or produce an automated
pass/fail exit code. Qdrant is outside this set.

| File | Run in | Coverage |
| --- | --- | --- |
| [postgresql.sql](postgresql.sql) | psql, pgAdmin or DBeaver | Four price/master tables; counts, dates, duplicates, prices and freshness |
| [mongodb.js](mongodb.js) | mongosh | Financial collections; datasets, facts, types, dates and ingestion status |
| [elasticsearch.http](elasticsearch.http) | Kibana Dev Tools Console | News indices; counts, dates, missing fields, enrichment failures and repeated IDs |

## PostgreSQL

Connect to `StockAnalysis_Bhavcopy`. From the repository root:

```powershell
psql -h localhost -p 5432 -U postgres -d StockAnalysis_Bhavcopy -v ON_ERROR_STOP=1 -f validation/postgresql.sql
```

Alternatively open the SQL file in pgAdmin/DBeaver. It uses a read-only
transaction and Indian time for calendar-day checks. If a statement errors in
an interactive session, issue `ROLLBACK;` before retrying.

Edit the missing-date window (initially 2026-03-30 through 2026-09-30).
Weekdays without data are candidates only: account for exchange holidays and
special weekend sessions. F&O zero prices and missing market rows outside your
configured company universe may be legitimate. The freshness threshold is seven days.

## MongoDB

From the repository root:

```powershell
mongosh "mongodb://localhost:27017" --file validation/mongodb.js
```

Use your normal authenticated connection if applicable. The script selects
`financial_ingestion`; change `databaseName` if needed. It prints each cursor
explicitly for noninteractive runs. The current-facts view check is skipped
when the view has not been installed. Change the example symbol `TCS` as needed.

Duplicate checks are scoped to a dataset. Historical versions and comparative
facts in overlapping XBRL filings are not automatically duplicate errors.
Reporting dates and ingestion timestamps measure different kinds of freshness.
The stuck-processing review threshold is one hour.

## Elasticsearch

Paste `elasticsearch.http` into Kibana > Dev Tools > Console and execute
individual requests. This is Kibana Console syntax, not a shell script or a
generic HTTP-client file. Adjust `news-enriched-*` if your configured index
pattern differs. The daily histogram initially covers September 2026 in Indian time.

The duplicate aggregation is a bounded diagnostic sample, not an exhaustive
audit. The same news ID in different category indices can be intentional.
Missing-field checks detect missing/null indexed values, not all blank strings.
If no matching index exists, requests can return index-not-found until the
first article is indexed.

## Schema references and verification

Queries follow:
- `Ingestion_Price/PostgressScript/001_create_schema_merged.sql`
- `financial_ingestion/mongodb_financial_setup.js`
- `Ingestion_News/elasticsearch/news-enriched-index-template.json`

Actual deployed schemas may differ; inspect them if a field/table is missing.
Counts and grouped audits can scan substantial data; run individual sections
or narrow the date range when necessary. Review findings before treating them
as ingestion failures. These scripts have not been executed against live databases.
