# RSS request timeouts

The producer downloads RSS/Atom XML before parsing it. Each network operation has a socket timeout, so an unresponsive feed logs an error and the producer continues with the next feed. This timeout is not a strict total wall-clock deadline for the whole download.

Set this optional value in Ingestion_News/.env:

```dotenv
NEWS_RSS_TIMEOUT_SECONDS=30
```

The default is 30 seconds. Values must be finite and greater than zero. Existing process environment variables take precedence over .env.

Successful fetches log the HTTP status, elapsed seconds, byte count, and entry count. Empty valid feeds are logged explicitly and publish no messages. HTML/block pages are rejected rather than treated as empty feeds. Malformed RSS with recognizable feed format continues through the existing warning and entry-processing path.

No browser session or additional dependency is required. Run the producer as before:

```powershell
python .\news_producer.py
```
