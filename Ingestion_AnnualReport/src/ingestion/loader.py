"""Chunk annual-report Markdown and educational PDFs for the shared embedding pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
from pathlib import Path

import yaml

from src.chunking.chunker import chunk_markdown
from src.ingestion.pipeline import AnnualReportEmbeddingPipeline, PipelineConfig
from src.utils.settings import DocumentSettings

LOG = logging.getLogger(__name__)


def education_chunks(
    path: Path, root: Path, settings: DocumentSettings, config: PipelineConfig
) -> list[dict]:
    """Extract page-level educational Markdown and optional adjacent JSON metadata."""
    import pymupdf4llm

    path = Path(path)
    sidecar = path.with_suffix(".metadata.json")
    details = (
        json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else {}
    )
    allowed = {"source", "topic", "title", "chapter", "publication_date", "source_url"}
    if not isinstance(details, dict) or set(details) - allowed:
        raise ValueError(f"Invalid education metadata keys in {sidecar}")
    if any(not isinstance(value, str) for value in details.values()):
        raise ValueError(f"Education metadata values must be strings: {sidecar}")
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    # Include relative source and bytes: same-named files in different folders cannot collide.
    content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    identity = hashlib.sha256(
        f"financial_education:{relative}:{content_hash}".encode()
    ).hexdigest()
    metadata = {
        "document_type": "financial_education",
        "document_id": identity,
        "source_file": path.name,
        "source_pdf": path.name,
        "source_path": str(path.resolve()),
        "source": settings.educational_source,
        "topic": settings.educational_topic,
        "title": path.stem,
        "content_sha256": content_hash,
        "parsed_by": "pymupdf4llm",
        **details,
    }
    pages = pymupdf4llm.to_markdown(str(path), page_chunks=True, write_images=False)
    if not isinstance(pages, list):
        raise ValueError(
            "PDF parser did not return page chunks; check pymupdf4llm version"
        )
    chunks = []
    for page in pages:
        page_metadata = page.get("metadata", {})
        page_number = page_metadata.get("page_number", page_metadata.get("page"))
        if not isinstance(page_number, int) or page_number < 1:
            raise ValueError(f"Missing PDF page number: {path}")
        chunks.extend(
            chunk_markdown(
                page.get("text", ""), {**metadata, "page_number": page_number}, config
            )
        )
    if not chunks:
        raise ValueError(
            f"No extractable text: {path}; scanned PDFs may require OCR first"
        )
    return chunks


def annual_chunks(path: Path, config: PipelineConfig) -> list[dict]:
    """Read existing YAML-frontmatter Markdown without inventing page citations."""
    content = path.read_text(encoding="utf-8-sig")
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", content, re.S)
    if not match:
        raise ValueError(f"Missing YAML frontmatter: {path}")
    metadata = yaml.safe_load(match.group(1)) or {}
    if (
        not isinstance(metadata, dict)
        or not metadata.get("symbol")
        or not metadata.get("year")
    ):
        raise ValueError(f"Annual report requires symbol/year metadata: {path}")
    # Keep existing document_type values (e.g. "Annual Report") for MCP compatibility.
    metadata.update(
        source_file=path.name,
        source_pdf=metadata.get("file_name", path.name),
        file_path=str(path.resolve()),
    )
    metadata.setdefault("document_type", "Annual Report")
    # Stable document identity isolates per-document chunk numbering from directory order.
    metadata["document_id"] = hashlib.sha256(
        f"{metadata['document_type']}:{metadata['symbol']}:{metadata['year']}:{path.name}".encode()
    ).hexdigest()
    chunks = chunk_markdown(content[match.end() :], metadata, config)
    if not chunks:
        raise ValueError(f"No extractable text: {path}")
    return chunks


def iter_documents(
    settings: DocumentSettings, config: PipelineConfig, kind: str = "all"
):
    """Yield one document at a time; log file failures and continue the run."""
    if kind not in {"annual", "education", "all"}:
        raise ValueError("kind must be annual, education, or all")
    sources = []
    if kind in {"annual", "all"}:
        sources.append((settings.markdown_dir, ".md", annual_chunks))
    if kind in {"education", "all"}:
        sources.append((settings.educational_pdf_dir, ".pdf", education_chunks))
    for root, extension, loader in sources:
        if not root.is_dir():
            LOG.error("Input directory does not exist: %s", root)
            yield str(root), None
            continue
        files = sorted(
            p for p in root.rglob("*") if p.is_file() and p.suffix.lower() == extension
        )
        if not files:
            LOG.warning("No %s files in %s", extension, root)
        for path in files:
            try:
                chunks = (
                    loader(path, config)
                    if extension == ".md"
                    else loader(path, root, settings, config)
                )
                yield str(path), chunks
            except Exception:
                LOG.exception("Failed extracting %s; continuing", path)
                yield str(path), None


def run_ingestion(kind: str = "all", env_file=None, *, pipeline=None) -> dict:
    """Run bounded-memory extraction/embedding with a summary of file failures."""
    settings = DocumentSettings.from_env(env_file)
    config = PipelineConfig.from_env(env_file)
    owned = pipeline is None
    pipeline = pipeline or AnnualReportEmbeddingPipeline(config)
    totals = dict(
        documents=0, failed_documents=0, stored=0, skipped_existing=0, failed_chunks=0
    )
    try:
        for path, chunks in iter_documents(settings, config, kind):
            totals["documents"] += 1
            if chunks is None:
                totals["failed_documents"] += 1
                continue
            try:
                summary = pipeline.run(chunks)
                totals["stored"] += summary.stored
                totals["skipped_existing"] += summary.skipped_existing
                totals["failed_chunks"] += summary.failed
                totals["failed_documents"] += int(summary.failed > 0)
            except ValueError:
                # Invalid collection/model contracts require operator correction.
                raise
            except Exception:
                LOG.exception("Failed ingesting %s; continuing", path)
                totals["failed_documents"] += 1
    finally:
        if owned:
            pipeline.close()
    return totals


def main() -> None:
    """CLI entry point for annual, education or combined ingestion."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--type", choices=["annual", "education", "all"], default="all")
    parser.add_argument("--env", type=Path, help="Defaults to .env beside this script")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    summary = run_ingestion(args.type, args.env)
    print(json.dumps(summary, indent=2))
    if summary["failed_documents"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
