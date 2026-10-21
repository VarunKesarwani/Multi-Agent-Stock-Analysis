`psql -U postgres -f PostgressScript/001_create_schema_merged.sql`
# Time: 2 minutes
`psql -U postgres -d StockAnalysis_Bhavcopy -f PostgressScript/002_migrate_schema_merged.sql`
docker run -p 6333:6333 -p 6334:6334 -v qdrant_storage:/qdrant/storage qdrant/qdrant

docker run -d -p 8000:8000 chromadb/chroma

docker run -d --name timescaledb -p 6543:5432 -e POSTGRES_PASSWORD=H#mmingB1rd timescale/timescaledb-ha:pg18

# run migration script to migrate schema to compatible
psql -U postgres -d StockAnalysis_Bhavcopy -f PostgressScript/002_migrate_schema_merged.sql

#validation of schema migration

