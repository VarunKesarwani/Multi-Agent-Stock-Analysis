# Financial-document RAG application

Modular ingestion, Qdrant retrieval and grounded answers, following the supplied
RAG project diagram. See [STRUCTURE.md](STRUCTURE.md) for the exact module mapping,
compatibility details and limitations.

## Quick start (PowerShell, Python 3.12+)

Run from the repository root:

```powershell
cd Ingestion_AnnualReport
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit document directories and model/database settings in .env.
ollama pull nomic-embed-text
ollama pull llama3.2:3b
```

Start your existing Qdrant server at `http://localhost:6333` and Ollama at
`http://localhost:11434`. If Qdrant is not installed, a local persistent instance
can be started with:

```powershell
docker run -d --name rag-qdrant -p 127.0.0.1:6333:6333 -v rag_qdrant_data:/qdrant/storage qdrant/qdrant:v1.15.5
```

Use your existing Qdrant instance if it already contains indexed reports. Do not
start a second instance on the same port. Linux/macOS: activate with
`source .venv/bin/activate` and copy with `cp .env.example .env`.

```powershell
# Convert annual PDFs using the existing symbol/year folder workflow:
python pdf_process.py
# Intentionally rerun conversion even when a valid output is already recorded:
python pdf_process.py --force
# Ingest annual Markdown and educational PDFs into the configured collection:
python main.py ingest --type all
# Or use --type annual / --type education.
python main.py search "What drives operating cash flow?" --symbol TCS --year 2025
python main.py ask "How does cash flow differ from profit?" --document-type financial_education
python main.py serve
```

The interactive API docs are at `http://127.0.0.1:8000/docs`.

```powershell
$body = @{ query = "Explain operating cash flow"; document_type = "financial_education"; limit = 5 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/search -ContentType application/json -Body $body
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/ask -ContentType application/json -Body $body
```

`/search` returns passages, scores, metadata and citations without invoking the
answer model. `/ask` returns an answer and its source excerpts. Optional filters:
`document_type`, `symbol`, `year`, `topic`, `min_score`; `limit` is between 1 and 20.

## Configuration

Precedence is **process environment > .env > config.yaml > code defaults**.
By default both files resolve beside `main.py`, independent of working directory.
Use `python main.py --env C:/path/to/.env ingest --type education` for another
configuration root. `RAG_CONFIG_FILE` selects another YAML file; relative settings
paths resolve against the chosen `.env` directory. YAML uses the same flat uppercase
keys as `.env` and must contain only scalar values. Keep credentials in `.env` or
process environment, not YAML.

Embeddings and answer generation are independent:

| Purpose | Variables | Default |
| --- | --- | --- |
| Embedding provider/model | `EMBEDDING_TYPE`, `EMBEDDING_MODEL` | `ollama`, `nomic-embed-text` |
| Answer provider/model | `LLM_PROVIDER`, `LLM_MODEL` | `ollama`, `llama3.2:3b` |
| OpenAI access | `OPENAI_API_KEY`, `OPENAI_BASE_URL` | Empty key; official API URL |
| Vector storage | `QDRANT_URL`, `QDRANT_COLLECTION`, `QDRANT_API_KEY` | Local Qdrant, `annual_reports` |
| Chunking | `CHUNK_SIZE_CHARS`, `CHUNK_OVERLAP_CHARS` | 4000 / 400 characters |
| Retrieval | `RAG_TOP_K`, `RAG_CONTEXT_CHARS` | 5 passages / 16000 context characters |
| Answer bounds | `LLM_TIMEOUT_SECONDS`, `LLM_MAX_TOKENS` | 120 seconds / 1024 output tokens |
| Logging | `LOG_FILE` | `logs/app.log`, rotating at 5 MB |

For OpenAI answers set `LLM_PROVIDER=openai`, `LLM_MODEL=gpt-4o-mini` and
`OPENAI_API_KEY`. For OpenAI embeddings also set `EMBEDDING_TYPE=openai` and
`EMBEDDING_MODEL=text-embedding-3-small`. Always set the corresponding model when
switching providers. An embedding model change requires a new collection and
re-ingestion; changing only the answer model does not.

