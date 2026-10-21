"""Compose retrieval, prompts and answer generation for CLI and API."""

from contextlib import contextmanager

from src.ingestion.pipeline import AnnualReportEmbeddingPipeline
from src.llm.llm_client import LLMClient
from src.prompts.prompt_templates import build_messages
from src.retrieval.retriever import Retriever, SearchRequest
from src.utils.config import PipelineConfig
from src.utils.runtime import RuntimeSettings


class RAGService:
    """Return source passages alongside generated answers."""

    def __init__(self, retriever, llm, settings: RuntimeSettings):
        self.retriever, self.llm, self.settings = retriever, llm, settings

    def search(self, request: SearchRequest) -> dict:
        """Search without invoking an answer model."""
        return {"query": request.query, "hits": self.retriever.search(request)}

    def ask(self, request: SearchRequest) -> dict:
        """Skip generation when no supporting source fits the context budget."""
        hits = self.retriever.search(request)
        messages, sources = build_messages(
            request.query, hits, self.settings.context_chars
        )
        if not sources:
            return {
                "answer": "I could not find supporting passages in the indexed documents.",
                "sources": [],
            }
        return {"answer": self.llm.generate(messages), "sources": sources}


@contextmanager
def open_service(env_file=None):
    """Create request-owned clients so synchronous requests do not share sessions."""
    settings = RuntimeSettings.from_env(env_file)
    pipeline = AnnualReportEmbeddingPipeline(PipelineConfig.from_env(env_file))
    llm = LLMClient(settings)
    try:
        yield RAGService(Retriever(pipeline), llm, settings)
    finally:
        llm.close()
        pipeline.close()
