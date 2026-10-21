# Kafka UI for local news validation

Kafbat UI is available at http://localhost:8084. It uses the internal Kafka listener (kafka:9092) and the Connect REST endpoint (http://connect:8083).

From Ingestion_News, start the UI and Connect:
```powershell
docker compose up -d kafka-ui connect
docker compose logs -f kafka-ui
```

Kafka and Elasticsearch start as dependencies. The UI only waits for Kafka, so Kafka inspection remains available even if Connect is unavailable. Connector inspection needs a running Connect service and registered connectors.

In the news-local cluster:
- Topics: inspect news_* raw topics and news_enriched_* outputs, partitions and messages.
- Messages: inspect enrichment_status and analysis in enriched JSON events.
- Consumer Groups: inspect news-enrichment-v1 (or your configured group) and its lag.
- Topics: inspect news_enrichment_failed for failed articles.
- Kafka Connect: inspect connector status and task errors.

Optional Compose .env settings:
```dotenv
KAFBAT_UI_PORT=8084
# Default image tag is latest; set a published release tag to pin your installation.
KAFBAT_UI_VERSION=latest
```

Port 8084 avoids the agent API at 8080 and Connect at 8083. The UI is bound to localhost and uses the existing local plaintext Kafka configuration.

An empty topic or missing topic does not alone prove ingestion failure: valid RSS feeds can contain zero entries. Compare producer and consumer logs with topic messages and consumer lag.