## Tests

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests use generated PDFs, in-memory Qdrant and simulated provider HTTP responses.
They do not require local models, a live database or API credits. Legacy exploratory
notebook dependencies are available separately in `requirements-notebooks.txt`.

## Existing ingestion reference

# Annual-report and financial-education ingestion

Use the same Qdrant collection and embedding model for company reports and educational material. Education is labelled `document_type=financial_education`; annual Markdown retains its existing labels such as `Annual Report`, `Quarterly Report`, and `HalfYearly Report` for compatibility with the existing MCP reader.

## Configure

From `Ingestion_AnnualReport`:

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

On Linux/macOS use `cp .env.example .env`. Edit `.env`; it is already ignored by the repository. Never commit API keys. The template includes:

- `ANNUAL_PDF_DIR`, `EDUCATIONAL_PDF_DIR`, `MARKDOWN_DIR`, `SYMBOLS_CSV`, summary/failure paths.
- `EMBEDDING_TYPE=ollama` (default) or `openai`, `EMBEDDING_MODEL`, service URLs and OpenAI key.
- `CHUNK_SIZE_CHARS`, `CHUNK_OVERLAP_CHARS`, batch size, attempts and timeouts.
- `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION`, lookup size and resume controls.

Relative paths resolve against the `.env` directory, independent of the notebook working directory. Absolute Windows paths should use forward slashes, e.g. `C:/Repo/RAG_Fin_Learning/Education`. Process environment values override `.env`. Restart notebook kernels after editing configuration or updating scripts. Provider secrets are excluded from the config representation.

For OpenAI set `EMBEDDING_TYPE=openai`, `EMBEDDING_MODEL=text-embedding-3-small`, and `OPENAI_API_KEY`. This sends document text to OpenAI. Ollama remains entirely local when its URL points to localhost. Set up/pull the chosen Ollama embedding model before running.

## Run

Annual PDF layout stays `<ANNUAL_PDF_DIR>/<SYMBOL>/<YEAR>/*.pdf`, with symbols from `SYMBOLS_CSV`:

```powershell
# Existing conversion, now configured by .env:
python pdf_process.py
# Embed converted annual-report Markdown:
python document_ingestion.py --type annual
# Extract, chunk and embed educational PDFs directly:
python document_ingestion.py --type education
# Process both sources (annual Markdown must already exist):
python document_ingestion.py --type all
# Optional alternative configuration file for chunk/embedding stage:
python document_ingestion.py --type education --env C:/config/financial-rag.env
```

`pdf_to_markdown.ipynb` now calls the shared PDF converter. `chunk_and_embedding.ipynb` calls the shared ingestion runner, with `kind="annual"`, `"education"` or `"all"`. Run notebooks from the project directory or repository root. The separate annual-report download notebook is unchanged.

Education PDFs are discovered recursively, including `.PDF` extensions; no company symbol CSV is needed for education-only runs. For each PDF you can add an adjacent sidecar, e.g. `cash_flow.pdf` and `cash_flow.metadata.json`:

```json
{
  "source": "Zerodha Varsity",
  "topic": "fundamental_analysis",
  "title": "Cash Flow Statement",
  "chapter": "Cash Flow Statement",
  "publication_date": "2025-01-01",
  "source_url": "https://example.com/original-document"
}
```

These are example metadata values; enter the real publication date and URL or omit them. Allowed sidecar fields are the six fields shown, all strings. Source/topic default to `.env`; title defaults to the filename. Education never receives a fabricated company symbol/year. Page numbers are one-based PDF pages, not necessarily the printed page labels. Existing annual Markdown does not gain invented page numbers.

The parser retains headings and keeps Markdown tables in separate blocks. Blocks are split with configured character overlap and a hard size limit. Oversized tables may span chunks; this is not a specialized financial-table reconstruction algorithm. Educational content does not use company-specific navigation filters. Empty/unreadable PDFs are reported as failed; scanned PDFs may need OCR before ingestion.

## Existing collection and reruns

### PDF-to-Markdown duplicate checks

