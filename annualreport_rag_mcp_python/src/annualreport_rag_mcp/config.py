from __future__ import annotations

import os
from dataclasses import dataclass


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


def _positive_int(name: str, default: str) -> int:
    value = int(os.getenv(name, default))
    if value < 1:
        raise ValueError(f"{name} must be positive.")
    return value


@dataclass(frozen=True)
class Settings:
    qdrant_url: str
    qdrant_api_key: str | None
    collection: str
    ollama_url: str
    embedding_model: str
    request_timeout_seconds: float
    host: str
    port: int
    path: str
    allowed_hosts: tuple[str, ...]
    log_level: str
    max_results: int

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333").rstrip("/"),
            qdrant_api_key=os.getenv("QDRANT_API_KEY") or None,
            collection=os.getenv("QDRANT_COLLECTION", "annual_reports"),
            ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
            host=os.getenv("MCP_HOST", "0.0.0.0"),
            port=int(os.getenv("MCP_PORT", "8003")),
            path=os.getenv("MCP_PATH", "/mcp"),
            allowed_hosts=_csv(
                "MCP_ALLOWED_HOSTS",
                "localhost,localhost:*,127.0.0.1,127.0.0.1:*,annualreport-rag-mcp,annualreport-rag-mcp:*",
            ),
            log_level=os.getenv("MCP_LOG_LEVEL", "INFO").upper(),
            max_results=_positive_int("MCP_MAX_RESULTS", "20"),
        )
        if not settings.path.startswith("/"):
            raise ValueError("MCP_PATH must start with '/'.")
        if settings.request_timeout_seconds <= 0:
            raise ValueError("REQUEST_TIMEOUT_SECONDS must be positive.")
        return settings

