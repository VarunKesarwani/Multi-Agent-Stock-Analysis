"""Validated embedding and ingestion configuration."""

import math
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class PipelineConfig:
    embedding_type: str = "ollama"
    openai_api_key: str = field(default="", repr=False)
    openai_base_url: str = "https://api.openai.com/v1"
    qdrant_api_key: str | None = field(default=None, repr=False)
    allow_legacy_embeddings: bool = False
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "nomic-embed-text"
    qdrant_url: str = "http://localhost:6333"
    collection_name: str = "annual_reports"
    embed_batch_size: int = 8
    qdrant_lookup_batch_size: int = 256
    max_chunk_chars: int = 4_000
    chunk_overlap_chars: int = 400
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 120.0
    qdrant_timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_base_seconds: float = 2.0
    skip_existing: bool = True
    failure_log: Path = Path("annual_report_embedding_failures.jsonl")

    @classmethod
    def from_env(cls, env_file: Path | str | None = None) -> "PipelineConfig":
        """Load the project .env; process variables override file values."""
        from src.utils.settings import boolean, env_path, env_values

        values, root = env_values(env_file)
        kind = values.get("EMBEDDING_TYPE", "ollama").lower()
        config = cls(
            embedding_type=kind,
            embedding_model=values.get(
                "EMBEDDING_MODEL",
                "nomic-embed-text" if kind == "ollama" else "text-embedding-3-small",
            ),
            ollama_base_url=values.get("OLLAMA_URL", "http://localhost:11434"),
            openai_base_url=values.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            openai_api_key=values.get("OPENAI_API_KEY", ""),
            qdrant_url=values.get("QDRANT_URL", "http://localhost:6333"),
            qdrant_api_key=values.get("QDRANT_API_KEY") or None,
            collection_name=values.get("QDRANT_COLLECTION", "annual_reports"),
            embed_batch_size=int(values.get("EMBED_BATCH_SIZE", "8")),
            qdrant_lookup_batch_size=int(values.get("QDRANT_LOOKUP_BATCH_SIZE", "256")),
            max_chunk_chars=int(values.get("CHUNK_SIZE_CHARS", "4000")),
            chunk_overlap_chars=int(values.get("CHUNK_OVERLAP_CHARS", "400")),
            connect_timeout_seconds=float(values.get("CONNECT_TIMEOUT_SECONDS", "5")),
            read_timeout_seconds=float(values.get("EMBED_TIMEOUT_SECONDS", "120")),
            qdrant_timeout_seconds=float(values.get("QDRANT_TIMEOUT_SECONDS", "30")),
            max_retries=int(values.get("EMBED_MAX_ATTEMPTS", "3")),
            retry_base_seconds=float(values.get("RETRY_BASE_SECONDS", "2")),
            skip_existing=boolean(values.get("SKIP_EXISTING", "true")),
            allow_legacy_embeddings=boolean(
                values.get("ALLOW_LEGACY_EMBEDDINGS", "false")
            ),
            failure_log=env_path(
                values.get("FAILURE_LOG", "annual_report_embedding_failures.jsonl"),
                root,
            ),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.embedding_type not in {"ollama", "openai"}:
            raise ValueError("EMBEDDING_TYPE must be ollama or openai")
        if self.embedding_type == "openai" and not self.openai_api_key.strip():
            raise ValueError("OPENAI_API_KEY is required for openai embeddings")
        if not self.embedding_model.strip() or not self.collection_name.strip():
            raise ValueError("Embedding model and Qdrant collection must not be blank")
        if self.qdrant_lookup_batch_size < 1:
            raise ValueError("qdrant_lookup_batch_size must be positive")
        for value in (
            self.connect_timeout_seconds,
            self.read_timeout_seconds,
            self.qdrant_timeout_seconds,
            self.retry_base_seconds,
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError("Timeouts and retry delay must be finite and positive")
        if self.embed_batch_size < 1:
            raise ValueError("embed_batch_size must be at least 1")
        if self.max_chunk_chars < 100:
            raise ValueError("max_chunk_chars must be at least 100")
        if not 0 <= self.chunk_overlap_chars < self.max_chunk_chars:
            raise ValueError(
                "chunk_overlap_chars must be >= 0 and smaller than max_chunk_chars"
            )
        if self.max_retries < 1:
            raise ValueError("max_retries must be at least 1")
