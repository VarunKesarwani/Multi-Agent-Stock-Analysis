# News ingestion: local services

The local Compose stack provides Kafka, the one-shot RSS producer, and
Elasticsearch. Run these commands from `Ingestion_News`.

## Run the producer from Windows

```powershell
docker compose up -d kafka elasticsearch
Test-NetConnection 127.0.0.1 -Port 29092
$env:KAFKA_BOOTSTRAP_SERVERS = "127.0.0.1:29092"
python .\news_producer.py
```

Kafka publishes `127.0.0.1:29092` to the Windows host. If you run the
producer from a notebook, set `KAFKA_BOOTSTRAP_SERVERS=127.0.0.1:29092`
in its environment before creating `NewsKafkaProducer`.

## Run the producer inside Docker

```powershell
docker compose up -d kafka elasticsearch
docker compose run --rm --build news-producer
```

The Docker producer connects to the Kafka service at `kafka:9092`.
It fetches feeds once, publishes messages, flushes, and exits. Kafka and
Elasticsearch data persist in named volumes across container restarts.

The producer sends raw events to `news_<category>` topics. Multiword categories
use underscores, such as `news_annual_reports` and `news_board_meetings`.
If the consumer is started before a category has produced any records, it waits
for that topic rather than stopping. The enrichment
consumer must run to produce enriched events, and the Kafka Connect sink must be
registered before those events appear in Elasticsearch. The Compose stack now
includes a Connect worker and its Elasticsearch sink plugin.
See [ELASTICSEARCH_SINK.md](ELASTICSEARCH_SINK.md) for the index template and
sink registration.

## Run the enrichment consumer on Windows

Install its dependencies and put local settings in `Ingestion_News/.env`:

```dotenv
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5-coder:7b
KAFKA_BOOTSTRAP_SERVERS=127.0.0.1:29092
```

The consumer loads this file from its own directory, regardless of the shell's
working directory. An existing PowerShell environment variable takes precedence;
check `$env:OLLAMA_MODEL` if the logged model differs from the file. Without a
configured `OLLAMA_MODEL`, the default is `qwen2.5-coder:7b`.

```powershell
python -m pip install -r .\requirements.txt
ollama run qwen2.5-coder:7b "Reply OK"
python .\news_enrichment_consumer.py
```

If earlier messages were published with `enrichment_status=FAILED`, the consumer
already committed their source offsets. Once the model works, stop the consumer
and use a new group to replay raw news (including messages already processed):

```powershell
$env:NEWS_ENRICHMENT_GROUP_ID = "news-enrichment-qwen-replay-v1"
$env:KAFKA_AUTO_OFFSET_RESET = "earliest"
python .\news_enrichment_consumer.py
```

The replay analyzes every retained raw message in the subscribed topics and
publishes new enriched records. Keep the new group ID for subsequent runs so
processing resumes from its committed offsets.

## Use OpenAI for news enrichment

Create an OpenAI API key in the OpenAI Platform and place it only in the local
`Ingestion_News/.env` (ignored by Git). API billing is separate from ChatGPT.
The consumer sends each article's title and RSS summary to the selected model.

```dotenv
NEWS_LLM_PROVIDER=openai
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4.1-mini
KAFKA_BOOTSTRAP_SERVERS=127.0.0.1:29092
```

`OLLAMA_HOST` and `OLLAMA_MODEL` are unused while OpenAI is selected. PowerShell
environment variables override values in `.env`; check
`$env:NEWS_LLM_PROVIDER` and `$env:OPENAI_MODEL` if startup logs differ.
The default provider remains `ollama` when `NEWS_LLM_PROVIDER` is absent.

After `git pull`, run from `Ingestion_News`:

```powershell
python -m pip install -r .\requirements.txt
python -c "from news_enrichment_consumer import NewsAnalyzer; print(NewsAnalyzer().analyze('Example company posts earnings', 'Revenue increased this quarter.'))"
```

The one-article check calls the API once and does not consume Kafka messages.
Once it succeeds, replay previously failed messages using a fresh consumer group:

```powershell
$env:NEWS_ENRICHMENT_GROUP_ID = "news-enrichment-openai-v1"
$env:KAFKA_AUTO_OFFSET_RESET = "earliest"
python .\news_enrichment_consumer.py
```

This reprocesses every retained raw message in the subscribed topics and incurs
API usage for each. Keep the new group ID for subsequent runs. To process only
new messages, leave the existing group ID unchanged instead of setting a new one.

If OpenAI returns `credit_balance_exhausted` or a hard usage/spend limit,
restore API access before running the consumer. The consumer stops on these
errors without committing the current raw Kafka offset, so restarting after
access is restored retries that article. The same applies to invalid API
credentials. Ordinary request-rate limits remain eligible for retries.

## Select the LLM provider

Copy `.env.example` to `.env` (or copy its settings into your existing file).
Set `NEWS_LLM_PROVIDER` to one of:

| Value | Model setting | API key setting |
| --- | --- | --- |
| `ollama` (default) | `OLLAMA_MODEL` | None |
| `openai` | `OPENAI_MODEL` | `OPENAI_API_KEY` |
| `gemini` | `GEMINI_MODEL` | `GEMINI_API_KEY` |
| `sarvam` | `SARVAM_MODEL` | `SARVAM_API_KEY` |

Only the selected provider's key is required. Keep real keys in the ignored
`.env` file; the example contains empty placeholders. Restart the consumer
after changing settings. Existing shell environment variables still take precedence.

With no provider setting, Ollama runs at `http://127.0.0.1:11434` by default.
The configured local model must already be installed. Unknown or empty provider
values fail at startup. There is no automatic switch to another provider after
a request fails.

For example, select Gemini with `NEWS_LLM_PROVIDER=gemini` and set
`GEMINI_API_KEY`; select Sarvam with `NEWS_LLM_PROVIDER=sarvam` and set
`SARVAM_API_KEY`. Models can be changed independently using the table above.
Cloud providers receive the article title and RSS summary.

Gemini and Sarvam use the existing OpenAI SDK's compatible Chat Completions
client, JSON mode, and local Pydantic validation. OpenAI keeps its Responses
API structured parsing; Ollama keeps its native schema format. All providers
return the same `NewsAnalysis` fields. Invalid or incomplete output follows
the existing retry and failed-event path. Cloud authentication/permission
errors pause consumption without committing the current offset; ordinary
rate-limit errors retry. Known hard quota errors also pause consumption.

API references:
- [Gemini OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai)
- [Sarvam chat completion](https://docs.sarvam.ai/api/api-guides-tutorials/chat-completion/overview)

Run the offline provider tests from `Ingestion_News`:
`python -m unittest discover -s tests -p "test_llm_providers.py"`.
