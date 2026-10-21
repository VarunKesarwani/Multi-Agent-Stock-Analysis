"""Compatibility facade for notebooks and existing ingestion scripts."""
from src.utils.config import PipelineConfig
from src.chunking.chunker import split_bounded_text, prepare_chunks
from src.vectordb.vector_store import create_payload
from src.ingestion.pipeline import AnnualReportEmbeddingPipeline, IngestionSummary
