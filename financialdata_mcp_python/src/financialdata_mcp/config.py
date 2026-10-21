from __future__ import annotations

import os
from dataclasses import dataclass


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    mongodb_uri: str
    mongodb_database: str
    host: str
    port: int
    path: str
    allowed_hosts: tuple[str, ...]
    log_level: str
    max_results: int

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            mongodb_uri=os.getenv("MONGODB_URI", "mongodb://localhost:27017/?directConnection=true"),
            mongodb_database=os.getenv("MONGODB_DATABASE", "financial_ingestion"),
            host=os.getenv("MCP_HOST", "0.0.0.0"),
            port=int(os.getenv("MCP_PORT", "8001")),
            path=os.getenv("MCP_PATH", "/mcp"),
            allowed_hosts=_csv(
                "MCP_ALLOWED_HOSTS",
                "localhost,localhost:*,127.0.0.1,127.0.0.1:*,financialdata-mcp,financialdata-mcp:*",
            ),
            log_level=os.getenv("MCP_LOG_LEVEL", "INFO").upper(),
            max_results=int(os.getenv("MCP_MAX_RESULTS", "500")),
        )
        if not settings.path.startswith("/"):
            raise ValueError("MCP_PATH must start with '/'.")
        if settings.max_results < 1:
            raise ValueError("MCP_MAX_RESULTS must be positive.")
        return settings