`python pdf_process.py` skips successfully converted PDFs by default, before
calling either parser. It compares the full SHA-256 of PDF bytes within the same
company symbol, year and classified report period. A renamed copy with the same
content and context reuses the original Markdown output; it does not create a
second Markdown file. A rename that changes the classified period is processed
separately so report metadata remains correct.

Completion records are stored in `MARKDOWN_DIR/.pdf_conversion_cache/`. Each
record includes the full PDF hash, output filename and Markdown hash. A skip
requires an existing, nonempty output whose hash still matches. Changed PDFs,
missing/empty/modified outputs, invalid records and failed conversions are retried.
Markdown and completion records are written atomically. Threaded workers in one
process serialize matching documents; separate simultaneous script processes are
not coordinated, so run one converter process per output directory.

Existing Markdown without a completion record is converted once to establish
verified state. Keep the cache directory with the Markdown files between runs.
Skipped rows appear in the summary CSV with `skip_reason=duplicate_pdf` and the
reused `output_file`. Renamed duplicates retain the first output's source metadata.
Use `python pdf_process.py --force`, or `pdf_process.main(force=True)` in a notebook,
to bypass this check after parser upgrades or when conversion is intentionally
required. This control is independent of the embedding-stage `SKIP_EXISTING` flag.
Changed documents still leave previous Markdown/Qdrant versions in place; this
check does not delete historical outputs or vectors.

### Embedding reruns

Each newly written point records document identity, source path/file, document type, headings, embedding provider/model, and chunk configuration. Education also records source/topic and page number. IDs are deterministic per document/chunk/text; adding another PDF does not renumber existing documents. The pipeline processes one document at a time, resumes existing matching IDs, isolates embedding failures, and reports file/chunk failures at the end. Extraction failures do not stop the remaining files. A collection/model incompatibility stops the run so you can correct configuration. CLI exits nonzero after any document failure.

**Do not mix embedding models in one collection, even if their dimensions match.** New writes check model/provider labels, vector dimensions, unnamed-vector configuration and cosine distance. The guard does not delete/recreate a collection. To change models, use a new collection and configure the retrieval client with the same model.

Old points written by the previous notebook do not identify their embedding model. With an existing collection the default guard will reject these unknown vectors. If you have confirmed they were embedded using exactly your configured provider/model (the former notebook defaults were Ollama `nomic-embed-text`), set `ALLOW_LEGACY_EMBEDDINGS=true`. This accepts unlabelled legacy points but still rejects explicitly labelled model mismatches. For a fresh collection keep it false.

To **add only education** to your existing report collection, use `--type education` after confirming the legacy model. The updated annual chunker uses per-document IDs and heading boundaries: rerunning annual reports from the old notebook into the old collection may leave duplicate old/new chunks. For a full annual reindex, use a new collection, verify it, then point retrieval at it; this code does not delete your old points. Likewise changing a PDF's content, relative location or chunk settings creates new IDs and does not remove superseded points. Deleted input files are not automatically removed from Qdrant. Metadata-only edits are skipped with `SKIP_EXISTING=true`; use false to refresh matching points.

## Retrieval

The shared pipeline exposes a filtered query:

```python
from chunk_embedding_pipeline import AnnualReportEmbeddingPipeline, PipelineConfig
pipeline = AnnualReportEmbeddingPipeline(PipelineConfig.from_env())
try:
    results = pipeline.query("Explain operating cash flow", document_type="financial_education")
finally:
    pipeline.close()
```

The separate `annualreport_rag_mcp_python` service currently requires a company symbol and uses Ollama. Its contract is unchanged in this ingestion PR: education-wide MCP search and OpenAI query embeddings would require a subsequent reader change. Keep its model/collection aligned for company-report searches. Education queries can use the filtered pipeline method above today.

## Tests

```powershell
python -m pip install pytest
python -m pytest -q
```

Tests cover config, real PDF extraction/page metadata, headings/tables, per-file failure continuation, ID isolation, Qdrant local-mode writes/resume/filtering, embedding model/dimension guards and mocked OpenAI responses. No live embedding service is required.

